"""Generate a grounded learning plan for one student (S4-6).

    cd python
    conda activate lja
    python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx   # once, to cache the clustering
    python -m lja.plan ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx S001

A separate entry point rather than a flag on lja.cli on purpose: the
clustering is one cached LLM call shared by every student, while a plan is
one LLM call per student, and mixing the two into one command would make
"re-run the pipeline" silently re-spend a plan call. This command never
calls the LLM for clustering -- it requires the cache lja.cli wrote.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .data.excel_loader import load_dataset
from .llm.factory import get_llm_client
from .llm.grounding import GroundingError
from .model.gap_detection import GapThresholds, compute_gaps
from .model.learning_plan import build_plan_context, generate_learning_plan, render_markdown
from .model.silo_clustering import SiloClusteringResult


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LJA: generate a grounded learning plan for one student")
    parser.add_argument("excel_path", help="Path to the CSE_results_*.xlsx workbook")
    parser.add_argument("student_id", help="Student id exactly as it appears in the workbook, e.g. S001")
    parser.add_argument(
        "--clustering-cache",
        default="output/silo_clustering.json",
        help="The SILO clustering written by lja.cli (default: %(default)s). Required; never regenerated here",
    )
    parser.add_argument(
        "--out-dir",
        default="output/plans",
        help="Where learning_plan_<student>.json and .md are written (default: %(default)s)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Generation attempts before giving up on a plan that will not ground (default: %(default)s)",
    )
    parser.add_argument(
        "--extra-instructions",
        default=None,
        help="Extra text appended to the plan system prompt, for prompt experiments without editing code",
    )
    args = parser.parse_args(argv)

    cache_path = Path(args.clustering_cache)
    if not cache_path.exists():
        print(f"No clustering cache at {cache_path}. Run python -m lja.cli first.", file=sys.stderr)
        return 2

    dataset = load_dataset(args.excel_path)
    clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
    gaps = compute_gaps(dataset, clustering, thresholds=GapThresholds())

    try:
        context = build_plan_context(dataset, clustering, gaps, args.student_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        f"Context for {args.student_id}: {len(context.competencies)} competencies, "
        f"{len(context.known_silos)} SILOs, {len(context.assessments)} assessments."
    )

    client = get_llm_client()
    print(f"LLM: {client.describe()}")
    try:
        plan = generate_learning_plan(
            client, context, max_attempts=args.max_attempts, extra_instructions=args.extra_instructions
        )
    except GroundingError as exc:
        # Tender requirement 6: an ungrounded plan fails the build, it does
        # not get written out with a warning attached.
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(f"LLM usage: {client.usage_summary()}", file=sys.stderr)
        return 1
    print(f"LLM usage: {client.usage_summary()}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"learning_plan_{args.student_id}.json"
    md_path = out_dir / f"learning_plan_{args.student_id}.md"
    json_path.write_text(plan.model_dump_json(indent=2))
    markdown = render_markdown(plan, context)
    md_path.write_text(markdown)

    print()
    print(markdown)
    print(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
