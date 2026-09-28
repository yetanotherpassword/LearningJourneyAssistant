"""Generate a grounded study strategy for one student (IOLG-123).

    cd python
    conda activate lja
    python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx   # once, to cache the clustering
    python -m lja.strategy ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx S001
    python -m lja.strategy --source moodle 12345

A learning plan (python -m lja.plan) says what to work on; a study strategy
says how to study it, one entry per gap. Same inputs, same staff-review gate
and same fail-closed grounding as lja.plan, and like it this command never
calls the LLM for clustering -- it requires the cache lja.cli wrote.

Exit codes: 0 written (or the student has no gap, so nothing is needed),
1 the strategy never passed grounding, 2 bad input or a rejected cluster.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .data.loading import add_source_arguments, clustering_cache_path, load_dataset_for_source
from .llm.factory import get_llm_client
from .llm.grounding import GroundingError
from .model.gap_detection import GapThresholds, compute_gaps
from .model.learning_plan import build_plan_context
from .model.silo_clustering import SiloClusteringResult
from .model.study_strategy import gap_competencies, generate_study_strategy, has_gaps, render_markdown
from .review import current_reviews, default_review_path, load_or_create_reviews


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LJA: generate a grounded study strategy for one student")
    parser.add_argument("excel_path", nargs="?", help="Path to the CSE_results_*.xlsx workbook (required for --source excel)")
    parser.add_argument("student_id", help="Student id exactly as it appears in the dataset")
    add_source_arguments(parser)
    parser.add_argument(
        "--clustering-cache",
        default=None,
        help="The SILO clustering written by lja.cli (default: the source's cache under output/). Never regenerated here",
    )
    parser.add_argument("--review-file", default=None, help="Staff-review JSON file (default: .review.json beside the cache)")
    parser.add_argument(
        "--out-dir",
        default="output/strategies",
        help="Where study_strategy_<student>.json and .md are written (default: %(default)s)",
    )
    parser.add_argument("--max-attempts", type=int, default=3, help="Generation attempts before giving up (default: %(default)s)")
    parser.add_argument("--extra-instructions", default=None, help="Extra text appended to the system prompt, for prompt experiments")
    args = parser.parse_args(argv)

    cache_path = Path(clustering_cache_path(args.source, args.clustering_cache))
    if not cache_path.exists():
        print(f"No clustering cache at {cache_path}. Run python -m lja.cli --source {args.source} first.", file=sys.stderr)
        return 2

    dataset = load_dataset_for_source(args.source, args.excel_path, args.mapping, parser=parser)
    clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
    gaps = compute_gaps(dataset, clustering, thresholds=GapThresholds())

    # Same gate as lja.plan (IOLG-108): a rejected cluster blocks, a pending
    # one warns. Only the clusters this student's evidence uses matter.
    review_path = Path(args.review_file) if args.review_file else default_review_path(cache_path)
    review_store = load_or_create_reviews(clustering, review_path)
    student_competencies = {g.competency_label for g in gaps if g.student_id == args.student_id}
    relevant = [r for r in current_reviews(clustering, review_store) if r.competency_label in student_competencies]
    rejected = [r.competency_label for r in relevant if r.state == "rejected"]
    pending = [r.competency_label for r in relevant if r.state == "pending"]
    if rejected:
        print(f"Cannot generate study strategy: rejected clustering used by this student: {', '.join(rejected)}.", file=sys.stderr)
        return 2
    if pending:
        print(f"WARNING: study strategy uses unreviewed clustering: {', '.join(pending)}.", file=sys.stderr)

    try:
        context = build_plan_context(dataset, clustering, gaps, args.student_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not has_gaps(context):
        print(f"{args.student_id} has no isolated or persistent gap, so no study strategy is needed.")
        return 0
    targets = gap_competencies(context)
    print(
        f"Context for {args.student_id}: {len(targets)} gap(s) to address "
        f"({', '.join(f'{c.competency_label} [{c.classification}]' for c in targets)}), "
        f"{len(context.assessments)} assessments."
    )

    client = get_llm_client()
    print(f"LLM: {client.describe()}")
    try:
        strategy = generate_study_strategy(
            client, context, max_attempts=args.max_attempts, extra_instructions=args.extra_instructions
        )
    except GroundingError as exc:
        # Tender requirement 6: an ungrounded strategy fails, it is not written out.
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(f"LLM usage: {client.usage_summary()}", file=sys.stderr)
        return 1
    print(f"LLM usage: {client.usage_summary()}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"study_strategy_{args.student_id}.json"
    md_path = out_dir / f"study_strategy_{args.student_id}.md"
    json_path.write_text(strategy.model_dump_json(indent=2))
    markdown = render_markdown(strategy, context)
    md_path.write_text(markdown)

    print()
    print(markdown)
    print(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
