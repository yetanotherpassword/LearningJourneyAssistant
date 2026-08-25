"""Unit tests for lja.model.gap_detection. Builds LjaDataset objects and
SiloClusteringResult objects directly rather than going through the Excel
loader or an LLM -- this module's job is pure arithmetic and classification,
and should be testable as such.
"""

from __future__ import annotations

from lja.data.excel_loader import LjaDataset, ResultRow
from lja.model.gap_detection import (
    DEFAULT_HIGH_THRESHOLD,
    DEFAULT_LOW_THRESHOLD,
    build_silo_to_competency_map,
    compute_gaps,
)
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef


def _dataset(results: list[ResultRow]) -> LjaDataset:
    return LjaDataset(silos={}, assessments=[], results=results, student_summaries=[])


def _clustering(*groups: tuple[str, list[tuple[str, str]]]) -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label=label,
                rationale="test",
                members=[SiloRef(subject_code=s, silo_local_id=i) for s, i in members],
            )
            for label, members in groups
        ]
    )


def test_build_silo_to_competency_map_flattens_clusters() -> None:
    clustering = _clustering(("Verification", [("SUBA", "SILO1"), ("SUBB", "SILO2")]))
    mapping = build_silo_to_competency_map(clustering)
    assert mapping == {"SUBA:SILO1": "Verification", "SUBB:SILO2": "Verification"}


def test_compute_gaps_proficient_single_subject() -> None:
    clustering = _clustering(("Skill", [("SUBA", "SILO1")]))
    results = [
        ResultRow("STU1", "SUBA", "Test", score=90.0, feedback_comment="", weight=1.0, weighted_score=90.0, silo_ids=("SILO1",))
    ]
    gaps = compute_gaps(_dataset(results), clustering)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.attainment_pct == 90.0
    assert gap.subjects_evidencing == 1
    assert gap.classification == "proficient"


def test_compute_gaps_weights_multiple_assessments() -> None:
    clustering = _clustering(("Skill", [("SUBA", "SILO1")]))
    results = [
        ResultRow("STU1", "SUBA", "Test", score=80.0, feedback_comment="", weight=0.4, weighted_score=32.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "SUBA", "Exam", score=40.0, feedback_comment="", weight=0.6, weighted_score=24.0, silo_ids=("SILO1",)),
    ]
    gaps = compute_gaps(_dataset(results), clustering)
    # weighted mean: (80*0.4 + 40*0.6) / (0.4+0.6) = 56.0
    assert gaps[0].attainment_pct == 56.0
    assert gaps[0].n_observations == 2


def test_compute_gaps_isolated_vs_persistent_gap() -> None:
    clustering = _clustering(("Skill", [("SUBA", "SILO1"), ("SUBB", "SILO1")]))

    # STU1: weak in only one subject -> isolated gap.
    isolated_results = [
        ResultRow("STU1", "SUBA", "Test", score=30.0, feedback_comment="", weight=1.0, weighted_score=30.0, silo_ids=("SILO1",)),
    ]
    gaps = compute_gaps(_dataset(isolated_results), clustering)
    assert gaps[0].classification == "isolated gap"

    # STU2: weak in the SAME competency across two different subjects -> persistent gap.
    persistent_results = [
        ResultRow("STU2", "SUBA", "Test", score=30.0, feedback_comment="", weight=1.0, weighted_score=30.0, silo_ids=("SILO1",)),
        ResultRow("STU2", "SUBB", "Exam", score=35.0, feedback_comment="", weight=1.0, weighted_score=35.0, silo_ids=("SILO1",)),
    ]
    gaps = compute_gaps(_dataset(persistent_results), clustering)
    assert gaps[0].classification == "persistent gap"
    assert gaps[0].subjects_evidencing == 2


def test_compute_gaps_developing_band_between_thresholds() -> None:
    clustering = _clustering(("Skill", [("SUBA", "SILO1")]))
    midpoint = (DEFAULT_LOW_THRESHOLD + DEFAULT_HIGH_THRESHOLD) / 2
    results = [
        ResultRow("STU1", "SUBA", "Test", score=midpoint, feedback_comment="", weight=1.0, weighted_score=midpoint, silo_ids=("SILO1",))
    ]
    gaps = compute_gaps(_dataset(results), clustering)
    assert gaps[0].classification == "developing"


def test_compute_gaps_one_assessment_evidences_multiple_silos_independently() -> None:
    """A single assessment covering two SILOs contributes its full score to
    BOTH competencies, not a split fraction of it -- see the design-decision
    note in gap_detection.py's module docstring.
    """
    clustering = _clustering(
        ("Competency A", [("SUBA", "SILO1")]),
        ("Competency B", [("SUBA", "SILO2")]),
    )
    results = [
        ResultRow("STU1", "SUBA", "Test", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO1", "SILO2")),
    ]
    gaps = {g.competency_label: g for g in compute_gaps(_dataset(results), clustering)}
    assert gaps["Competency A"].attainment_pct == 70.0
    assert gaps["Competency B"].attainment_pct == 70.0
