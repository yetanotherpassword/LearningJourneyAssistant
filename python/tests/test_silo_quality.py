"""Tests for lja.model.silo_quality -- pure functions over small in-memory
fixtures. Two subjects, three SILOs: one competency spans both subjects, one
SILO sits alone in its own cluster and is flagged, and one SILO is never
assessed. That is enough to exercise every issue class and the progression.
"""

from __future__ import annotations

from lja.data.excel_loader import Assessment, LjaDataset, ResultRow, Silo, StudentSummary
from lja.model.gap_detection import BASIS_FLOOR, BASIS_RELATIVE, CompetencyGap
from lja.model.silo_clustering import CompetencyCluster, FlaggedSilo, SiloClusteringResult, SiloRef
from lja.model.silo_quality import (
    assess_silos,
    competency_progressions,
    discipline_links,
    slugify,
    subject_competency_matrix,
    subject_links,
    summarise_subjects,
    term_kind,
    term_weights,
)

DS = "Data structures and algorithms"


def _dataset() -> LjaDataset:
    silos = {
        "CSE1OOF:SILO1": Silo("CSE1OOF", "SILO1", "Implement and analyse basic data structures in a program"),
        "CSE2ALG:SILO1": Silo("CSE2ALG", "SILO1", "Understand and appreciate the general objectives of algorithms"),
        "CSE2ALG:SILO2": Silo("CSE2ALG", "SILO2", "Design and evaluate data structures for a given problem"),
    }
    assessments = [
        Assessment("CSE1OOF", "Test", 40.0, "Individual", False, False, ("SILO1",)),
        Assessment("CSE2ALG", "Assignment", 60.0, "Individual", False, False, ("SILO2",)),
    ]
    results = [
        ResultRow("STU1", "CSE1OOF", "Test", 80.0, "ok", 40.0, 32.0, ("SILO1",)),
        ResultRow("STU2", "CSE1OOF", "Test", 40.0, "weak", 40.0, 16.0, ("SILO1",)),
        ResultRow("STU1", "CSE2ALG", "Assignment", 60.0, "ok", 60.0, 36.0, ("SILO2",)),
        ResultRow("STU2", "CSE2ALG", "Assignment", 30.0, "weak", 60.0, 18.0, ("SILO2",)),
    ]
    summaries = [
        StudentSummary("STU1", {"CSE1OOF": 80.0, "CSE2ALG": 60.0}, 70.0, "Credit"),
        StudentSummary("STU2", {"CSE1OOF": 40.0, "CSE2ALG": 30.0}, 35.0, "Fail"),
    ]
    return LjaDataset(silos=silos, assessments=assessments, results=results, student_summaries=summaries)


def _clustering() -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label=DS,
                rationale="Both describe building and reasoning about data structures.",
                members=[SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1"), SiloRef(subject_code="CSE2ALG", silo_local_id="SILO2")],
            ),
            CompetencyCluster(
                competency_label="Vague outcome",
                rationale="Cannot be linked to anything specific.",
                members=[SiloRef(subject_code="CSE2ALG", silo_local_id="SILO1")],
            ),
        ],
        flagged_silos=[FlaggedSilo(subject_code="CSE2ALG", silo_local_id="SILO1", reason="Vague wording; not assessable.")],
    )


def _gaps() -> list[CompetencyGap]:
    return [
        CompetencyGap("STU1", DS, 68.0, 2, 2, "proficient", BASIS_RELATIVE, 1.2),
        CompetencyGap("STU2", DS, 34.0, 2, 2, "persistent gap", BASIS_FLOOR, None),
    ]


def test_assess_silos_finds_every_issue_class() -> None:
    rows = {r.key: r for r in assess_silos(_dataset(), _clustering(), _gaps())}
    assert set(rows) == {"CSE1OOF:SILO1", "CSE2ALG:SILO1", "CSE2ALG:SILO2"}

    good = rows["CSE1OOF:SILO1"]
    assert good.issues == ()
    assert good.competency_label == DS
    assert good.cluster_span == 2
    assert good.n_assessments == 1
    assert good.n_students == 2
    assert good.mean_attainment == 60.0  # equal weights: (80 + 40) / 2
    assert good.gap_rate == 50.0  # STU2 has a persistent gap on DS

    bad = rows["CSE2ALG:SILO1"]
    assert bad.flagged and bad.flag_reason.startswith("Vague")
    assert bad.orphan
    assert bad.n_assessments == 0 and bad.mean_attainment is None and bad.gap_rate is None
    assert "understand" in bad.vague_terms and "appreciate" in bad.vague_terms
    assert set(bad.issues) == {"flagged", "no cross-subject link", "not assessed", "vague wording"}


def test_attainment_is_weight_weighted_like_gap_detection() -> None:
    dataset = _dataset()
    dataset.results.append(ResultRow("STU1", "CSE2ALG", "Exam", 100.0, "", 20.0, 20.0, ("SILO2",)))
    dataset.assessments.append(Assessment("CSE2ALG", "Exam", 20.0, "Individual", False, False, ("SILO2",)))
    rows = {r.key: r for r in assess_silos(dataset, _clustering(), _gaps())}
    # (60*60 + 30*60 + 100*20) / 140 = 7400 / 140
    assert rows["CSE2ALG:SILO2"].mean_attainment == round(7400 / 140, 2)
    assert rows["CSE2ALG:SILO2"].n_assessments == 2


def test_subject_summary_counts_and_health() -> None:
    dataset, clustering, gaps = _dataset(), _clustering(), _gaps()
    subjects = {s.subject_code: s for s in summarise_subjects(assess_silos(dataset, clustering, gaps), dataset, gaps)}
    alg = subjects["CSE2ALG"]
    assert alg.n_silos == 2 and alg.n_flagged == 1 and alg.n_orphan == 1 and alg.n_unassessed == 1 and alg.n_vague == 1
    assert alg.n_clean == 1 and alg.health == 50.0
    assert alg.year_level == 2 and alg.n_students == 2
    # Both students are evidenced on DS via CSE2ALG:SILO2; STU2's is a gap -> 1 of 2 pairs.
    assert alg.gap_rate == 50.0
    assert subjects["CSE1OOF"].health == 100.0
    # Worst health first.
    assert [s.subject_code for s in summarise_subjects(assess_silos(dataset, clustering, gaps), dataset, gaps)] == ["CSE2ALG", "CSE1OOF"]


def test_term_weights_classify_vocabulary_and_count_once_per_silo() -> None:
    terms = {t.term: t for t in term_weights(assess_silos(_dataset(), _clustering(), _gaps()))}
    assert terms["data"].count == 2 and terms["data"].n_subjects == 2
    assert terms["understand"].kind == "vague"
    assert terms["implement"].kind == "measurable" and terms["evaluate"].kind == "measurable"
    assert terms["structures"].kind == "other"
    assert "the" not in terms and "and" not in terms
    # Attainment on the terms' outcomes: 'data' appears in SILOs at 60.0 and 45.0.
    assert terms["data"].mean_attainment == 52.5
    assert terms["understand"].mean_attainment is None  # its only SILO is unassessed


def test_term_kind_matches_stems() -> None:
    assert term_kind("analysing") == "measurable"
    assert term_kind("appreciation") == "vague"
    assert term_kind("banana") == "other"


def test_progression_orders_subjects_by_year_and_reports_delta() -> None:
    progressions = competency_progressions(_dataset(), _clustering(), _gaps())
    assert [p.label for p in progressions] == [DS]  # the single-subject cluster has no progression
    p = progressions[0]
    assert p.slug == "data-structures-and-algorithms"
    assert [pt.subject_code for pt in p.points] == ["CSE1OOF", "CSE2ALG"]
    assert [pt.mean_attainment for pt in p.points] == [60.0, 45.0]
    assert [pt.gap_rate for pt in p.points] == [50.0, 50.0]
    assert p.delta == -15.0 and p.trend == "declining"
    assert not any(pt.flagged for pt in p.points)


def test_subject_links_matrix_is_symmetric_with_labels() -> None:
    links = subject_links(_clustering())
    assert links.subjects == ("CSE1OOF", "CSE2ALG")
    assert links.matrix == ((0, 1), (1, 0))
    assert links.shared[("CSE1OOF", "CSE2ALG")] == (DS,)


def test_matrix_leaves_untaught_cells_empty() -> None:
    m = subject_competency_matrix(_dataset(), _clustering())
    assert m.subjects == ("CSE1OOF", "CSE2ALG")
    assert m.competencies == (DS, "Vague outcome")
    assert m.cells[0] == (60.0, None)
    assert m.cells[1] == (45.0, None)  # the vague outcome is never assessed


def test_slugify() -> None:
    assert slugify("Object-oriented analysis & modelling") == "object-oriented-analysis-modelling"
    assert slugify("!!!") == "competency"


def test_discipline_links_count_distinct_competencies_and_keep_internal_links() -> None:
    clustering = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Proof",
                rationale="r",
                members=[SiloRef(subject_code=c, silo_local_id="SILO1") for c in ("CSE1OOF", "CSE2ALG", "MAT1001", "MAT2001")],
            ),
            CompetencyCluster(
                competency_label="Solo",
                rationale="r",
                members=[SiloRef(subject_code="PHY1SCA", silo_local_id="SILO1")],
            ),
        ],
        flagged_silos=[],
    )
    links = discipline_links(clustering)
    assert links.disciplines == ("CSE", "MAT", "PHY")
    assert links.subject_counts == (2, 2, 1)
    # One competency spanning four subjects in two disciplines is ONE link, not four.
    assert links.matrix == ((1, 1, 0), (1, 1, 0), (0, 0, 0))
    assert links.shared[("CSE", "MAT")] == ("Proof",)
    assert links.shared[("CSE", "CSE")] == ("Proof",)
