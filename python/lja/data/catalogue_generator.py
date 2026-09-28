"""Generate a complete synthetic cohort -- workbook, ground truth, and
optionally the Moodle-side fixtures -- from a subject catalogue (IOLG-113).

    cd python
    python -m lja.data.catalogue_generator ../data-fixtures/subject_catalogue.yaml \
        --students 500 --out ../data-fixtures/CSE_results_catalogue_500_synthetic.xlsx \
        --moodle-out ../data-fixtures/moodle-generated

How this differs from synth_generator.py, which EXTENDS the supplied
workbook with more students of the same three subjects:

1. Subjects, SILOs and assessments come from the catalogue, so the cohort
   can cover 12 subjects or 40. The workbook it writes has the same three
   sheets and columns as the supplied one and loads through
   excel_loader.load_dataset() unchanged.
2. Every student carries a hidden ABILITY per competency, not just one
   baseline. The supplied data (and synth_generator's copy of it) is a
   single per-student baseline plus independent noise, which is why the
   relative gap detector sees near-flat profiles there (config.py's
   GAP_MIN_SPREAD note, docs/adr/0001). Here a student who is weak at
   "abstraction" is weak at it in every subject that assesses it -- which
   is the thing the product is supposed to find.
3. Ground truth is written beside the workbook: which students were given a
   planted gap and in which competency, every student's ability vector, and
   the catalogue's competency clustering in the LLM cache's own JSON shape.
   catalogue_verify.py scores a pipeline run against it.

4. When the catalogue defines PROGRAMS, students are assigned to one and
   enrol by its rules, so an engineering student and a biology student
   share first-year chemistry and maths and then diverge -- a cohort that
   looks like a university, not one giant class. Abilities are drawn from
   a small number of latent aptitude traits through the competencies'
   `traits` loadings (catalogue.py), so strengths are correlated:
   a student strong in one quantitative competency tends to be strong in
   the others, and a program's students lean towards the traits its core
   subjects reward. Without programs or traits the model degrades to the
   simpler one above.

Feedback text reuses synth_generator's template-bank mechanism: one LLM call
for ~24 varied templates, sampled per row, or the built-in fallback with
--no-llm-feedback.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..review import ReviewStore, cluster_id, cluster_members
from .catalogue import Catalogue, ground_truth_clustering, load_catalogue
from .excel_loader import ResultRow, StudentSummary
from .synth_generator import (
    _FALLBACK_TEMPLATES,
    _feedback_band,
    _join_naturally,
    generate_feedback_bank,
)


@dataclass(frozen=True)
class CohortParams:
    n_students: int
    start_index: int = 1
    # Mirrors the supplied dataset's distribution (mean ~68, sd ~11).
    baseline_mean: float = 68.0
    baseline_sd: float = 11.0
    # Per-student, per-competency ability spread around the baseline. This is
    # the term the supplied data lacks. 7 points gives a typical student a
    # profile MAD of several points -- clearly above GAP_MIN_SPREAD -- without
    # making every student look bimodal.
    competency_sd: float = 7.0
    # Per-assessment noise on top of ability: marking variance, a bad day.
    noise_sd: float = 4.0
    planted_gap_fraction: float = 0.08
    # Competency ids eligible for a planted gap. Empty means every
    # cross-subject competency in the catalogue.
    planted_gap_competencies: tuple[str, ...] = ()
    planted_gap_depth: tuple[float, float] = (18.0, 30.0)
    # Probability a student is enrolled in each subject. 1.0 = everyone
    # takes everything (the supplied workbook's shape). Below 1.0 a planted
    # student is still enrolled in every subject that evidences their gap
    # competency, otherwise the gap could not be 'persistent' by definition.
    enrolment_fraction: float = 1.0
    min_subjects: int = 2
    # Latent-trait ability model (used when competencies carry `traits`).
    # Share of each competency's ability variance that comes through the
    # shared traits rather than independent noise: 1.0 makes every
    # competency a pure function of a student's few aptitudes, 0.0 makes
    # them independent (the model above).
    latent_share: float = 0.7
    # How strongly a program's students lean towards the traits its core
    # subjects reward, in trait standard deviations. 0 = no selection effect.
    program_selection: float = 0.6


@dataclass
class GeneratedStudent:
    student_id: str
    baseline: float
    abilities: dict[str, float]
    subjects: list[str]
    planted_competency: str | None = None
    planted_depth: float = 0.0
    program: str | None = None
    traits: list[float] | None = None


@dataclass
class Cohort:
    students: list[GeneratedStudent]
    results: list[ResultRow]
    summaries: list[StudentSummary]
    # (student_id, subject_code, assessment_name) -> raw score, for the
    # Moodle emitter, which needs per-assessment marks without re-deriving them.
    scores: dict[tuple[str, str, str], float] = field(default_factory=dict)

    @property
    def planted(self) -> dict[str, GeneratedStudent]:
        return {s.student_id: s for s in self.students if s.planted_competency}


def _performance_band(average_total: float) -> str:
    if average_total < 50:
        return "At risk"
    if average_total < 60:
        return "P range"
    if average_total < 70:
        return "C range"
    if average_total < 80:
        return "D range"
    return "HD/D range"


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _program_core_subjects(catalogue: Catalogue, program) -> list[str]:
    seen: list[str] = []
    for rule in program.rules:
        if rule.core:
            for code in catalogue.match_subjects(rule.patterns):
                if code not in seen:
                    seen.append(code)
                if rule.take >= 0 and len(seen) >= rule.take:
                    break
    return seen


def program_trait_means(catalogue: Catalogue, params: CohortParams) -> dict[str, list[float]]:
    """Per program, the mean loading of the competencies its core subjects
    evidence, scaled to `program_selection` trait SDs. This is the selection
    effect: people who chose engineering tend to be the people engineering
    rewards. Zero vector when the catalogue has no traits."""
    silo_comp = catalogue.silo_key_to_competency()
    loadings = {c.id: c.traits for c in catalogue.competencies if c.traits}
    if not loadings:
        return {p.code: [] for p in catalogue.programs}
    dim = len(next(iter(loadings.values())))
    out: dict[str, list[float]] = {}
    for program in catalogue.programs:
        vecs = []
        for code in _program_core_subjects(catalogue, program):
            for silo in catalogue.subject(code).silos:
                cid = silo_comp[f"{code}:{silo.id}"]
                if cid in loadings:
                    vecs.append(loadings[cid])
        if not vecs:
            out[program.code] = [0.0] * dim
            continue
        mean = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        norm = math.sqrt(sum(m * m for m in mean)) or 1.0
        out[program.code] = [params.program_selection * m / norm for m in mean]
    return out


def enrol_by_program(catalogue: Catalogue, program, rng: random.Random) -> list[str]:
    """Apply the program's rules in order; each rule draws from subjects not
    already chosen. Core rules take the first `take` matches in catalogue
    order (or all); elective rules sample `take` of the pool."""
    chosen: list[str] = []
    for rule in program.rules:
        pool = [c for c in catalogue.match_subjects(rule.patterns) if c not in chosen]
        if not pool:
            continue
        if rule.take < 0 or rule.take >= len(pool):
            picks = pool
        elif rule.core:
            picks = pool[: rule.take]
        else:
            picks = rng.sample(pool, k=rule.take)
        chosen.extend(picks)
    order = [s.code for s in catalogue.subjects]
    return sorted(chosen, key=order.index)


def draw_abilities(catalogue: Catalogue, params: CohortParams, traits: list[float] | None, rng: random.Random) -> dict[str, float]:
    abilities: dict[str, float] = {}
    shared = math.sqrt(params.latent_share)
    indep = math.sqrt(1.0 - params.latent_share)
    for c in catalogue.competencies:
        if traits and c.traits:
            latent = sum(a * b for a, b in zip(c.traits, traits))
            abilities[c.id] = params.competency_sd * (shared * latent + indep * rng.gauss(0.0, 1.0))
        else:
            abilities[c.id] = rng.gauss(0.0, params.competency_sd)
    return abilities


def generate_cohort(
    catalogue: Catalogue,
    params: CohortParams,
    *,
    feedback_bank: dict[str, list[str]],
    rng: random.Random,
) -> Cohort:
    silo_comp = catalogue.silo_key_to_competency()
    comp_subjects = catalogue.competency_subjects()
    eligible = list(params.planted_gap_competencies) or catalogue.cross_subject_competencies()
    unknown = [c for c in eligible if c not in comp_subjects]
    if unknown:
        raise ValueError(f"planted-gap competencies not in catalogue: {unknown}")
    if not eligible:
        raise ValueError("no cross-subject competency to plant a gap in; the catalogue needs at least one")

    all_codes = [s.code for s in catalogue.subjects]
    students: list[GeneratedStudent] = []
    results: list[ResultRow] = []
    summaries: list[StudentSummary] = []
    scores: dict[tuple[str, str, str], float] = {}

    has_traits = any(c.traits for c in catalogue.competencies)
    n_traits = len(next(c.traits for c in catalogue.competencies if c.traits)) if has_traits else 0
    prog_means = program_trait_means(catalogue, params) if catalogue.programs else {}
    prog_weights = [p.intake_share for p in catalogue.programs]

    for i in range(params.n_students):
        student_id = f"STU{params.start_index + i:04d}"
        baseline = _clip(rng.gauss(params.baseline_mean, params.baseline_sd), 20.0, 99.0)

        program = rng.choices(catalogue.programs, weights=prog_weights, k=1)[0] if catalogue.programs else None
        traits: list[float] | None = None
        if has_traits:
            mean = prog_means.get(program.code, [0.0] * n_traits) if program else [0.0] * n_traits
            traits = [rng.gauss(m, 1.0) for m in mean]
        abilities = draw_abilities(catalogue, params, traits, rng)

        # Enrolment first, so a planted gap can only land in a competency the
        # student's own subjects will evidence at least twice.
        if program is not None:
            enrolled = enrol_by_program(catalogue, program, rng)
        elif params.enrolment_fraction >= 1.0:
            enrolled = list(all_codes)
        else:
            enrolled = [c for c in all_codes if rng.random() < params.enrolment_fraction]
            while len(enrolled) < min(params.min_subjects, len(all_codes)):
                enrolled.append(rng.choice([c for c in all_codes if c not in enrolled]))
            enrolled.sort(key=all_codes.index)

        planted: str | None = None
        depth = 0.0
        if rng.random() < params.planted_gap_fraction:
            if program is None and params.enrolment_fraction < 1.0:
                # Legacy path: keep the old guarantee by adding the gap's subjects.
                planted = rng.choice(eligible)
                enrolled = sorted(set(enrolled) | comp_subjects[planted], key=all_codes.index)
            else:
                evidenced = {
                    cid for cid in eligible if len(comp_subjects[cid] & set(enrolled)) >= 2
                }
                planted = rng.choice(sorted(evidenced)) if evidenced else None
            if planted:
                depth = rng.uniform(*params.planted_gap_depth)
                # Depth is applied on top of whatever ability they had, so a
                # planted student is always clearly below their OWN median on
                # this competency -- that is the signal, and it is independent
                # of how strong they are overall.
                abilities[planted] = min(abilities[planted], 0.0) - depth

        subject_totals: dict[str, float] = {}
        for code in enrolled:
            subject = catalogue.subject(code)
            weighted_sum = 0.0
            for assessment in subject.assessments:
                comps = [silo_comp[f"{code}:{sid}"] for sid in assessment.silos]
                ability_term = sum(abilities[c] for c in comps) / len(comps)
                score = round(_clip(baseline + ability_term + rng.gauss(0.0, params.noise_sd), 1.0, 100.0))

                silo_texts = {s.id: s.text for s in subject.silos}
                template = rng.choice(feedback_bank[_feedback_band(score)])
                feedback = template.format(silos=_join_naturally([silo_texts[sid] for sid in assessment.silos]))

                weighted_score = round(score * assessment.weight, 2)
                weighted_sum += weighted_score
                scores[(student_id, code, assessment.name)] = float(score)
                results.append(
                    ResultRow(
                        student_id=student_id,
                        subject_code=code,
                        assessment_name=assessment.name,
                        score=float(score),
                        feedback_comment=feedback,
                        weight=assessment.weight,
                        weighted_score=weighted_score,
                        silo_ids=tuple(assessment.silos),
                    )
                )
            subject_totals[code] = round(weighted_sum, 2)

        average_total = round(sum(subject_totals.values()) / len(subject_totals), 4)
        summaries.append(
            StudentSummary(
                student_id=student_id,
                subject_totals=subject_totals,
                average_total=average_total,
                performance_band=_performance_band(average_total),
            )
        )
        students.append(
            GeneratedStudent(
                student_id=student_id,
                baseline=baseline,
                abilities=abilities,
                subjects=enrolled,
                planted_competency=planted,
                planted_depth=depth,
                program=program.code if program else None,
                traits=traits,
            )
        )

    return Cohort(students=students, results=results, summaries=summaries, scores=scores)


# -- workbook -----------------------------------------------------------------


def _silo_field(catalogue: Catalogue, subject_code: str, silo_ids: tuple[str, ...] | list[str]) -> str:
    texts = {s.id: s.text for s in catalogue.subject(subject_code).silos}
    return "; ".join(f"{sid}: {texts[sid]}" for sid in silo_ids)


def assessment_map_frame(catalogue: Catalogue) -> pd.DataFrame:
    rows = []
    for subject in catalogue.subjects:
        for a in subject.assessments:
            rows.append(
                {
                    "Subject Code": subject.code,
                    "Assessment Type": f"{subject.code} - {a.name}",
                    "Weight": a.weight,
                    "Contribution": a.contribution,
                    "Early Assessment": "Yes" if a.early_assessment else "No",
                    "Hurdle": "Yes" if a.hurdle else "No",
                    "SILOs": ", ".join(a.silos),
                    "SILO Theme Summary": _silo_field(catalogue, subject.code, a.silos),
                }
            )
    return pd.DataFrame(rows)


def write_workbook(catalogue: Catalogue, cohort: Cohort, out_path: str | Path) -> None:
    results_df = pd.DataFrame(
        [
            {
                "Student ID": r.student_id,
                "Assessment Type": f"{r.subject_code} - {r.assessment_name}",
                "Score (1-100)": int(r.score),
                "Feedback Comment": r.feedback_comment,
                "SILO's": _silo_field(catalogue, r.subject_code, r.silo_ids),
                "Weight": r.weight,
                "Weighted Score": r.weighted_score,
            }
            for r in cohort.results
        ]
    )
    codes = [s.code for s in catalogue.subjects]
    programs = {s.student_id: s.program or "" for s in cohort.students}
    summary_df = pd.DataFrame(
        [
            {
                "Student ID": s.student_id,
                "Program": programs.get(s.student_id, ""),
                **{f"{code} Total": s.subject_totals.get(code) for code in codes},
                "Average Total": s.average_total,
                "Performance Band": s.performance_band,
            }
            for s in cohort.summaries
        ]
    )
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        results_df.to_excel(writer, sheet_name="Results", index=False)
        summary_df.to_excel(writer, sheet_name="Student Summary", index=False)
        assessment_map_frame(catalogue).to_excel(writer, sheet_name="Assessment Map", index=False)


# -- ground truth -------------------------------------------------------------


def truth_document(catalogue: Catalogue, cohort: Cohort, params: CohortParams, seed: int, catalogue_path: str) -> dict:
    return {
        "catalogue": catalogue_path,
        "seed": seed,
        "params": {
            k: (list(v) if isinstance(v, tuple) else v) for k, v in params.__dict__.items()
        },
        "competency_labels": {c.id: c.label for c in catalogue.competencies},
        "competency_traits": {c.id: c.traits for c in catalogue.competencies if c.traits},
        "programs": {p.code: p.title for p in catalogue.programs},
        "silo_competency": catalogue.silo_key_to_competency(),
        "planted": {
            s.student_id: {"competency": s.planted_competency, "depth": round(s.planted_depth, 2)}
            for s in cohort.students
            if s.planted_competency
        },
        "students": {
            s.student_id: {
                "baseline": round(s.baseline, 2),
                "program": s.program,
                "traits": [round(t, 3) for t in s.traits] if s.traits else None,
                "subjects": s.subjects,
                "abilities": {k: round(v, 2) for k, v in s.abilities.items()},
            }
            for s in cohort.students
        },
    }


def confirmed_review_store(catalogue: Catalogue) -> ReviewStore:
    """A staff-review file with every ground-truth cluster already confirmed,
    so `lja.cli --clustering-cache <truth>` passes the confirmation gate
    without --allow-unconfirmed. Legitimate here and only here: the
    'reviewer' is the catalogue author, who wrote the clusters by hand.
    """
    from ..review import ClusterReview

    store = ReviewStore()
    for cluster in ground_truth_clustering(catalogue).clusters:
        cid = cluster_id(cluster)
        store.reviews[cid] = ClusterReview(
            cluster_id=cid,
            competency_label=cluster.competency_label,
            members=cluster_members(cluster),
            state="confirmed",
            note="Ground truth from the subject catalogue, not an LLM proposal.",
        )
    return store


def write_truth_files(catalogue: Catalogue, cohort: Cohort, params: CohortParams, seed: int, catalogue_path: str, out_xlsx: Path) -> dict[str, Path]:
    stem = out_xlsx.with_suffix("")
    paths = {
        "truth": stem.with_name(stem.name + ".truth.json"),
        "clustering": stem.with_name(stem.name + ".clustering.json"),
        "review": stem.with_name(stem.name + ".clustering.review.json"),
    }
    paths["truth"].write_text(json.dumps(truth_document(catalogue, cohort, params, seed, catalogue_path), indent=2))
    paths["clustering"].write_text(ground_truth_clustering(catalogue).model_dump_json(indent=2))
    paths["review"].write_text(confirmed_review_store(catalogue).model_dump_json(indent=2) + "\n")
    return paths


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic cohort from a subject catalogue (IOLG-113)")
    parser.add_argument("catalogue", help="Subject catalogue YAML, e.g. ../data-fixtures/subject_catalogue.yaml")
    parser.add_argument("--students", type=int, default=300)
    parser.add_argument("--start-index", type=int, default=1, help="First student number (STU%%04d)")
    parser.add_argument("--out", required=True, help="Output workbook path (.xlsx); truth files are written beside it")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baseline-mean", type=float, default=CohortParams.baseline_mean)
    parser.add_argument("--baseline-sd", type=float, default=CohortParams.baseline_sd)
    parser.add_argument("--competency-sd", type=float, default=CohortParams.competency_sd,
                        help="Per-competency ability spread; 0 reproduces the supplied data's flat profiles")
    parser.add_argument("--noise-sd", type=float, default=CohortParams.noise_sd)
    parser.add_argument("--planted-gap-fraction", type=float, default=CohortParams.planted_gap_fraction)
    parser.add_argument("--planted-gap-competencies", default="",
                        help="Comma-separated competency ids to plant gaps in (default: every cross-subject competency)")
    parser.add_argument("--planted-gap-depth", default="18,30", help="min,max points of suppression")
    parser.add_argument("--enrolment-fraction", type=float, default=1.0,
                        help="Probability a student takes each subject (1.0 = everyone takes everything)")
    parser.add_argument("--latent-share", type=float, default=CohortParams.latent_share,
                        help="Share of competency ability variance carried by shared aptitude traits (0..1)")
    parser.add_argument("--program-selection", type=float, default=CohortParams.program_selection,
                        help="How far a program's students lean towards its core traits, in trait SDs")
    parser.add_argument("--no-llm-feedback", action="store_true", help="Use the built-in feedback templates only")
    parser.add_argument("--moodle-out", default=None,
                        help="Also write Moodle fixtures (competency CSVs, criterion map, rubric marking JSON) into this directory")
    parser.add_argument("--moodle-students", type=int, default=5,
                        help="How many generated students to mark in the Moodle rubric fixture per assignment")
    parser.add_argument("--llm-remarks", action="store_true",
                        help="Generate the Moodle remark template bank with the LLM (default: built-in templates)")
    args = parser.parse_args(argv)

    catalogue = load_catalogue(args.catalogue)
    n_silos = sum(len(s.silos) for s in catalogue.subjects)
    print(f"Catalogue: {len(catalogue.subjects)} subjects, {n_silos} SILOs, {len(catalogue.competencies)} competencies "
          f"({len(catalogue.cross_subject_competencies())} span 2+ subjects).")

    if args.no_llm_feedback:
        feedback_bank = dict(_FALLBACK_TEMPLATES)
        client = None
    else:
        from ..llm.factory import get_llm_client

        client = get_llm_client()
        print(f"LLM: {client.describe()}")
        print("Generating a varied feedback-template bank (one LLM call)...")
        feedback_bank = generate_feedback_bank(client)

    lo, hi = (float(x) for x in args.planted_gap_depth.split(","))
    params = CohortParams(
        n_students=args.students,
        start_index=args.start_index,
        baseline_mean=args.baseline_mean,
        baseline_sd=args.baseline_sd,
        competency_sd=args.competency_sd,
        noise_sd=args.noise_sd,
        planted_gap_fraction=args.planted_gap_fraction,
        planted_gap_competencies=tuple(c.strip() for c in args.planted_gap_competencies.split(",") if c.strip()),
        planted_gap_depth=(lo, hi),
        enrolment_fraction=args.enrolment_fraction,
        latent_share=args.latent_share,
        program_selection=args.program_selection,
    )
    rng = random.Random(args.seed)
    cohort = generate_cohort(catalogue, params, feedback_bank=feedback_bank, rng=rng)

    out_xlsx = Path(args.out)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(catalogue, cohort, out_xlsx)
    truth_paths = write_truth_files(catalogue, cohort, params, args.seed, args.catalogue, out_xlsx)

    planted = cohort.planted
    print(f"Generated {len(cohort.students)} students, {len(cohort.results)} result rows; "
          f"{len(planted)} students carry a planted gap.")
    if catalogue.programs:
        from collections import Counter

        by_program = Counter(s.program for s in cohort.students)
        subj = [len(s.subjects) for s in cohort.students]
        print("Programs: " + ", ".join(f"{p}={n}" for p, n in sorted(by_program.items()))
              + f"; subjects per student {min(subj)}-{max(subj)} (mean {sum(subj) / len(subj):.1f})")
    print(f"Wrote workbook:   {out_xlsx}")
    for label, p in truth_paths.items():
        print(f"Wrote {label + ':':<12}{p}")

    if args.moodle_out:
        from .moodle_emitters import write_moodle_fixtures

        remark_bank = None
        if args.llm_remarks:
            from .moodle_emitters import generate_remark_bank

            if client is None:
                from ..llm.factory import get_llm_client

                client = get_llm_client()
            print("Generating a marker-remark template bank (one LLM call)...")
            remark_bank = generate_remark_bank(client)
        written = write_moodle_fixtures(
            catalogue, cohort, Path(args.moodle_out), n_students=args.moodle_students, remark_bank=remark_bank, rng=rng
        )
        for p in written:
            print(f"Wrote moodle:     {p}")

    if client is not None:
        print(f"LLM usage: {client.usage_summary()}")
    print("\nNext: run the pipeline against the ground-truth clustering, then score it:")
    print(f"  python -m lja.cli {out_xlsx} --clustering-cache {truth_paths['clustering']}")
    print(f"  python -m lja.data.catalogue_verify {truth_paths['truth']} --gaps output/gap_report.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
