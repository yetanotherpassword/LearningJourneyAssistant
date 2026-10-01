"""Grounded practice quiz for one student (tender requirement R8, "adaptive quiz").

A learning plan says WHAT to work on and a study strategy says HOW to study
it. A quiz lets the student check whether the gap is closing: a few
multiple-choice questions per gap competency, each tied to one SILO the
student is weak in and one of their own assessments, with an explanation
that points back at that SILO.

It mirrors study_strategy.py on purpose -- same context (PlanContext, plus
the handbook synopsis of each subject where the catalogue has one), same
fail-closed generate/validate/retry loop, same per-competency grounding --
because the tender singles quizzes out as the artefact "most likely to look
plausible while quietly not being grounded".

What the checks DO guarantee: every item is filed under a real gap of this
student, names a SILO of that competency, an assessment of this student
that covers that SILO, and the subject both belong to; every gap gets its
items; option counts and the answer index are well-formed; prose carries
no invented subject code or SILO key.

What the checks DO NOT guarantee, and the page says so: that the marked
answer is correct, or that the question is pitched at the right level. The
only subject matter in the input is the SILO wording, the assessment names,
the marker's feedback and the handbook synopsis. The question, its answer
key and its distractors come from the model's general knowledge of that
topic. That is the limit the tender warned about, and it is why staff
review of a quiz before a student sees it is part of the design rather
than an optional extra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..llm.base import LLMClient
from ..llm.grounding import (
    SILO_KEY_PATTERN,
    SUBJECT_CODE_PATTERN,
    GroundingError,
    ReferenceCheck,
    check_grounding,
    extract_codes,
)
from .gap_detection import ISOLATED_GAP, PERSISTENT_GAP
from .learning_plan import CompetencyContext, PlanContext
from .study_strategy import assessments_for, evidencing_subjects, gap_competencies

GAP_KINDS = (PERSISTENT_GAP, ISOLATED_GAP)

MIN_OPTIONS = 3
MAX_OPTIONS = 4
DEFAULT_ITEMS_PER_GAP = 2

# --- Context ---------------------------------------------------------------


@dataclass(frozen=True)
class SubjectInfo:
    """What the catalogue knows about a subject beyond its SILOs: the title
    and, for handbook subjects, the first part of the handbook synopsis.
    Shown to the model as topic context and to the reader on the page."""

    code: str
    title: str
    year_level: int
    synopsis: str = ""


@dataclass(frozen=True)
class QuizContext:
    """A PlanContext plus subject synopses and the item count per gap. The
    plan context is the complete vocabulary; the synopses add topic
    background only and introduce no new names the checks would have to
    know about (a synopsis may mention another subject code, so the
    subjects it names are added to the known set, nothing else)."""

    plan: PlanContext
    subjects: tuple[SubjectInfo, ...] = ()
    items_per_gap: int = DEFAULT_ITEMS_PER_GAP

    @property
    def student_id(self) -> str:
        return self.plan.student_id

    @property
    def known_subjects(self) -> frozenset[str]:
        extra = {s.code for s in self.subjects}
        for s in self.subjects:
            extra.update(extract_codes(s.synopsis, SUBJECT_CODE_PATTERN))
        return self.plan.known_subjects | frozenset(extra)


def build_quiz_context(
    plan: PlanContext,
    subjects_by_code: dict[str, SubjectInfo] | None = None,
    *,
    items_per_gap: int = DEFAULT_ITEMS_PER_GAP,
) -> QuizContext:
    """Attach the catalogue's subject info for every subject the plan
    context mentions. Subjects the catalogue does not know are listed with
    their code only, so the page never claims a synopsis it does not have."""
    if items_per_gap < 1:
        raise ValueError("items_per_gap must be at least 1")
    subjects_by_code = subjects_by_code or {}
    infos = []
    for code in sorted(plan.known_subjects):
        info = subjects_by_code.get(code)
        infos.append(info if info is not None else SubjectInfo(code=code, title="", year_level=0))
    return QuizContext(plan=plan, subjects=tuple(infos), items_per_gap=items_per_gap)


def has_gaps(context: QuizContext) -> bool:
    return bool(gap_competencies(context.plan))


# --- Output schema ---------------------------------------------------------
# extra="forbid" for the same reasons as learning_plan.py.


class QuizItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_label: str
    gap_kind: Literal["persistent gap", "isolated gap"]
    subject_code: str  # the subject the SILO and assessment belong to
    silo_key: str  # "SUBJECT:SILOn" -- the outcome this question tests
    assessment_key: str  # "SUBJECT:Assessment name" -- the student's assessment it is pitched at
    stem: str
    options: list[str] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    correct_index: int = Field(ge=0, lt=MAX_OPTIONS)
    explanation: str  # why the answer is right, naming the SILO to revisit


class Quiz(BaseModel):
    """What the model returns."""

    model_config = ConfigDict(extra="forbid")

    student_id: str
    introduction: str
    items: list[QuizItem]


class QuizSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str = ""
    year_level: int = 0
    synopsis: str = ""


class QuizDocument(BaseModel):
    """What is written to disk and what the dashboard renders: the quiz plus
    the subject info it was shown, so the page can print the same synopsis
    the model saw and nothing more."""

    model_config = ConfigDict(extra="forbid")

    student_id: str
    introduction: str
    items: list[QuizItem]
    subjects: list[QuizSubject] = []

    @classmethod
    def from_quiz(cls, quiz: Quiz, context: QuizContext) -> QuizDocument:
        return cls(
            student_id=quiz.student_id,
            introduction=quiz.introduction,
            items=quiz.items,
            subjects=[
                QuizSubject(code=s.code, title=s.title, year_level=s.year_level, synopsis=s.synopsis)
                for s in context.subjects
            ],
        )


# --- Grounding -------------------------------------------------------------

_ITEM_PROSE_FIELDS = ("stem", "explanation")


def _gaps(context: QuizContext) -> dict[str, CompetencyContext]:
    return {c.competency_label: c for c in gap_competencies(context.plan)}


def quiz_grounding_checks(quiz: Quiz, context: QuizContext) -> list[ReferenceCheck]:
    """Name checks: every reference must come from the context, filed under
    the right competency. Separate from the structural rules so each can be
    tested on its own."""
    gaps = _gaps(context)
    prose = [quiz.introduction]
    for item in quiz.items:
        prose += [getattr(item, f) for f in _ITEM_PROSE_FIELDS] + list(item.options)
    prose_text = "\n".join(prose)

    checks = [
        ReferenceCheck("student", [quiz.student_id], [context.student_id]),
        # Every gap gets at least one item; nothing for a non-gap. Counts
        # per gap are a structural rule below.
        ReferenceCheck("gap competency", [i.competency_label for i in quiz.items], gaps.keys(), require_complete=True),
        ReferenceCheck(
            "gap classification",
            [f"{i.competency_label} = {i.gap_kind}" for i in quiz.items],
            [f"{label} = {c.classification}" for label, c in gaps.items()],
        ),
        ReferenceCheck("SILO mentioned in prose", extract_codes(prose_text, SILO_KEY_PATTERN), context.plan.known_silos),
        ReferenceCheck("subject mentioned in prose", extract_codes(prose_text, SUBJECT_CODE_PATTERN), context.known_subjects),
    ]
    for item in quiz.items:
        competency = gaps.get(item.competency_label)
        if competency is None:
            continue  # already reported by the gap-competency check
        label = item.competency_label
        checks += [
            ReferenceCheck(f"subject evidencing '{label}'", [item.subject_code], evidencing_subjects(competency)),
            ReferenceCheck(f"SILO in '{label}'", [item.silo_key], competency.silo_keys),
            ReferenceCheck(f"assessment evidencing '{label}'", [item.assessment_key], assessments_for(context.plan, competency)),
        ]
    return checks


def quiz_structure_problems(quiz: Quiz, context: QuizContext) -> list[str]:
    """Well-formedness and the per-gap count. Plain sentences, quoted back
    to the model on retry."""
    gaps = _gaps(context)
    problems: list[str] = []
    want = context.items_per_gap
    counts = {label: 0 for label in gaps}
    for item in quiz.items:
        if item.competency_label in counts:
            counts[item.competency_label] += 1
    for label, n in counts.items():
        if n != want:
            problems.append(f"'{label}' has {n} question(s); write exactly {want}")

    for n, item in enumerate(quiz.items, 1):
        where = f"question {n}"
        if not item.stem.strip():
            problems.append(f"{where} has an empty stem")
        cleaned = [o.strip() for o in item.options]
        if any(not o for o in cleaned):
            problems.append(f"{where} has a blank option")
        if len(set(cleaned)) != len(cleaned):
            problems.append(f"{where} repeats an option")
        if not 0 <= item.correct_index < len(item.options):
            problems.append(f"{where}: correct_index {item.correct_index} is outside its {len(item.options)} options")
        if not item.explanation.strip():
            problems.append(f"{where} has no explanation")
        # The SILO and the assessment must be in the subject the item says
        # they are; the per-competency checks above only confirm each exists.
        if item.silo_key.split(":", 1)[0] != item.subject_code:
            problems.append(f"{where}: silo_key {item.silo_key} is not in subject {item.subject_code}")
        if item.assessment_key.split(":", 1)[0] != item.subject_code:
            problems.append(f"{where}: assessment_key {item.assessment_key} is not in subject {item.subject_code}")
    return problems


def validate_quiz(quiz: Quiz, context: QuizContext) -> None:
    """Raise GroundingError listing every name and structure problem at once."""
    artefact = f"quiz for {context.student_id}"
    report = check_grounding(artefact, quiz_grounding_checks(quiz, context))
    structure = quiz_structure_problems(quiz, context)
    if report.ok and not structure:
        return
    parts = [p.describe() for p in report.problems] + structure
    raise GroundingError(f"{artefact} failed grounding validation -- " + "; ".join(parts))


# --- Prompt ----------------------------------------------------------------

_SYSTEM_PROMPT = """You are writing a short practice quiz for ONE university student, so they can check \
whether a learning gap is closing. You will be given their results: how they attain each \
cross-subject competency, which of those are gaps, the wording of the learning outcomes (SILOs) \
behind each gap, their own assessment scores and marker feedback, and a short handbook synopsis of \
each subject where one is available.

Write multiple-choice questions ONLY for competencies marked "persistent gap" or "isolated gap". \
Mastery estimates are formative signals, never a verdict on the student; the introduction should \
say the quiz is practice, not assessment.

Rules that are checked automatically -- a quiz that breaks them is rejected and you will be asked again:

1. Write exactly {items_per_gap} question(s) for every competency marked a gap, and none for any \
other competency. Copy competency_label and gap_kind from the input.
2. Each question names one subject_code, one silo_key (e.g. CSE1OOF:SILO2) and one assessment_key \
(e.g. CSE1OOF:Test), copied exactly from the input. The SILO must be listed under that competency, \
the assessment must be one of this student's assessments that covers that SILO, and both must \
belong to the subject named in subject_code. If a sentence mentions a subject or SILO, use its \
exact key. Do not mention any subject or SILO that is not in the input.
3. The question tests what that SILO's wording describes, pitched at the level of the named \
assessment and the subject synopsis. Do not test anything the SILO does not say. Where the marker's \
feedback names a specific mistake, build a question around that mistake.
4. Give 3 or 4 options. Exactly one is correct; correct_index is its 0-based position. Distractors \
are plausible mistakes, not jokes or obviously wrong answers. Vary which position holds the correct \
answer.
5. explanation says why the correct option is right, why the most tempting distractor is wrong, \
and names the silo_key to revisit.
6. introduction is one or two sentences on what the quiz covers and that it is practice.
"""


def _render_context(context: QuizContext) -> str:
    plan = context.plan
    lines = [f"Student: {plan.student_id}", "", "Competencies (lowest attainment first):"]
    for c in plan.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject) or "no per-subject evidence"
        lines.append(f"- {c.competency_label}: {c.classification}, attainment {c.attainment_pct:.1f}% (per subject: {per_subject})")
        if c.classification in GAP_KINDS:
            for key in c.silo_keys:
                lines.append(f"    SILO {key}: {plan.silo_text.get(key, '(wording not available)')}")
            covering = sorted(assessments_for(plan, c))
            lines.append(f"    Assessments covering it: {', '.join(covering) or 'none'}")
    lines += ["", "This student's assessments (score is a percentage; feedback is the marker's comment):"]
    for a in plan.assessments:
        silos = ", ".join(a.silo_keys) or "no clustered SILO"
        feedback = a.feedback_comment.strip() or "(no feedback recorded)"
        lines.append(f"- {a.key}: {a.score:.1f}%, weight {a.weight:g}, SILOs {silos}. Feedback: {feedback}")
    lines += ["", "Subjects (title and handbook synopsis where available):"]
    for s in context.subjects:
        title = f" {s.title}" if s.title else ""
        synopsis = f": {s.synopsis}" if s.synopsis else ": (no synopsis available)"
        lines.append(f"- {s.code}{title}{synopsis}")
    return "\n".join(lines)


# --- Generation ------------------------------------------------------------


def generate_quiz(
    client: LLMClient,
    context: QuizContext,
    *,
    max_attempts: int = 3,
    extra_instructions: str | None = None,
) -> Quiz:
    """Generate, validate, retry with the problems quoted back; raise if it
    never grounds. Raises ValueError up front for a student with no gaps --
    a quiz for nothing would be pure invention."""
    if not has_gaps(context):
        raise ValueError(f"Student {context.student_id} has no isolated or persistent gap; no quiz is needed.")

    system_prompt = _SYSTEM_PROMPT.format(items_per_gap=context.items_per_gap)
    if extra_instructions:
        system_prompt = f"{system_prompt}\n\n{extra_instructions}"
    base_prompt = _render_context(context)

    last_error: GroundingError | None = None
    for _attempt in range(1, max_attempts + 1):
        user_prompt = base_prompt
        if last_error is not None:
            user_prompt += (
                f"\n\nYour previous quiz was rejected: {last_error} "
                "Fix every item named there. Copy every label, key and code exactly from the input above."
            )
        quiz = client.complete_structured(system=system_prompt, user=user_prompt, schema=Quiz)
        try:
            validate_quiz(quiz, context)
            return quiz
        except GroundingError as exc:
            last_error = exc
            continue

    raise GroundingError(
        f"Quiz for {context.student_id} failed grounding validation on all {max_attempts} attempts. "
        f"Last error: {last_error}"
    ) from last_error


# --- Rendering -------------------------------------------------------------

_LETTERS = "ABCD"


def render_markdown(document: QuizDocument, context: QuizContext) -> str:
    """Readable quiz with the answers after the questions and the evidence it
    was grounded in, so a reader can check any reference against the numbers."""
    out = [f"# Practice quiz for {document.student_id}", "", document.introduction, ""]
    out += [
        "> The grounding checks confirm every question is tied to one of this student's own gaps,",
        "> SILOs and assessments. They do not confirm the marked answer is correct: a member of",
        "> staff should check the answer key before a student uses this.",
        "",
    ]
    for n, item in enumerate(document.items, 1):
        kind = "persistent gap" if item.gap_kind == PERSISTENT_GAP else "isolated gap"
        out += [f"## {n}. {item.competency_label} ({kind})", ""]
        out += [f"*{item.subject_code}, {item.silo_key}, pitched at {item.assessment_key}*", ""]
        out += [item.stem, ""]
        out += [f"- {_LETTERS[i]}. {o}" for i, o in enumerate(item.options)]
        out.append("")
    out += ["## Answers", ""]
    for n, item in enumerate(document.items, 1):
        out += [f"**{n}.** {_LETTERS[item.correct_index]}. {item.explanation}", ""]
    if any(s.title or s.synopsis for s in document.subjects):
        out += ["## The subjects", ""]
        for s in document.subjects:
            title = f" {s.title}" if s.title else ""
            out += [f"- **{s.code}**{title}. {s.synopsis}".rstrip(". ") + ".", ""] if s.synopsis else [f"- **{s.code}**{title}", ""]
    out += ["## The evidence this quiz was grounded in", "", "| Competency | Classification | Attainment | Per subject |", "| --- | --- | --- | --- |"]
    for c in context.plan.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject)
        out.append(f"| {c.competency_label} | {c.classification} | {c.attainment_pct:.1f}% | {per_subject} |")
    out.append("")
    return "\n".join(out)
