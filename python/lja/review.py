"""Staff confirmation gate for LLM-generated SILO competency clusters.

The LLM clustering cache is regenerable. Staff review decisions are not, so
review decisions are stored in a separate JSON file beside the clustering cache.

Typical use:
    cd python
    python -m lja.review

The main pipeline reads the same review file and blocks gap generation when
clusters are rejected, or when clusters are still pending unless the caller
explicitly passes --allow-unconfirmed.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .model.silo_clustering import CompetencyCluster, SiloClusteringResult

ReviewState = Literal["pending", "confirmed", "rejected"]


class ClusterReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    competency_label: str
    members: list[str]
    state: ReviewState = "pending"
    note: str = ""


class ReviewStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    reviews: dict[str, ClusterReview] = Field(default_factory=dict)


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "rejected"},
    "confirmed": {"pending"},
    "rejected": {"pending"},
}


def cluster_members(cluster: CompetencyCluster) -> list[str]:
    """Return a deterministic, human-readable member list."""
    return sorted(f"{m.subject_code}:{m.silo_local_id}" for m in cluster.members)


def cluster_id(cluster: CompetencyCluster) -> str:
    """Stable id based on cluster membership, not the LLM-generated label."""
    canonical = "|".join(cluster_members(cluster))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def default_review_path(clustering_path: Path) -> Path:
    """Store staff decisions beside the clustering cache."""
    return clustering_path.with_name(f"{clustering_path.stem}.review.json")


def save_reviews(store: ReviewStore, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(store.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_or_create_reviews(
    clustering: SiloClusteringResult,
    path: Path,
) -> ReviewStore:
    """Load staff decisions and add pending records for unseen clusters.

    Old review records are retained even when a later clustering run no longer
    contains that cluster. That avoids destroying a human decision simply
    because the regenerable LLM cache changed. Gate checks only use clusters
    that exist in the current clustering result.
    """
    if path.exists():
        store = ReviewStore.model_validate_json(path.read_text(encoding="utf-8"))
    else:
        store = ReviewStore()

    changed = not path.exists()

    for cluster in clustering.clusters:
        cid = cluster_id(cluster)
        members = cluster_members(cluster)
        existing = store.reviews.get(cid)

        if existing is None:
            store.reviews[cid] = ClusterReview(
                cluster_id=cid,
                competency_label=cluster.competency_label,
                members=members,
            )
            changed = True
            continue

        if (
            existing.competency_label != cluster.competency_label
            or existing.members != members
        ):
            store.reviews[cid] = existing.model_copy(
                update={
                    "competency_label": cluster.competency_label,
                    "members": members,
                }
            )
            changed = True

    if changed:
        save_reviews(store, path)

    return store


def current_reviews(
    clustering: SiloClusteringResult,
    store: ReviewStore,
) -> list[ClusterReview]:
    """Return review records for the clusters in the current LLM output."""
    return [store.reviews[cluster_id(cluster)] for cluster in clustering.clusters]


def set_review_state(
    store: ReviewStore,
    cid: str,
    state: ReviewState,
    *,
    note: str | None = None,
) -> ClusterReview:
    """Apply one explicit review-state transition.

    Direct confirmed<->rejected transitions are intentionally disallowed.
    A reviewer resets the cluster to pending first, making re-review visible.
    """
    if cid not in store.reviews:
        raise KeyError(f"Unknown cluster id: {cid}")

    current = store.reviews[cid]

    if state != current.state and state not in _ALLOWED_TRANSITIONS[current.state]:
        raise ValueError(
            f"Invalid review transition {current.state!r} -> {state!r}. "
            "Reset the cluster to 'pending' before changing a settled decision."
        )

    new_note = current.note if note is None else note.strip()
    if state == "rejected" and not new_note:
        raise ValueError("A rejected cluster requires a note explaining the rework needed.")

    updated = current.model_copy(update={"state": state, "note": new_note})
    store.reviews[cid] = updated
    return updated


def gate_status(
    clustering: SiloClusteringResult,
    store: ReviewStore,
) -> tuple[list[ClusterReview], list[ClusterReview]]:
    """Return (pending, rejected) reviews for the current clustering."""
    reviews = current_reviews(clustering, store)
    pending = [r for r in reviews if r.state == "pending"]
    rejected = [r for r in reviews if r.state == "rejected"]
    return pending, rejected


def rework_instructions(review: ClusterReview) -> str:
    note = review.note or "(no note supplied)"
    return (
        f"Rejected cluster: {review.competency_label} [{review.cluster_id}]\n"
        f"Staff note: {note}\n"
        "Rework path:\n"
        "  1. Use the staff note to refine the clustering instructions.\n"
        "  2. Regenerate clustering with --refresh-clustering and, where useful,\n"
        "     --extra-instructions \"<staff feedback>\".\n"
        "  3. Run `python -m lja.review` again and review the regenerated cluster.\n"
        "  4. If membership is unchanged, explicitly reset this cluster to pending before re-reviewing it."
    )


def _resolve_cluster_id(store: ReviewStore, value: str) -> str:
    """Accept an exact id or a unique id prefix for interactive convenience."""
    if value in store.reviews:
        return value

    matches = [cid for cid in store.reviews if cid.startswith(value)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(f"No cluster id matches {value!r}.")
    raise KeyError(f"Cluster id prefix {value!r} is ambiguous: {matches}")


def _print_reviews(
    clustering: SiloClusteringResult,
    store: ReviewStore,
) -> None:
    print("\nLLM SILO competency clusters:")
    for review in current_reviews(clustering, store):
        print(f"\n[{review.cluster_id}] {review.competency_label}")
        print(f"  Members: {', '.join(review.members)}")
        print(f"  State:   {review.state}")
        if review.note:
            print(f"  Note:    {review.note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review LLM-generated SILO competency clusters."
    )
    parser.add_argument(
        "--clustering-cache",
        default="output/silo_clustering.json",
        help="LLM clustering cache to review (default: %(default)s)",
    )
    parser.add_argument(
        "--review-file",
        default=None,
        help=(
            "Staff-review JSON file. Defaults to a .review.json file beside "
            "the clustering cache."
        ),
    )
    parser.add_argument(
        "--cluster",
        default=None,
        help="Cluster id (or unique id prefix) to update.",
    )
    parser.add_argument(
        "--state",
        choices=["pending", "confirmed", "rejected"],
        default=None,
        help="New review state. Use with --cluster.",
    )
    parser.add_argument(
        "--note",
        default=None,
        help="Staff review note. Required when rejecting a cluster.",
    )
    args = parser.parse_args(argv)

    clustering_path = Path(args.clustering_cache)
    if not clustering_path.exists():
        print(
            f"Clustering cache not found: {clustering_path}\n"
            "Run `python -m lja.cli <dataset.xlsx> --allow-unconfirmed` once "
            "to create the LLM clustering cache, then review it.",
            file=sys.stderr,
        )
        return 2

    clustering = SiloClusteringResult.model_validate_json(
        clustering_path.read_text(encoding="utf-8")
    )
    review_path = (
        Path(args.review_file)
        if args.review_file
        else default_review_path(clustering_path)
    )
    store = load_or_create_reviews(clustering, review_path)

    if (args.cluster is None) != (args.state is None):
        parser.error("--cluster and --state must be supplied together.")

    if args.cluster is not None and args.state is not None:
        try:
            cid = _resolve_cluster_id(store, args.cluster)
            updated = set_review_state(
                store,
                cid,
                args.state,
                note=args.note,
            )
        except (KeyError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

        save_reviews(store, review_path)
        print(
            f"Updated {updated.competency_label} [{updated.cluster_id}] "
            f"to {updated.state}."
        )
        if updated.state == "rejected":
            print("\n" + rework_instructions(updated))

    _print_reviews(clustering, store)
    print(f"\nReview decisions: {review_path}")

    if args.cluster is None and sys.stdin.isatty():
        raw_id = input("\nCluster id to review (Enter to finish): ").strip()
        if raw_id:
            raw_state = input(
                "State [pending/confirmed/rejected]: "
            ).strip().lower()
            if raw_state not in {"pending", "confirmed", "rejected"}:
                print("Invalid state.", file=sys.stderr)
                return 2
            note = input("Staff note (required for rejected): ").strip()

            try:
                cid = _resolve_cluster_id(store, raw_id)
                updated = set_review_state(
                    store,
                    cid,
                    raw_state,  # type: ignore[arg-type]
                    note=note,
                )
            except (KeyError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2

            save_reviews(store, review_path)
            print(
                f"Updated {updated.competency_label} [{updated.cluster_id}] "
                f"to {updated.state}."
            )
            if updated.state == "rejected":
                print("\n" + rework_instructions(updated))

    return 0


if __name__ == "__main__":
    sys.exit(main())
