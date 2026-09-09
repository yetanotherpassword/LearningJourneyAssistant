"""Unit tests for lja.model.gap_evidence -- built the same way as
test_gap_detection.py: LjaDataset/SiloClusteringResult objects constructed
directly, no Excel loader, no LLM.
"""

from __future__ import annotations

from lja.data.excel_loader import LjaDataset, ResultRow, StudentSummary
from lja.model.gap_evidence import (
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_INSUFFICIENT,
    TREND_STABLE,
    SubjectEvidence,
    _parse_year_level,
    describe_trend,
    future_subjects_sharing_competency,
    subject_breakdown,
)
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef


def _dataset(results: list[ResultRow] | None = None, summaries: list[StudentSummary] | None = None) -> LjaDataset:
    return LjaDataset(silos={}, assessments=[], results=results or [], student_summaries=summaries or [])


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


def test_parse_year_level_reads_the_digit_out_of_the_subject_code() -> None:
    assert _parse_year_level("CSE1OOF") == 1
    assert _parse_year_level("CSE2ALG") == 2
    assert _parse_year_level("CSE3CAP") == 3


def test_parse_year_level_returns_none_for_a_code_with_no_leading_digit() -> None:
    assert _parse_year_level("NOYEAR") is None


def test_subject_breakdown_splits_and_weights_per_subject() -> None:
    clustering = _clustering(("Skill", [("CSE1OOF", "SILO1"), ("CSE2ALG", "SILO1")]))
    results = [
        ResultRow("STU1", "CSE1OOF", "Test", score=80.0, feedback_comment="", weight=0.4, weighted_score=32.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "CSE1OOF", "Exam", score=40.0, feedback_comment="", weight=0.6, weighted_score=24.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "CSE2ALG", "Test", score=90.0, feedback_comment="", weight=1.0, weighted_score=90.0, silo_ids=("SILO1",)),
        # A different student's row must never leak into STU1's breakdown.
        ResultRow("STU2", "CSE1OOF", "Test", score=10.0, feedback_comment="", weight=1.0, weighted_score=10.0, silo_ids=("SILO1",)),
    ]
    evidence = subject_breakdown(_dataset(results), clustering, "STU1", "Skill")

    by_subject = {e.subject_code: e for e in evidence}
    assert by_subject["CSE1OOF"].attainment_pct == 56.0  # (80*0.4 + 40*0.6) / 1.0
    assert by_subject["CSE1OOF"].n_observations == 2
    assert by_subject["CSE1OOF"].year_level == 1
    assert by_subject["CSE2ALG"].attainment_pct == 90.0
    assert by_subject["CSE2ALG"].year_level == 2

    # Sorted by year level, earliest first.
    assert [e.subject_code for e in evidence] == ["CSE1OOF", "CSE2ALG"]


def test_subject_breakdown_counts_a_multi_silo_row_once_per_subject() -> None:
    """A row carrying two SILOs that both land in the requested competency
    (e.g. via two different flagged SILOs) must not be double-counted.
    """
    clustering = _clustering(("Skill", [("CSE1OOF", "SILO1"), ("CSE1OOF", "SILO2")]))
    results = [
        ResultRow("STU1", "CSE1OOF", "Test", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO1", "SILO2")),
    ]
    evidence = subject_breakdown(_dataset(results), clustering, "STU1", "Skill")
    assert len(evidence) == 1
    assert evidence[0].n_observations == 1


def test_describe_trend_improving_and_declining() -> None:
    improving = [
        SubjectEvidence("CSE1OOF", 1, 30.0, 2),
        SubjectEvidence("CSE2ALG", 2, 60.0, 2),
    ]
    assert describe_trend(improving) == TREND_IMPROVING

    declining = [
        SubjectEvidence("CSE1OOF", 1, 70.0, 2),
        SubjectEvidence("CSE2ALG", 2, 35.0, 2),
    ]
    assert describe_trend(declining) == TREND_DECLINING


def test_describe_trend_stable_within_the_band() -> None:
    stable = [
        SubjectEvidence("CSE1OOF", 1, 50.0, 2),
        SubjectEvidence("CSE2ALG", 2, 53.0, 2),
    ]
    assert describe_trend(stable) == TREND_STABLE


def test_describe_trend_insufficient_with_fewer_than_two_dated_subjects() -> None:
    assert describe_trend([SubjectEvidence("CSE1OOF", 1, 40.0, 2)]) == TREND_INSUFFICIENT
    # A subject with no parseable year level never counts toward the comparison.
    assert describe_trend([SubjectEvidence("CSE1OOF", 1, 40.0, 2), SubjectEvidence("NOYEAR", None, 90.0, 1)]) == TREND_INSUFFICIENT


def test_future_subjects_sharing_competency_excludes_subjects_already_taken() -> None:
    dataset = _dataset(
        summaries=[StudentSummary("STU1", subject_totals={"CSE1OOF": 70.0}, average_total=70.0, performance_band="Credit")]
    )
    clustering = _clustering(("Skill", [("CSE1OOF", "SILO1"), ("CSE2ALG", "SILO1"), ("CSE3CAP", "SILO1")]))
    result = future_subjects_sharing_competency(dataset, clustering, "STU1", "Skill")
    assert result == ["CSE2ALG", "CSE3CAP"]


def test_future_subjects_sharing_competency_is_empty_once_everything_is_taken() -> None:
    """The honest null result on the current 3-subject fixture, where every
    student already has results in every offered subject.
    """
    dataset = _dataset(
        summaries=[
            StudentSummary(
                "STU1",
                subject_totals={"CSE1OOF": 70.0, "CSE2ALG": 60.0, "CSE3CAP": 65.0},
                average_total=65.0,
                performance_band="Credit",
            )
        ]
    )
    clustering = _clustering(("Skill", [("CSE1OOF", "SILO1"), ("CSE2ALG", "SILO1")]))
    assert future_subjects_sharing_competency(dataset, clustering, "STU1", "Skill") == []


def test_future_subjects_sharing_competency_unknown_student_returns_empty() -> None:
    dataset = _dataset(summaries=[])
    clustering = _clustering(("Skill", [("CSE1OOF", "SILO1")]))
    assert future_subjects_sharing_competency(dataset, clustering, "GHOST", "Skill") == []
