"""Unit tests for lja.data.synth_generator. The LLM-driven feedback bank
generation is exercised only via its fallback path here (deterministic,
offline); everything else -- score generation, the planted-gap mechanism,
band/total arithmetic -- is pure and fully testable without a live model.
"""

from __future__ import annotations

import random

import pytest

from lja.data.excel_loader import Assessment, LjaDataset, Silo
from lja.data.synth_generator import (
    _FALLBACK_TEMPLATES,
    _feedback_band,
    _join_naturally,
    _next_start_index,
    generate_synthetic_students,
)


def _small_dataset() -> LjaDataset:
    silos = {
        "SUBA:SILO1": Silo("SUBA", "SILO1", "alpha skill"),
        "SUBA:SILO2": Silo("SUBA", "SILO2", "beta skill"),
        "SUBB:SILO1": Silo("SUBB", "SILO1", "gamma skill"),
    }
    assessments = [
        Assessment("SUBA", "Test", 1.0, "Individual", False, False, ("SILO1", "SILO2")),
        Assessment("SUBB", "Exam", 1.0, "Individual", False, False, ("SILO1",)),
    ]
    return LjaDataset(silos=silos, assessments=assessments, results=[], student_summaries=[])


@pytest.mark.parametrize(
    ("score", "expected_band"),
    [(10, "limited"), (49.9, "limited"), (50, "developing"), (64.9, "developing"), (65, "proficient"), (79.9, "proficient"), (80, "excellent"), (100, "excellent")],
)
def test_feedback_band_boundaries(score: float, expected_band: str) -> None:
    assert _feedback_band(score) == expected_band


def test_join_naturally() -> None:
    assert _join_naturally([]) == "the assessed learning themes"
    assert _join_naturally(["a"]) == "a"
    assert _join_naturally(["a", "b"]) == "a and b"
    assert _join_naturally(["a", "b", "c"]) == "a, b and c"


def test_next_start_index_continues_after_existing_students() -> None:
    from lja.data.excel_loader import StudentSummary

    dataset = _small_dataset()
    dataset = LjaDataset(
        silos=dataset.silos,
        assessments=dataset.assessments,
        results=[],
        student_summaries=[
            StudentSummary("STU0001", {}, 0, "C range"),
            StudentSummary("STU0150", {}, 0, "C range"),
        ],
    )
    assert _next_start_index(dataset) == 151


def test_next_start_index_empty_dataset_starts_at_one() -> None:
    assert _next_start_index(_small_dataset()) == 1


def test_generate_synthetic_students_produces_one_row_per_assessment() -> None:
    dataset = _small_dataset()
    results, summaries, planted = generate_synthetic_students(
        dataset,
        n_students=5,
        start_index=1,
        planted_gap_silos=set(),
        planted_gap_fraction=0.0,
        feedback_bank=dict(_FALLBACK_TEMPLATES),
        rng=random.Random(1),
    )
    assert len(summaries) == 5
    assert len(results) == 5 * len(dataset.assessments)
    assert planted == []
    ids = {s.student_id for s in summaries}
    assert ids == {"STU0001", "STU0002", "STU0003", "STU0004", "STU0005"}


def test_generate_synthetic_students_subject_total_equals_sum_of_weighted_scores() -> None:
    """Mirrors the real dataset's own invariant, confirmed by inspection:
    a subject's Total is exactly the sum of that subject's Weighted Score
    rows, not an independent number.
    """
    dataset = _small_dataset()
    results, summaries, _ = generate_synthetic_students(
        dataset,
        n_students=10,
        start_index=1,
        planted_gap_silos=set(),
        planted_gap_fraction=0.0,
        feedback_bank=dict(_FALLBACK_TEMPLATES),
        rng=random.Random(7),
    )
    for summary in summaries:
        for subject_code, total in summary.subject_totals.items():
            expected = round(
                sum(r.weighted_score for r in results if r.student_id == summary.student_id and r.subject_code == subject_code),
                2,
            )
            assert total == pytest.approx(expected)


def test_generate_synthetic_students_average_total_and_band_are_consistent() -> None:
    dataset = _small_dataset()
    _, summaries, _ = generate_synthetic_students(
        dataset,
        n_students=30,
        start_index=1,
        planted_gap_silos=set(),
        planted_gap_fraction=0.0,
        feedback_bank=dict(_FALLBACK_TEMPLATES),
        rng=random.Random(3),
    )
    for summary in summaries:
        expected_avg = round(sum(summary.subject_totals.values()) / len(summary.subject_totals), 4)
        assert summary.average_total == pytest.approx(expected_avg)
        if summary.average_total < 50:
            assert summary.performance_band == "At risk"
        elif summary.average_total < 60:
            assert summary.performance_band == "P range"
        elif summary.average_total < 70:
            assert summary.performance_band == "C range"
        elif summary.average_total < 80:
            assert summary.performance_band == "D range"
        else:
            assert summary.performance_band == "HD/D range"


def test_planted_gap_group_is_suppressed_only_on_targeted_silos() -> None:
    """The core correctness property of the whole generator: a planted
    student's SUBB score (untouched SILO) should look like anyone else's,
    while their SUBA score (touches the planted SILO) should be pulled
    down hard. Run with fraction=1.0 so every student is planted --
    removes sampling luck from the assertion.
    """
    dataset = _small_dataset()
    planted_results, _, planted_ids = generate_synthetic_students(
        dataset,
        n_students=20,
        start_index=1,
        planted_gap_silos={"SUBA:SILO1"},
        planted_gap_fraction=1.0,
        feedback_bank=dict(_FALLBACK_TEMPLATES),
        rng=random.Random(11),
    )
    assert len(planted_ids) == 20  # every student planted

    suba_scores = [r.score for r in planted_results if r.subject_code == "SUBA"]
    subb_scores = [r.score for r in planted_results if r.subject_code == "SUBB"]

    avg_suba = sum(suba_scores) / len(suba_scores)
    avg_subb = sum(subb_scores) / len(subb_scores)
    # SUBA touches the planted SILO and should be suppressed well below
    # the real dataset's ~68 baseline mean; SUBB is untouched and should
    # stay near it.
    assert avg_suba < 55
    assert avg_subb > 55
