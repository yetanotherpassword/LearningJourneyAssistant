from __future__ import annotations

import pytest

from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef
from lja.review import (
    cluster_id,
    gate_status,
    load_or_create_reviews,
    save_reviews,
    set_review_state,
)


def _clustering() -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Programming Design",
                rationale="Shared design competency.",
                members=[
                    SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1"),
                    SiloRef(subject_code="CSE3CAP", silo_local_id="SILO2"),
                ],
            ),
            CompetencyCluster(
                competency_label="Technical Communication",
                rationale="Shared communication competency.",
                members=[
                    SiloRef(subject_code="CSE3CAP", silo_local_id="SILO3"),
                ],
            ),
        ]
    )


def _store(tmp_path):
    clustering = _clustering()
    path = tmp_path / "silo_clustering.review.json"
    store = load_or_create_reviews(clustering, path)
    return clustering, path, store


def test_new_clusters_start_pending(tmp_path) -> None:
    clustering, path, store = _store(tmp_path)

    assert path.exists()
    assert len(store.reviews) == 2
    assert all(review.state == "pending" for review in store.reviews.values())

    pending, rejected = gate_status(clustering, store)
    assert len(pending) == 2
    assert rejected == []


def test_pending_to_confirmed(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    updated = set_review_state(store, cid, "confirmed", note="Reviewed by staff.")

    assert updated.state == "confirmed"
    assert updated.note == "Reviewed by staff."


def test_pending_to_rejected_requires_rework_note(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    with pytest.raises(ValueError, match="requires a note"):
        set_review_state(store, cid, "rejected")

    updated = set_review_state(
        store,
        cid,
        "rejected",
        note="These SILOs describe different competencies; split the cluster.",
    )
    assert updated.state == "rejected"
    assert "split" in updated.note


def test_confirmed_can_be_reset_to_pending_for_rereview(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    set_review_state(store, cid, "confirmed", note="First review.")
    updated = set_review_state(
        store,
        cid,
        "pending",
        note="Re-review after clustering change.",
    )

    assert updated.state == "pending"
    assert updated.note == "Re-review after clustering change."


def test_rejected_can_be_reset_to_pending_after_rework(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    set_review_state(store, cid, "rejected", note="Split this cluster.")
    updated = set_review_state(
        store,
        cid,
        "pending",
        note="Regenerated and ready for review.",
    )

    assert updated.state == "pending"


def test_settled_decision_cannot_flip_directly(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    set_review_state(store, cid, "confirmed", note="Accepted.")

    with pytest.raises(ValueError, match="Reset the cluster to 'pending'"):
        set_review_state(
            store,
            cid,
            "rejected",
            note="Changed my mind.",
        )


def test_review_state_and_note_survive_save_and_reload(tmp_path) -> None:
    clustering, path, store = _store(tmp_path)
    cid = cluster_id(clustering.clusters[0])

    set_review_state(
        store,
        cid,
        "confirmed",
        note="Staff checked the SILO members.",
    )
    save_reviews(store, path)

    reloaded = load_or_create_reviews(clustering, path)

    assert reloaded.reviews[cid].state == "confirmed"
    assert reloaded.reviews[cid].note == "Staff checked the SILO members."


def test_gate_reports_pending_and_rejected_current_clusters(tmp_path) -> None:
    clustering, _path, store = _store(tmp_path)
    first = cluster_id(clustering.clusters[0])
    second = cluster_id(clustering.clusters[1])

    set_review_state(store, first, "confirmed", note="Accepted.")
    set_review_state(store, second, "rejected", note="Needs rework.")

    pending, rejected = gate_status(clustering, store)

    assert pending == []
    assert [r.cluster_id for r in rejected] == [second]
