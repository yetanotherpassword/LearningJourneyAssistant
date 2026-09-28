"""Sprint 5 grounding audit for IOLG-121.

Generates learning plans for a fixed set of ten students, records every
grounding-validation attempt, and writes the plan/evidence pairs needed for
independent human review.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .data.excel_loader import load_dataset
from .llm.base import LLMClient
from .llm.factory import get_llm_client
from .llm.grounding import GroundingError
from .model.gap_detection import GapThresholds, compute_gaps
from .model.learning_plan import (
    LearningPlan,
    PlanContext,
    build_plan_context,
    generate_learning_plan,
    render_markdown,
    validate_plan,
)
from .model.silo_clustering import SiloClusteringResult
from .review import ReviewStore, current_reviews

T = TypeVar("T", bound=BaseModel)

DEFAULT_STUDENTS = [
    "STU0003",
    "STU0004",
    "STU0022",
    "STU0054",
    "STU0055",
    "STU0067",
    "STU0075",
    "STU0001",
    "STU0005",
    "STU0007",
]


class AuditingClient:
    """Wrap an LLM client and record the grounding result of every plan attempt."""

    def __init__(self, inner: LLMClient, context: PlanContext) -> None:
        self.inner = inner
        self.context = context
        self.attempts: list[dict[str, object]] = []

    def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        result = self.inner.complete_structured(
            system=system,
            user=user,
            schema=schema,
        )

        if isinstance(result, LearningPlan):
            attempt_number = len(self.attempts) + 1
            try:
                validate_plan(result, self.context)
            except GroundingError as exc:
                self.attempts.append(
                    {
                        "attempt": attempt_number,
                        "result": "FAIL",
                        "failed_checks": str(exc),
                    }
                )
            else:
                self.attempts.append(
                    {
                        "attempt": attempt_number,
                        "result": "PASS",
                        "failed_checks": "",
                    }
                )

        return result

    def describe(self) -> str:
        return self.inner.describe()

    def usage_summary(self) -> str:
        return self.inner.usage_summary()


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the fixed ten-student grounding audit for IOLG-121."
    )
    parser.add_argument("dataset")
    parser.add_argument("--clustering-cache", required=True)
    parser.add_argument("--review-file", required=True)
    parser.add_argument(
        "--students",
        nargs="+",
        default=DEFAULT_STUDENTS,
        help="Student ids to audit (default: fixed Sprint 5 set of ten).",
    )
    parser.add_argument(
        "--out-dir",
        default="../docs/sprints/sprint-5/grounding-audit",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    plans_dir = out_dir / "plans"
    evidence_dir = out_dir / "evidence"
    plans_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset(args.dataset)

    clustering_path = Path(args.clustering_cache)
    clustering = SiloClusteringResult.model_validate_json(
        clustering_path.read_text(encoding="utf-8")
    )

    review_path = Path(args.review_file)
    review_store = ReviewStore.model_validate_json(
        review_path.read_text(encoding="utf-8")
    )
    reviews = current_reviews(clustering, review_store)
    not_confirmed = [r for r in reviews if r.state != "confirmed"]
    if not_confirmed:
        labels = ", ".join(
            f"{r.competency_label} ({r.state})" for r in not_confirmed
        )
        raise RuntimeError(
            f"Audit requires confirmed reference clustering; found: {labels}"
        )

    gaps = compute_gaps(dataset, clustering, thresholds=GapThresholds())

    rows: list[dict[str, object]] = []
    model_description = ""

    for student_id in args.students:
        print(f"\n=== {student_id} ===")

        context = build_plan_context(
            dataset,
            clustering,
            gaps,
            student_id,
        )

        evidence_path = evidence_dir / f"evidence_{student_id}.json"
        evidence_path.write_text(
            json.dumps(asdict(context), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        base_client = get_llm_client()
        client = AuditingClient(base_client, context)
        model_description = client.describe()
        print(f"LLM: {model_description}")

        final_result = "FAIL"
        final_error = ""

        try:
            plan = generate_learning_plan(
                client,
                context,
                max_attempts=args.max_attempts,
            )
            validate_plan(plan, context)

            json_path = plans_dir / f"learning_plan_{student_id}.json"
            md_path = plans_dir / f"learning_plan_{student_id}.md"

            json_path.write_text(
                plan.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            md_path.write_text(
                render_markdown(plan, context).rstrip() + "\n",
                encoding="utf-8",
            )

            final_result = "PASS"
        except Exception as exc:
            final_error = f"{type(exc).__name__}: {exc}"

        failed_attempts = [
            a for a in client.attempts if a["result"] == "FAIL"
        ]
        failed_checks = " | ".join(
            f"attempt {a['attempt']}: {a['failed_checks']}"
            for a in failed_attempts
        )

        rows.append(
            {
                "student_id": student_id,
                "attempts": len(client.attempts),
                "failed_attempts": len(failed_attempts),
                "failed_checks": failed_checks or "None",
                "final_grounding": final_result,
                "final_error": final_error,
                "usage": client.usage_summary(),
            }
        )

        print(
            f"{student_id}: {final_result}; "
            f"attempts={len(client.attempts)}; "
            f"failed_attempts={len(failed_attempts)}"
        )
        print(f"Usage: {client.usage_summary()}")

    csv_path = out_dir / "machine-audit.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            lineterminator="\n",
            fieldnames=[
                "student_id",
                "attempts",
                "failed_attempts",
                "failed_checks",
                "final_grounding",
                "final_error",
                "usage",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "audit": "IOLG-121 grounding audit",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "dataset": args.dataset,
        "clustering_cache": args.clustering_cache,
        "review_file": args.review_file,
        "model": model_description,
        "max_attempts": args.max_attempts,
        "students": args.students,
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    passed = sum(row["final_grounding"] == "PASS" for row in rows)
    print(f"\nMachine audit complete: {passed}/{len(rows)} plans passed.")
    print(f"Wrote {csv_path}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
