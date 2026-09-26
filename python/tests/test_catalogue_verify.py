"""Tests for lja.data.catalogue_verify's scoring, on hand-built inputs."""

from __future__ import annotations

from lja.data.catalogue_verify import (
    labels_by_truth_competency,
    score_clustering,
    score_planted,
    score_unplanted,
)
from lja.model.silo_clustering import SiloClusteringResult

_TRUTH = {
    "competency_labels": {"alpha": "Alpha", "beta": "Beta"},
    "silo_competency": {"A:SILO1": "alpha", "B:SILO1": "alpha", "A:SILO2": "beta", "B:SILO2": "beta"},
    "planted": {"STU0001": {"competency": "beta", "depth": 20}, "STU0002": {"competency": "alpha", "depth": 25}},
    "students": {
        "STU0001": {"abilities": {"alpha": 3.0, "beta": -22.0}},
        "STU0002": {"abilities": {"alpha": -25.0, "beta": 1.0}},
        "STU0003": {"abilities": {"alpha": -9.0, "beta": 4.0}},
        "STU0004": {"abilities": {"alpha": 5.0, "beta": 6.0}},
    },
}


def _row(sid: str, label: str, cls: str) -> dict[str, str]:
    return {"student_id": sid, "competency_label": label, "classification": cls}


def test_planted_recall_against_truth_labels() -> None:
    rows = [
        _row("STU0001", "Beta", "persistent gap"),
        _row("STU0002", "Alpha", "isolated gap"),
        _row("STU0002", "Beta", "proficient"),
    ]
    scores = score_planted(_TRUTH, rows, labels_by_truth_competency(_TRUTH, None))
    assert scores["detected_any"] == 2
    assert scores["detected_persistent"] == 1
    assert scores["recall_persistent"] == 0.5
    assert scores["missed"] == []


def test_planted_recall_maps_through_llm_labels() -> None:
    llm = SiloClusteringResult.model_validate(
        {"clusters": [
            {"competency_label": "Thing One", "rationale": "", "members": [
                {"subject_code": "A", "silo_local_id": "SILO1"}, {"subject_code": "B", "silo_local_id": "SILO1"}]},
            {"competency_label": "Thing Two", "rationale": "", "members": [
                {"subject_code": "A", "silo_local_id": "SILO2"}, {"subject_code": "B", "silo_local_id": "SILO2"}]},
        ]}
    )
    label_map = labels_by_truth_competency(_TRUTH, llm)
    assert label_map == {"alpha": {"Thing One"}, "beta": {"Thing Two"}}
    rows = [_row("STU0001", "Thing Two", "persistent gap"), _row("STU0002", "Thing Two", "persistent gap")]
    scores = score_planted(_TRUTH, rows, label_map)
    assert scores["detected_persistent"] == 1 and scores["missed"] == ["STU0002"]


def test_unplanted_flags_checked_against_ability() -> None:
    rows = [
        _row("STU0003", "Alpha", "persistent gap"),  # alpha IS their weakest: consistent
        _row("STU0004", "Beta", "persistent gap"),   # beta is their strongest: not consistent
        _row("STU0001", "Beta", "persistent gap"),   # planted, ignored here
    ]
    scores = score_unplanted(_TRUTH, rows, labels_by_truth_competency(_TRUTH, None))
    assert scores["unplanted_flagged"] == 2
    assert scores["consistent_with_ability"] == 1


def test_clustering_pairwise_scores() -> None:
    # LLM merges everything into one cluster: recall 100%, precision 2/6.
    llm = SiloClusteringResult.model_validate(
        {"clusters": [{"competency_label": "All", "rationale": "", "members": [
            {"subject_code": s, "silo_local_id": i} for s in ("A", "B") for i in ("SILO1", "SILO2")]}]}
    )
    scores = score_clustering(_TRUTH, llm)
    assert scores["pair_recall"] == 1.0
    assert abs(scores["pair_precision"] - 2 / 6) < 1e-9
    assert scores["silos_uncovered"] == 0
