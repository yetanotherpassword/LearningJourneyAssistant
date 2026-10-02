"""Unit tests for lja.model.trajectory (IOLG-106) -- built like
test_gap_evidence.py: LjaDataset/SiloClusteringResult objects constructed
directly, no Excel loader, no LLM.

One test per rule in the brief: sequence parsing, the year-digit fallback,
delta and label boundaries at the band, a student who skipped a subject,
the basis label, and the ordering of the subjects ahead.
"""

from __future__ import annotations

from lja.data.excel_loader import LjaDataset, ResultRow, StudentSummary
from lja.model.gap_evidence import (
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_INSUFFICIENT,
    TREND_STABLE,
    SubjectEvidence,
)
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef
from lja.model.trajectory import (
    BASIS_DECLARED,
    BASIS_MIXED,
    BASIS_NONE,
    BASIS_YEAR_DIGIT,
    SOURCE_DECLARED,
    SOURCE_UNKNOWN,
    SOURCE_YEAR_DIGIT,
    SubjectSequence,
    compute_trajectories,
    compute_trajectory,
    describe_trend,
    trend_label,
)

SEQ = SubjectSequence(("CSE1OOF", "CSE2ALG", "CSE3CAP"))


def _row(student: str, subject: str, score: float, silo: str = "SILO1", weight: float = 1.0) -> ResultRow:
    return ResultRow(
        student_id=student, subject_code=subject, assessment_name="Exam", score=score,
        feedback_comment="", weight=weight, weighted_score=score * weight, silo_ids=(silo,),
    )


def _dataset(results: list[ResultRow], taken: dict[str, dict[str, float]]) -> LjaDataset:
    summaries = [
        StudentSummary(student_id=s, subject_totals=totals, average_total=60.0, performance_band="P")
        for s, totals in taken.items()
    ]
    return LjaDataset(silos={}, assessments=[], results=results, student_summaries=summaries)


def _clustering(label: str, *subjects: str) -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label=label, rationale="test",
                members=[SiloRef(subject_code=s, silo_local_id="SILO1") for s in subjects],
            )
        ]
    )


# ---------------------------------------------------------------- sequence parsing

def test_sequence_parses_a_comma_list_ignoring_whitespace_blanks_and_repeats() -> None:
    seq = SubjectSequence.from_string(" CSE1OOF, CSE2ALG ,, CSE3CAP,CSE2ALG ")
    assert seq.declared == ("CSE1OOF", "CSE2ALG", "CSE3CAP")


def test_declared_subjects_order_by_their_place_not_their_year_digit() -> None:
    # Declared order deliberately contradicts the digits: the declaration wins.
    seq = SubjectSequence.from_string("CSE3CAP,CSE1OOF")
    assert seq.position("CSE3CAP").source == SOURCE_DECLARED
    assert seq.sort_key("CSE3CAP") < seq.sort_key("CSE1OOF")


def test_undeclared_subject_falls_back_to_the_year_digit_after_every_declared_one() -> None:
    pos = SEQ.position("MAT1ALG")
    assert pos.source == SOURCE_YEAR_DIGIT
    assert SEQ.sort_key("CSE3CAP") < SEQ.sort_key("MAT1ALG")  # declared before any fallback
    assert SEQ.sort_key("MAT1ALG") < SEQ.sort_key("MAT2CAL")  # then by year


def test_subject_with_no_digit_is_unknown_and_sorts_last() -> None:
    pos = SEQ.position("CAPSTONE")
    assert pos.source == SOURCE_UNKNOWN
    assert not pos.ordered
    assert SEQ.sort_key("MAT2CAL") < SEQ.sort_key("CAPSTONE")


def test_empty_sequence_is_pure_year_digit_fallback() -> None:
    seq = SubjectSequence.from_string("")
    assert seq.declared == ()
    assert seq.position("CSE2ALG").source == SOURCE_YEAR_DIGIT


# ---------------------------------------------------------------- delta and label

def test_trend_label_boundaries_at_the_band() -> None:
    assert trend_label([60.0, 65.0], 5.0) == (5.0, TREND_STABLE)      # exactly the band is stable
    assert trend_label([60.0, 65.1], 5.0) == (5.1, TREND_IMPROVING)
    assert trend_label([65.1, 60.0], 5.0) == (-5.1, TREND_DECLINING)
    assert trend_label([60.0], 5.0) == (None, TREND_INSUFFICIENT)
    assert trend_label([], 5.0) == (None, TREND_INSUFFICIENT)


def test_band_is_configuration_not_a_constant() -> None:
    """Same two marks, two bands, two labels."""
    assert trend_label([60.0, 66.0], 5.0)[1] == TREND_IMPROVING
    assert trend_label([60.0, 66.0], 10.0)[1] == TREND_STABLE


def test_describe_trend_orders_by_the_declared_sequence_before_the_year_digit() -> None:
    """Evidence arrives in no particular order; the declared sequence
    decides first and last. Here the digits say OOF (1) then CAP (3) --
    stable -- but a sequence declaring CAP first makes it declining."""
    evidence = [
        SubjectEvidence("CSE3CAP", 3, 70.0, 2),
        SubjectEvidence("CSE1OOF", 1, 60.0, 2),
    ]
    assert describe_trend(evidence, sequence=SEQ, stable_band=5.0) == TREND_IMPROVING
    reversed_seq = SubjectSequence.from_string("CSE3CAP,CSE1OOF")
    assert describe_trend(evidence, sequence=reversed_seq, stable_band=5.0) == TREND_DECLINING


def test_describe_trend_ignores_subjects_that_cannot_be_ordered() -> None:
    evidence = [SubjectEvidence("CAPSTONE", None, 90.0, 1), SubjectEvidence("CSE1OOF", 1, 60.0, 2)]
    assert describe_trend(evidence, sequence=SEQ, stable_band=5.0) == TREND_INSUFFICIENT


# ---------------------------------------------------------------- compute_trajectory

def test_trajectory_lists_every_subject_in_the_competency_in_sequence_order() -> None:
    dataset = _dataset(
        [_row("S1", "CSE1OOF", 60.0), _row("S1", "CSE2ALG", 50.0)],
        {"S1": {"CSE1OOF": 60.0, "CSE2ALG": 50.0}},
    )
    clustering = _clustering("DS", "CSE3CAP", "CSE1OOF", "CSE2ALG")
    t = compute_trajectory(dataset, clustering, "S1", "DS", sequence=SEQ, stable_band=5.0)
    assert [p.subject_code for p in t.points] == ["CSE1OOF", "CSE2ALG", "CSE3CAP"]
    assert [p.taken for p in t.points] == [True, True, False]
    assert [p.subject_code for p in t.ahead] == ["CSE3CAP"]
    assert t.delta == -10.0
    assert t.label == TREND_DECLINING
    assert t.basis == BASIS_DECLARED
    assert t.stable_band == 5.0


def test_ahead_subjects_are_in_sequence_order_so_the_first_is_next() -> None:
    dataset = _dataset([_row("S1", "CSE1OOF", 55.0)], {"S1": {"CSE1OOF": 55.0}})
    clustering = _clustering("DS", "CSE3CAP", "CSE2ALG", "CSE1OOF")
    t = compute_trajectory(dataset, clustering, "S1", "DS", sequence=SEQ)
    assert [p.subject_code for p in t.ahead] == ["CSE2ALG", "CSE3CAP"]
    assert t.label == TREND_INSUFFICIENT  # one point is not a trend
    assert t.delta is None


def test_student_who_skipped_a_subject_still_gets_a_trend_from_the_ones_sat() -> None:
    """Sat OOF and CAP, never ALG: ALG is 'ahead' in the middle of the chain
    and the trend compares the two subjects actually sat."""
    dataset = _dataset(
        [_row("S1", "CSE1OOF", 50.0), _row("S1", "CSE3CAP", 70.0)],
        {"S1": {"CSE1OOF": 50.0, "CSE3CAP": 70.0}},
    )
    clustering = _clustering("DS", "CSE1OOF", "CSE2ALG", "CSE3CAP")
    t = compute_trajectory(dataset, clustering, "S1", "DS", sequence=SEQ, stable_band=5.0)
    assert [(p.subject_code, p.taken) for p in t.points] == [("CSE1OOF", True), ("CSE2ALG", False), ("CSE3CAP", True)]
    assert t.delta == 20.0
    assert t.label == TREND_IMPROVING


def test_basis_reports_year_digit_when_nothing_is_declared_and_mixed_when_both_apply() -> None:
    dataset = _dataset(
        [_row("S1", "MAT1ALG", 60.0), _row("S1", "MAT2CAL", 70.0)],
        {"S1": {"MAT1ALG": 60.0, "MAT2CAL": 70.0}},
    )
    clustering = _clustering("Maths", "MAT1ALG", "MAT2CAL")
    assert compute_trajectory(dataset, clustering, "S1", "Maths", sequence=SEQ).basis == BASIS_YEAR_DIGIT

    dataset = _dataset(
        [_row("S1", "CSE1OOF", 60.0), _row("S1", "MAT2CAL", 70.0)],
        {"S1": {"CSE1OOF": 60.0, "MAT2CAL": 70.0}},
    )
    clustering = _clustering("Mixed", "CSE1OOF", "MAT2CAL")
    assert compute_trajectory(dataset, clustering, "S1", "Mixed", sequence=SEQ).basis == BASIS_MIXED


def test_basis_is_none_and_trend_insufficient_when_no_subject_can_be_ordered() -> None:
    dataset = _dataset(
        [_row("S1", "CAPSTONE", 60.0), _row("S1", "HONOURS", 70.0)],
        {"S1": {"CAPSTONE": 60.0, "HONOURS": 70.0}},
    )
    clustering = _clustering("Proj", "CAPSTONE", "HONOURS")
    t = compute_trajectory(dataset, clustering, "S1", "Proj", sequence=SEQ)
    assert t.basis == BASIS_NONE
    assert t.label == TREND_INSUFFICIENT
    assert all(p.source == SOURCE_UNKNOWN for p in t.points)


def test_taken_subject_with_no_result_in_this_competency_is_taken_not_ahead() -> None:
    """The student sat CSE2ALG (it is in their totals) but none of its
    results touch this competency's SILOs: it must not be shown as a
    subject still ahead of them."""
    dataset = _dataset(
        [_row("S1", "CSE1OOF", 55.0)],
        {"S1": {"CSE1OOF": 55.0, "CSE2ALG": 61.0}},
    )
    clustering = _clustering("DS", "CSE1OOF", "CSE2ALG")
    t = compute_trajectory(dataset, clustering, "S1", "DS", sequence=SEQ)
    alg = next(p for p in t.points if p.subject_code == "CSE2ALG")
    assert alg.taken and alg.attainment_pct is None
    assert t.ahead == ()


def test_unknown_student_has_nothing_ahead() -> None:
    dataset = _dataset([], {})
    clustering = _clustering("DS", "CSE1OOF", "CSE2ALG")
    t = compute_trajectory(dataset, clustering, "NOBODY", "DS", sequence=SEQ)
    assert t.ahead == ()
    assert t.label == TREND_INSUFFICIENT


def test_compute_trajectories_keys_by_student_and_competency() -> None:
    dataset = _dataset(
        [_row("S1", "CSE1OOF", 60.0), _row("S2", "CSE1OOF", 80.0)],
        {"S1": {"CSE1OOF": 60.0}, "S2": {"CSE1OOF": 80.0}},
    )
    clustering = _clustering("DS", "CSE1OOF", "CSE2ALG")
    out = compute_trajectories(dataset, clustering, [("S1", "DS"), ("S2", "DS")], sequence=SEQ)
    assert set(out) == {("S1", "DS"), ("S2", "DS")}
    assert out[("S2", "DS")].taken[0].attainment_pct == 80.0
