"""Generate a grounded practice quiz for one student (tender R8, adaptive quiz).

    python -m lja.quiz ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx STU0003

Same inputs and gate as lja.plan and lja.strategy: the clustering cache
lja.cli wrote, the staff-review file beside it, the gap engine's output for
this student. Adds one optional input, the subject catalogue
(--catalogue), for subject titles and handbook synopses; without it the
quiz still generates, with codes only.

Writes output/quizzes/quiz_<student>.json and .md. The dashboard's student
page renders the JSON if it is present. A quiz that never grounds is not
written (exit 1); a student with no gap gets no quiz and no LLM call.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .data.catalogue import load_catalogue
from .data.loading import add_source_arguments, clustering_cache_path, load_dataset_for_source
from .llm.factory import get_llm_client
from .llm.grounding import GroundingError
from .model.gap_detection import GapThresholds, compute_gaps
from .model.learning_plan import build_plan_context
from .model.quiz import (
    DEFAULT_FORMAT,
    DEFAULT_ITEMS_PER_GAP,
    QuizDocument,
    SubjectInfo,
    build_quiz_context,
    generate_quiz,
    has_gaps,
    render_markdown,
    review_quiz,
)
from .model.silo_clustering import SiloClusteringResult
from .model.study_strategy import gap_competencies
from .review import current_reviews, default_review_path, load_or_create_reviews


def load_subject_info(path: str | Path | None) -> dict[str, SubjectInfo]:
    """Subject title, year level and synopsis from the catalogue, keyed by
    code. An absent or unreadable catalogue gives an empty map: the quiz
    then carries codes only and the page says no synopsis is available."""
    if path is None:
        return {}
    catalogue_path = Path(path)
    if not catalogue_path.exists():
        return {}
    catalogue = load_catalogue(catalogue_path)
    return {
        s.code: SubjectInfo(code=s.code, title=s.title, year_level=s.year_level, synopsis=s.description)
        for s in catalogue.subjects
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LJA: generate a grounded practice quiz for one student")
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
        "--catalogue",
        default=config.QUIZ_CATALOGUE_PATH,
        help="Subject catalogue YAML for titles and handbook synopses (default: %(default)s; skipped if missing)",
    )
    parser.add_argument(
        "--out-dir",
        default="output/quizzes",
        help="Where quiz_<student>.json and .md are written (default: %(default)s)",
    )
    parser.add_argument(
        "--items-per-gap",
        type=int,
        default=DEFAULT_ITEMS_PER_GAP,
        help="Questions per gap competency (default: %(default)s)",
    )
    parser.add_argument(
        "--format",
        choices=["multiple_choice", "written", "mixed"],
        default=DEFAULT_FORMAT,
        help="Question format policy. mixed lets the model choose per question, except that a SILO that asks the "
        "student to do something (implement, design, evaluate...) must get a written task (default: %(default)s)",
    )
    parser.add_argument("--max-attempts", type=int, default=3, help="Generation attempts before giving up (default: %(default)s)")
    parser.add_argument("--extra-instructions", default=None, help="Extra text appended to the system prompt, for prompt experiments")
    parser.add_argument(
        "--skip-educator-review",
        action="store_true",
        help="Do not run the blind second pass that answers each question without the key and writes the educator notes",
    )
    args = parser.parse_args(argv)

    cache_path = Path(clustering_cache_path(args.source, args.clustering_cache))
    if not cache_path.exists():
        print(f"No clustering cache at {cache_path}. Run python -m lja.cli --source {args.source} first.", file=sys.stderr)
        return 2

    dataset = load_dataset_for_source(args.source, args.excel_path, args.mapping, parser=parser)
    clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
    gaps = compute_gaps(dataset, clustering, thresholds=GapThresholds())

    # Same gate as lja.plan and lja.strategy: a rejected cluster blocks, a
    # pending one warns. Only the clusters this student's evidence uses matter.
    review_path = Path(args.review_file) if args.review_file else default_review_path(cache_path)
    review_store = load_or_create_reviews(clustering, review_path)
    student_competencies = {g.competency_label for g in gaps if g.student_id == args.student_id}
    relevant = [r for r in current_reviews(clustering, review_store) if r.competency_label in student_competencies]
    rejected = [r.competency_label for r in relevant if r.state == "rejected"]
    pending = [r.competency_label for r in relevant if r.state == "pending"]
    if rejected:
        print(f"Cannot generate quiz: rejected clustering used by this student: {', '.join(rejected)}.", file=sys.stderr)
        return 2
    if pending:
        print(f"WARNING: quiz uses unreviewed clustering: {', '.join(pending)}.", file=sys.stderr)

    try:
        plan_context = build_plan_context(dataset, clustering, gaps, args.student_id)
        context = build_quiz_context(
            plan_context, load_subject_info(args.catalogue), items_per_gap=args.items_per_gap, format=args.format
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not has_gaps(context):
        print(f"{args.student_id} has no isolated or persistent gap, so no quiz is needed.")
        return 0
    targets = gap_competencies(plan_context)
    with_synopsis = sum(1 for s in context.subjects if s.synopsis)
    print(
        f"Context for {args.student_id}: {len(targets)} gap(s) to quiz "
        f"({', '.join(f'{c.competency_label} [{c.classification}]' for c in targets)}), "
        f"{len(plan_context.assessments)} assessments, {with_synopsis}/{len(context.subjects)} subjects with a synopsis."
    )

    client = get_llm_client()
    print(f"LLM: {client.describe()}")
    try:
        quiz = generate_quiz(client, context, max_attempts=args.max_attempts, extra_instructions=args.extra_instructions)
    except GroundingError as exc:
        # Tender requirement 6: an ungrounded quiz fails, it is not written out.
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(f"LLM usage: {client.usage_summary()}", file=sys.stderr)
        return 1
    print(f"LLM usage: {client.usage_summary()}")

    document = QuizDocument.from_quiz(quiz, context)
    if not args.skip_educator_review:
        # Blind second pass. A review that never grounds is reported, not
        # fatal: the quiz is still grounded, it just has no educator notes.
        try:
            review = review_quiz(client, document, context, max_attempts=args.max_attempts)
        except GroundingError as exc:
            print(f"\nWARNING: educator review not written: {exc}", file=sys.stderr)
        else:
            document = document.model_copy(update={"educator_review": review})
            disagree = document.disagreements
            if disagree:
                print(f"Blind check DISAGREES with the answer key on question(s) {', '.join(str(i + 1) for i in disagree)}.")
            else:
                print("Blind check agrees with the author on every question.")
        print(f"LLM usage: {client.usage_summary()}")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"quiz_{args.student_id}.json"
    md_path = out_dir / f"quiz_{args.student_id}.md"
    json_path.write_text(document.model_dump_json(indent=2))
    markdown = render_markdown(document, context)
    md_path.write_text(markdown)

    print()
    print(markdown)
    print(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
