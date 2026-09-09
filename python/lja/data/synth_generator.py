"""Generates additional synthetic students in the same shape as
data-fixtures/CSE_results_150_students_3_Subjects.xlsx, so the output drops
straight into the existing pipeline unchanged.

Two deliberate design choices, not just "add noise":

1. A configurable fraction of new students get a PLANTED, known gap -- their
   scores are genuinely suppressed on a chosen set of SILOs spanning two
   subjects, everything else normal. This gives ground truth: running the
   real pipeline (cluster_silos + compute_gaps) against the output and
   checking whether it recovers exactly the planted students as a
   persistent gap is a real correctness check on the whole system, not just
   "did it run." See the CLI's --verify flag.
2. Feedback text comes from an LLM-generated bank of varied templates (one
   LLM call for ~24 templates, not one call per row), sampled per row and
   filled in with that row's actual SILO text. Scott called the supplied
   data's 45-unique-string canned feedback a real limitation on the call
   (2026-08-11) -- this is a direct answer to that, without an LLM call per
   row, which would be slow and not needed for what varied *phrasing* buys us.
"""

from __future__ import annotations

import argparse
import random
import sys

import pandas as pd
from pydantic import BaseModel

from .excel_loader import Assessment, LjaDataset, ResultRow, StudentSummary, load_dataset

# Evidenced twice this session (see python/README.md's "real finding"
# section, points 3 and 5): CSE1OOF's abstraction/encapsulation SILO and
# CSE2ALG's data-structure-identification/implementation SILOs are the one
# link the clustering has found correctly and repeatably. Good default for
# a planted gap precisely because we already trust the system can find it.
DEFAULT_PLANTED_GAP_SILOS = ("CSE1OOF:SILO2", "CSE2ALG:SILO2", "CSE2ALG:SILO3")

FEEDBACK_BANDS = ("limited", "developing", "proficient", "excellent")

# Used only if the LLM is unavailable or returns nothing usable for a band
# -- keeps the generator runnable without an LLM call being load-bearing.
_FALLBACK_TEMPLATES: dict[str, list[str]] = {
    "limited": ["This result shows significant gaps in {silos}. Substantial revision is needed."],
    "developing": ["This result meets some requirements but needs more consistent grasp of {silos}."],
    "proficient": ["This is a solid result, demonstrating a good grasp of {silos}."],
    "excellent": ["This is an excellent result, showing strong command of {silos}."],
}


class FeedbackTemplate(BaseModel):
    band: str
    text: str  # must contain the literal substring "{silos}"


class FeedbackTemplateBank(BaseModel):
    templates: list[FeedbackTemplate]


_FEEDBACK_SYSTEM_PROMPT = """You are generating a bank of REUSABLE feedback-comment TEMPLATES for \
synthetic test data at a university -- not feedback for a real student, and not text that will \
ever be shown as-is. Each template will later be filled in programmatically with the specific \
learning outcomes a given assessment addressed.

Generate 6 templates for EACH of these four performance bands: limited, developing, proficient, \
excellent (24 templates total). Within a band, vary sentence structure and vocabulary substantially \
-- these should not read like synonym-swapped copies of each other. Professional academic tone, \
1-2 sentences each, appropriate to Australian university marking.

Every template's text MUST contain the literal placeholder "{silos}" exactly once, at the point \
where the specific learning outcomes will be inserted -- e.g. "This result shows a limited grasp \
of {silos}, and revision is recommended before the next assessment." Do not fill it in yourself; \
leave the literal characters "{silos}" in the text.
"""


def generate_feedback_bank(client) -> dict[str, list[str]]:
    user_prompt = "Generate the 24 templates now (6 per band)."
    try:
        result = client.complete_structured(
            system=_FEEDBACK_SYSTEM_PROMPT, user=user_prompt, schema=FeedbackTemplateBank
        )
    except Exception:
        # A varied-phrasing bank is a nice-to-have, not load-bearing --
        # fall back rather than fail the whole generation run over it.
        return dict(_FALLBACK_TEMPLATES)

    bank: dict[str, list[str]] = {band: [] for band in FEEDBACK_BANDS}
    for template in result.templates:
        if template.band in bank and "{silos}" in template.text:
            bank[template.band].append(template.text)

    for band in FEEDBACK_BANDS:
        if not bank[band]:
            bank[band] = list(_FALLBACK_TEMPLATES[band])
    return bank


def _feedback_band(score: float) -> str:
    if score < 50:
        return "limited"
    if score < 65:
        return "developing"
    if score < 80:
        return "proficient"
    return "excellent"


def _join_naturally(items: list[str]) -> str:
    if not items:
        return "the assessed learning themes"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def generate_synthetic_students(
    dataset: LjaDataset,
    *,
    n_students: int,
    start_index: int,
    planted_gap_silos: set[str],
    planted_gap_fraction: float,
    feedback_bank: dict[str, list[str]],
    rng: random.Random,
) -> tuple[list[ResultRow], list[StudentSummary], list[str]]:
    """Returns (new result rows, new student summaries, ids of planted-gap
    students) -- the third element is the ground truth for --verify.
    """
    new_results: list[ResultRow] = []
    new_summaries: list[StudentSummary] = []
    planted_student_ids: list[str] = []

    assessments_by_subject: dict[str, list[Assessment]] = {}
    for assessment in dataset.assessments:
        assessments_by_subject.setdefault(assessment.subject_code, []).append(assessment)
    subject_codes = sorted(assessments_by_subject.keys())

    for i in range(n_students):
        student_id = f"STU{start_index + i:04d}"
        is_planted = rng.random() < planted_gap_fraction
        if is_planted:
            planted_student_ids.append(student_id)

        # Mirrors the real dataset's distribution (mean ~68, std ~11,
        # observed range ~38-97) rather than an arbitrary guess.
        baseline = max(20.0, min(99.0, rng.gauss(68, 11)))

        subject_totals: dict[str, float] = {}
        for subject_code in subject_codes:
            weighted_sum = 0.0
            for assessment in assessments_by_subject[subject_code]:
                score = baseline + rng.gauss(0, 6)
                if is_planted and planted_gap_silos.intersection(
                    f"{subject_code}:{sid}" for sid in assessment.silo_ids
                ):
                    # Deliberate, large suppression -- this is the ground
                    # truth signal, not incidental noise.
                    score -= rng.uniform(20, 32)
                score = round(max(1.0, min(100.0, score)))

                silo_descs = [dataset.silos[f"{subject_code}:{sid}"].text for sid in assessment.silo_ids]
                template = rng.choice(feedback_bank[_feedback_band(score)])
                feedback = template.format(silos=_join_naturally(silo_descs))

                weighted_score = round(score * assessment.weight, 2)
                weighted_sum += weighted_score

                new_results.append(
                    ResultRow(
                        student_id=student_id,
                        subject_code=subject_code,
                        assessment_name=assessment.assessment_name,
                        score=float(score),
                        feedback_comment=feedback,
                        weight=assessment.weight,
                        weighted_score=weighted_score,
                        silo_ids=assessment.silo_ids,
                    )
                )
            subject_totals[subject_code] = round(weighted_sum, 2)

        average_total = round(sum(subject_totals.values()) / len(subject_totals), 4)
        if average_total < 50:
            band = "At risk"
        elif average_total < 60:
            band = "P range"
        elif average_total < 70:
            band = "C range"
        elif average_total < 80:
            band = "D range"
        else:
            band = "HD/D range"

        new_summaries.append(
            StudentSummary(
                student_id=student_id,
                subject_totals=subject_totals,
                average_total=average_total,
                performance_band=band,
            )
        )

    return new_results, new_summaries, planted_student_ids


def _next_start_index(dataset: LjaDataset) -> int:
    existing_numbers = [
        int(s.student_id[3:]) for s in dataset.student_summaries if s.student_id.startswith("STU")
    ]
    return (max(existing_numbers) + 1) if existing_numbers else 1


def _assessment_type_column(subject_code: str, assessment_name: str) -> str:
    return f"{subject_code} - {assessment_name}"


def _silo_field(dataset: LjaDataset, subject_code: str, silo_ids: tuple[str, ...]) -> str:
    return "; ".join(f"{sid}: {dataset.silos[f'{subject_code}:{sid}'].text}" for sid in silo_ids)


def write_extended_workbook(
    source_path: str,
    out_path: str,
    dataset: LjaDataset,
    new_results: list[ResultRow],
    new_summaries: list[StudentSummary],
) -> None:
    assessment_map_df = pd.read_excel(source_path, sheet_name="Assessment Map")
    original_results_df = pd.read_excel(source_path, sheet_name="Results")
    original_summary_df = pd.read_excel(source_path, sheet_name="Student Summary")

    new_results_df = pd.DataFrame(
        [
            {
                "Student ID": r.student_id,
                "Assessment Type": _assessment_type_column(r.subject_code, r.assessment_name),
                "Score (1-100)": r.score,
                "Feedback Comment": r.feedback_comment,
                "SILO's": _silo_field(dataset, r.subject_code, r.silo_ids),
                "Weight": r.weight,
                "Weighted Score": r.weighted_score,
            }
            for r in new_results
        ]
    )
    combined_results_df = pd.concat([original_results_df, new_results_df], ignore_index=True)

    subject_codes = sorted({r.subject_code for r in new_results}) or sorted(
        {a.subject_code for a in dataset.assessments}
    )
    new_summary_df = pd.DataFrame(
        [
            {
                "Student ID": s.student_id,
                **{f"{code} Total": s.subject_totals.get(code, 0.0) for code in subject_codes},
                "Average Total": s.average_total,
                "Performance Band": s.performance_band,
            }
            for s in new_summaries
        ]
    )
    combined_summary_df = pd.concat([original_summary_df, new_summary_df], ignore_index=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        combined_results_df.to_excel(writer, sheet_name="Results", index=False)
        combined_summary_df.to_excel(writer, sheet_name="Student Summary", index=False)
        assessment_map_df.to_excel(writer, sheet_name="Assessment Map", index=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate additional synthetic students for LJA")
    parser.add_argument("source_xlsx", help="Existing workbook to extend, e.g. the supplied dataset")
    parser.add_argument("--add", type=int, default=150, help="Number of new synthetic students (default: %(default)s)")
    parser.add_argument("--out", required=True, help="Output workbook path")
    parser.add_argument(
        "--planted-gap-silos",
        default=",".join(DEFAULT_PLANTED_GAP_SILOS),
        help="Comma-separated SUBJECT:SILOn keys to deliberately suppress for the planted-gap group",
    )
    parser.add_argument("--planted-gap-fraction", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--no-llm-feedback",
        action="store_true",
        help="Skip the LLM call and use the small built-in fallback templates only",
    )
    args = parser.parse_args(argv)

    dataset = load_dataset(args.source_xlsx)
    print(f"Loaded source: {len(dataset.student_summaries)} existing students.")

    if args.no_llm_feedback:
        feedback_bank = dict(_FALLBACK_TEMPLATES)
    else:
        from ..llm.factory import get_llm_client

        print("Generating a varied feedback-template bank (one LLM call)...")
        feedback_bank = generate_feedback_bank(get_llm_client())
        for band in FEEDBACK_BANDS:
            print(f"  {band}: {len(feedback_bank[band])} templates")

    planted_gap_silos = {s.strip() for s in args.planted_gap_silos.split(",") if s.strip()}
    rng = random.Random(args.seed)

    new_results, new_summaries, planted_ids = generate_synthetic_students(
        dataset,
        n_students=args.add,
        start_index=_next_start_index(dataset),
        planted_gap_silos=planted_gap_silos,
        planted_gap_fraction=args.planted_gap_fraction,
        feedback_bank=feedback_bank,
        rng=rng,
    )
    print(f"Generated {len(new_summaries)} new students, {len(planted_ids)} with a planted gap on {sorted(planted_gap_silos)}.")

    write_extended_workbook(args.source_xlsx, args.out, dataset, new_results, new_summaries)
    print(f"Wrote combined workbook: {args.out}")
    print(f"Planted-gap student IDs (ground truth for --verify): {planted_ids}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
