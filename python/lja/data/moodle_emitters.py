"""Moodle-side fixtures derived from the subject catalogue (IOLG-113).

Everything here exists so the Moodle path and the Excel path are fed from
ONE definition of subjects and SILOs. The outputs:

- competency_framework_<CODE>.csv  -- one importable competency framework
  per subject, same column layout as data-fixtures/competency_framework_cse5idp.csv
  (Site administration -> Competencies -> Import competency framework).
- criterion_silo_map.csv           -- every rubric criterion in every subject,
  mapped to a SUBJECT:SILOn key. Same columns as
  data-fixtures/criterion_silo_map_CSE1IOI.csv; it is what makes Query 2's
  rows comparable to the Excel-path rows.
- rubric_fixture.json              -- the marking plan devenv/fixtures/
  mark_rubric_from_json.php replays: per course and assignment, the rubric
  definition and per-student level + remark for the first N enrolled
  students. Marks come from the SAME generated cohort as the workbook, so
  the Moodle rows and the Excel rows describe the same students.
- seed_subjects.txt                -- the shortnames devenv/seed.sh should
  generate, one per line.

Remarks: one template bank per performance band, filled with the criterion
text -- the synth_generator feedback-bank idea applied to rubric remarks.
Built-in templates by default; --llm-remarks on the generator swaps in an
LLM-written bank (one call), the "legitimate use of an LLM" devenv/README.md
describes.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .catalogue import Catalogue, CatalogueAssessment, RubricCriterion, Subject
from .catalogue_generator import Cohort
from .synth_generator import FEEDBACK_BANDS, _feedback_band

# Band -> rubric level index. Same cut points as the feedback bands, so a
# 'limited' Excel feedback comment and a 'Not demonstrated' Moodle level
# describe the same mark.
_BAND_TO_LEVEL = {"limited": 0, "developing": 1, "proficient": 2, "excellent": 3}

_FALLBACK_REMARKS: dict[str, list[str]] = {
    "limited": [
        "Little evidence of {criterion} in this submission; revisit the core material before the next task.",
        "The work does not yet demonstrate {criterion}. Seek feedback early and rework the approach.",
        "{criterion} is largely absent here, and the submission needs substantial revision to meet the standard.",
    ],
    "developing": [
        "Some progress on {criterion}, though the work is inconsistent and needs more careful attention.",
        "{criterion} is partially demonstrated; the ideas are present but not yet applied reliably.",
        "A developing attempt at {criterion}. Tighten the weaker sections and check the edge cases.",
    ],
    "proficient": [
        "Solid demonstration of {criterion}, with only minor points to tidy up.",
        "{criterion} is handled competently throughout; a few refinements would lift this further.",
        "Good, consistent work on {criterion}. The approach is sound and clearly applied.",
    ],
    "excellent": [
        "Excellent command of {criterion}; this is clear, thorough and well justified.",
        "{criterion} is demonstrated to a very high standard, with thoughtful attention to detail.",
        "An exemplary treatment of {criterion} that goes well beyond the minimum expectations.",
    ],
}


class RemarkTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: str
    text: str  # must contain the literal "{criterion}"


class RemarkTemplateBank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    templates: list[RemarkTemplate]


_REMARK_SYSTEM_PROMPT = """You are generating a bank of REUSABLE marker-remark TEMPLATES for synthetic \
university test data -- not feedback for a real student. Each template will later be filled in \
programmatically with the text of one rubric criterion (for example "Correct implementation and testing").

Generate 6 templates for EACH of these four performance bands: limited, developing, proficient, \
excellent (24 total). Within a band, vary sentence structure and vocabulary substantially -- they must \
not read like synonym-swapped copies. 1-2 sentences, professional Australian university marking tone, \
speaking only to the one criterion.

Every template MUST contain the literal placeholder "{criterion}" exactly once. Do not fill it in.
"""


def generate_remark_bank(client) -> dict[str, list[str]]:
    try:
        result = client.complete_structured(
            system=_REMARK_SYSTEM_PROMPT, user="Generate the 24 templates now (6 per band).", schema=RemarkTemplateBank
        )
    except Exception:
        return {b: list(t) for b, t in _FALLBACK_REMARKS.items()}
    bank: dict[str, list[str]] = {band: [] for band in FEEDBACK_BANDS}
    for t in result.templates:
        if t.band in bank and "{criterion}" in t.text:
            bank[t.band].append(t.text)
    for band in FEEDBACK_BANDS:
        if not bank[band]:
            bank[band] = list(_FALLBACK_REMARKS[band])
    return bank


def effective_criteria(subject: Subject, assessment: CatalogueAssessment) -> list[RubricCriterion]:
    """The assessment's explicit rubric, or one criterion per SILO derived
    from the SILO text when none is given."""
    if assessment.rubric is not None:
        return list(assessment.rubric.criteria)
    texts = {s.id: s.text for s in subject.silos}
    return [RubricCriterion(text=texts[sid][:1].upper() + texts[sid][1:], silo=sid) for sid in assessment.silos]


def level_for_score(score: float, n_levels: int) -> int:
    level = _BAND_TO_LEVEL[_feedback_band(score)]
    return min(level, n_levels - 1)


# -- competency frameworks ----------------------------------------------------

_FRAMEWORK_COLUMNS = [
    "Parent ID number", "ID number", "Short name", "Description", "Description format", "Scale values",
    "Scale configuration", "Rule type", "Rule outcome", "Rule config", "Related ID numbers", "Exported ID",
    "Is framework", "Taxonomy",
]


def competency_framework_rows(catalogue: Catalogue, subject: Subject) -> list[list[str]]:
    scale_values = json.dumps(list(catalogue.rubric_levels.values()))
    n = len(catalogue.rubric_levels)
    # Default level = the lowest; proficient = the top half, matching the
    # worked CSE5IDP example's shape. scaleid 0 is the documented caveat in
    # data-fixtures/README.md -- verify against an export on your Moodle.
    scale_config = json.dumps(
        [{"scaleid": "0"}]
        + [{"id": i + 1, "scaledefault": 1 if i == 0 else 0, "proficient": 1 if i >= n // 2 else 0} for i in range(n)]
    )
    framework_id = f"{subject.code}-SILOS"
    rows = [
        [
            "", framework_id, f"{subject.code} subject intended learning outcomes",
            f"Subject intended learning outcomes for {subject.code} {subject.title} (year {subject.year_level}). "
            f"Source: {'supplied dataset' if subject.source == 'supplied' else 'LJA synthetic subject catalogue'}.",
            "1", scale_values, scale_config, "", "0", "", "", "", "1", "outcome",
        ]
    ]
    for silo in subject.silos:
        short = f"{silo.id} {silo.text}"
        rows.append(
            ["" + framework_id, f"{subject.code}-{silo.id}", short[:100], silo.text, "1", "", "", "", "0", "", "", "", "0", ""]
        )
    return rows


# -- rubric fixture -----------------------------------------------------------


def rubric_fixture(
    catalogue: Catalogue,
    cohort: Cohort,
    *,
    n_students: int,
    remark_bank: dict[str, list[str]] | None,
    rng: random.Random,
) -> list[dict]:
    bank = remark_bank or _FALLBACK_REMARKS
    levels = catalogue.rubric_levels
    fixtures: list[dict] = []
    for subject in catalogue.subjects:
        # Only students enrolled in this subject have marks for it.
        enrolled = [s for s in cohort.students if subject.code in s.subjects][:n_students]
        for assessment in subject.assessments:
            criteria = effective_criteria(subject, assessment)
            students = []
            for gs in enrolled:
                score = cohort.scores[(gs.student_id, subject.code, assessment.name)]
                level = level_for_score(score, len(levels))
                band = _feedback_band(score)
                students.append(
                    {
                        "source_student_id": gs.student_id,
                        "scores": [level] * len(criteria),
                        "remarks": [rng.choice(bank[band]).format(criterion=c.text) for c in criteria],
                    }
                )
            fixtures.append(
                {
                    "course": subject.code,
                    "assignment": assessment.moodle_assignment,
                    "catalogue_assessment": assessment.name,
                    "rubric_name": f"LJA {subject.code} {assessment.name} rubric",
                    "criteria": [c.text for c in criteria],
                    "levels": {str(k): v for k, v in levels.items()},
                    "students": students,
                }
            )
    return fixtures


# -- write everything ---------------------------------------------------------


def write_moodle_fixtures(
    catalogue: Catalogue,
    cohort: Cohort,
    out_dir: Path,
    *,
    n_students: int = 5,
    remark_bank: dict[str, list[str]] | None = None,
    rng: random.Random | None = None,
) -> list[Path]:
    rng = rng or random.Random(0)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for subject in catalogue.subjects:
        p = out_dir / f"competency_framework_{subject.code}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(_FRAMEWORK_COLUMNS)
            w.writerows(competency_framework_rows(catalogue, subject))
        written.append(p)

    p = out_dir / "criterion_silo_map.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject_code", "assessment_name", "criterion_text", "silo_key", "weight"])
        for subject in catalogue.subjects:
            for assessment in subject.assessments:
                for c in effective_criteria(subject, assessment):
                    w.writerow([subject.code, assessment.moodle_assignment, c.text, f"{subject.code}:{c.silo}", 1.0])
    written.append(p)

    p = out_dir / "rubric_fixture.json"
    p.write_text(json.dumps(rubric_fixture(catalogue, cohort, n_students=n_students, remark_bank=remark_bank, rng=rng), indent=2))
    written.append(p)

    p = out_dir / "seed_subjects.txt"
    p.write_text("".join(f"{s.code}\n" for s in catalogue.subjects))
    written.append(p)
    return written
