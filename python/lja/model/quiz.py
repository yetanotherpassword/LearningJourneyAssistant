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
MIN_MARKING_POINTS = 2
MAX_MARKING_POINTS = 5

# Question formats. The educator sets the policy per run; under "mixed" the
# model chooses per question, inside the rule below.
MULTIPLE_CHOICE = "multiple_choice"
WRITTEN = "written"
QuizFormat = Literal["multiple_choice", "written", "mixed"]
ITEM_KINDS = (MULTIPLE_CHOICE, WRITTEN)
DEFAULT_FORMAT: QuizFormat = "mixed"

# A SILO whose wording asks the student to DO something (implement, design,
# evaluate...) is not served by recognising an option: under the mixed policy
# such a SILO must get a written task. Matched as substrings of the
# lower-cased SILO text, so "implementing" and "implementation" both count.
# "identify", "compare", "state" and the like are left to the model.
DOING_VERBS = (
    "implement", "design", "develop", "build", "construct", "creat", "writ", "program",
    "analys", "evaluat", "explain", "apply", "solv", "model", "test", "debug",
)


def requires_written(silo_text: str) -> bool:
    """The mixed-policy rule: does this SILO's wording ask for doing rather
    than recognising? Pure function so the prompt, the checks and the tests
    read the same rule."""
    text = silo_text.lower()
    return any(verb in text for verb in DOING_VERBS)

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
    format: QuizFormat = DEFAULT_FORMAT

    def expected_kind(self, silo_key: str) -> str | None:
        """What kind an item on this SILO must have under the policy: a fixed
        kind for the single-format policies, "written" for a doing SILO under
        "mixed", None when the model may choose."""
        if self.format == MULTIPLE_CHOICE:
            return MULTIPLE_CHOICE
        if self.format == WRITTEN:
            return WRITTEN
        return WRITTEN if requires_written(self.plan.silo_text.get(silo_key, "")) else None

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
    format: QuizFormat = DEFAULT_FORMAT,
) -> QuizContext:
    """Attach the catalogue's subject info for every subject the plan
    context mentions. Subjects the catalogue does not know are listed with
    their code only, so the page never claims a synopsis it does not have."""
    if items_per_gap < 1:
        raise ValueError("items_per_gap must be at least 1")
    if format not in (MULTIPLE_CHOICE, WRITTEN, "mixed"):
        raise ValueError(f"format must be multiple_choice, written or mixed, not {format!r}")
    subjects_by_code = subjects_by_code or {}
    infos = []
    for code in sorted(plan.known_subjects):
        info = subjects_by_code.get(code)
        infos.append(info if info is not None else SubjectInfo(code=code, title="", year_level=0))
    return QuizContext(plan=plan, subjects=tuple(infos), items_per_gap=items_per_gap, format=format)


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
    kind: Literal["multiple_choice", "written"]  # required: a defaulted field is omitted by the model
    stem: str  # the question, or for a written item the task
    # multiple_choice only
    options: list[str] = Field(default_factory=list, max_length=MAX_OPTIONS)
    correct_index: int | None = Field(default=None, ge=0, lt=MAX_OPTIONS)
    # written only
    model_answer: str = ""  # a full answer a tutor would accept
    marking_points: list[str] = Field(default_factory=list, max_length=MAX_MARKING_POINTS)  # what a good answer must contain
    explanation: str  # why the answer is right, naming the SILO to revisit

    @property
    def is_written(self) -> bool:
        return self.kind == WRITTEN


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


class EducatorNote(BaseModel):
    """One question's blind check: the reviewer's own answer, chosen without
    seeing the author's key, plus a teaching explanation for the student
    and any concern about the question itself."""

    model_config = ConfigDict(extra="forbid")

    question_index: int = Field(ge=0)  # position in QuizDocument.items
    # Both fields are required but nullable: a defaulted field is omitted by
    # the model, and then every written task fails the verdict check.
    # multiple choice: the reviewer's own choice, made without the key; null for a written task
    chosen_index: int | None = Field(ge=0, lt=MAX_OPTIONS)
    # written: the reviewer marks the author's model answer against the marking points; null for multiple choice
    marking_verdict: Literal["meets", "partly", "fails"] | None
    confidence: Literal["high", "medium", "low"]
    teaching_explanation: str  # why the answer is right, why the others are wrong, how it serves the SILO
    concerns: str = ""  # more than one defensible answer, ambiguity, level mismatch; empty if none


class EducatorReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: list[EducatorNote]
    reviewer: str = ""  # the LLM client's describe() string, for provenance


class QuizDocument(BaseModel):
    """What is written to disk and what the dashboard renders: the quiz plus
    the subject info it was shown, so the page can print the same synopsis
    the model saw and nothing more, and the educator review if one ran."""

    model_config = ConfigDict(extra="forbid")

    student_id: str
    introduction: str
    items: list[QuizItem]
    subjects: list[QuizSubject] = []
    educator_review: EducatorReview | None = None

    def note_for(self, index: int) -> EducatorNote | None:
        if self.educator_review is None:
            return None
        return next((n for n in self.educator_review.notes if n.question_index == index), None)

    def agrees(self, index: int) -> bool | None:
        """Multiple choice: whether the blind reviewer chose the author's
        answer. Written: whether the reviewer found the model answer meets
        its marking points. None without a review."""
        note = self.note_for(index)
        if note is None:
            return None
        item = self.items[index]
        if item.is_written:
            return note.marking_verdict == "meets"
        return note.chosen_index == item.correct_index

    @property
    def disagreements(self) -> list[int]:
        return [i for i in range(len(self.items)) if self.agrees(i) is False]

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
        prose += [item.model_answer] + list(item.marking_points)
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


def _item_shape_problems(item: QuizItem) -> list[str]:
    """What each kind must and must not carry."""
    problems: list[str] = []
    if item.is_written:
        if item.options or item.correct_index is not None:
            problems.append("a written task carries no options or correct_index")
        if not item.model_answer.strip():
            problems.append("a written task needs a model_answer")
        points = [m.strip() for m in item.marking_points]
        if any(not m for m in points):
            problems.append("has a blank marking point")
        if not MIN_MARKING_POINTS <= len(points) <= MAX_MARKING_POINTS:
            problems.append(f"has {len(points)} marking point(s); give {MIN_MARKING_POINTS} to {MAX_MARKING_POINTS}")
        return problems
    if item.model_answer.strip() or item.marking_points:
        problems.append("a multiple-choice question carries no model_answer or marking_points")
    cleaned = [o.strip() for o in item.options]
    if not MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS:
        problems.append(f"has {len(cleaned)} option(s); give {MIN_OPTIONS} to {MAX_OPTIONS}")
    if any(not o for o in cleaned):
        problems.append("has a blank option")
    if len(set(cleaned)) != len(cleaned):
        problems.append("repeats an option")
    if item.correct_index is None or not 0 <= item.correct_index < len(cleaned):
        problems.append(f"correct_index {item.correct_index} is outside its {len(cleaned)} options")
    return problems


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
        if not item.explanation.strip():
            problems.append(f"{where} has no explanation")
        expected = context.expected_kind(item.silo_key)
        if expected is not None and item.kind != expected:
            why = (
                f"the quiz format is {context.format}" if context.format != "mixed"
                else f"{item.silo_key} asks the student to do something, so it needs a written task"
            )
            problems.append(f"{where} is {item.kind} but must be {expected}: {why}")
        problems += [f"{where}: {p}" for p in _item_shape_problems(item)]
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

Write questions ONLY for competencies marked "persistent gap" or "isolated gap". Mastery \
estimates are formative signals, never a verdict on the student; the introduction should say the \
quiz is practice, not assessment.

Two kinds of question exist. A multiple_choice question has a stem, 3 or 4 options and a \
correct_index. A written task has a stem that asks the student to produce something -- a short \
explanation, a design, a code fragment, a worked comparison -- plus a model_answer a tutor would \
accept and {min_points} to {max_points} marking_points saying what a good answer must contain. \
{format_policy}

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
4. For multiple_choice: give 3 or 4 options, exactly one correct, correct_index its 0-based \
position, no model_answer or marking_points. Distractors are plausible mistakes, not jokes. Vary \
which position holds the correct answer. For written: no options or correct_index; a model_answer \
of three to eight sentences (or a short code fragment with a sentence of justification), and \
marking_points that a tutor could tick off.
5. explanation says why the answer is right (for multiple choice, why the most tempting distractor \
is wrong; for written, what distinguishes a strong answer from a weak one) and names the silo_key \
to revisit.
6. introduction is one or two sentences on what the quiz covers and that it is practice.
"""


def _format_policy(context: QuizContext) -> str:
    if context.format == MULTIPLE_CHOICE:
        return "The educator has set this quiz to multiple choice only: every question is multiple_choice."
    if context.format == WRITTEN:
        return "The educator has set this quiz to written tasks only: every question is written."
    return (
        "The educator has allowed both kinds. Choose per question from the SILO's wording and the subject: "
        "a SILO that asks the student to DO something (implement, design, develop, build, analyse, evaluate, "
        "explain, apply, solve, write, model, test) MUST get a written task; a SILO about identifying, "
        "comparing, recognising or stating may be either. Each SILO marked \"(written task required)\" below "
        "is one the checks will hold to that rule."
    )


def _render_context(context: QuizContext) -> str:
    plan = context.plan
    lines = [f"Student: {plan.student_id}", "", "Competencies (lowest attainment first):"]
    for c in plan.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject) or "no per-subject evidence"
        lines.append(f"- {c.competency_label}: {c.classification}, attainment {c.attainment_pct:.1f}% (per subject: {per_subject})")
        if c.classification in GAP_KINDS:
            for key in c.silo_keys:
                tag = " (written task required)" if context.expected_kind(key) == WRITTEN and context.format == "mixed" else ""
                lines.append(f"    SILO {key}: {plan.silo_text.get(key, '(wording not available)')}{tag}")
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

    system_prompt = _SYSTEM_PROMPT.format(
        items_per_gap=context.items_per_gap,
        min_points=MIN_MARKING_POINTS,
        max_points=MAX_MARKING_POINTS,
        format_policy=_format_policy(context),
    )
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


# --- Educator review (blind second pass) -----------------------------------
#
# The generator's grounding checks cannot see whether the answer key is
# right. This pass gives a model each question WITHOUT the key, asks it to
# choose and to write the explanation a tutor would, and the code compares
# its choice with the author's. A disagreement does not prove either wrong;
# it tells the educator which question to look at first.

_REVIEW_SYSTEM_PROMPT = """You are a university tutor checking a practice quiz before a student sees it. For \
each question you are given the learning outcome (SILO) it is meant to test, the assessment it is \
pitched at and the subject's handbook synopsis. Questions come in two kinds.

For a MULTIPLE CHOICE question you are given the stem and the options but NOT the author's answer \
key. Choose the correct option yourself (chosen_index, 0-based); leave marking_verdict null. If more \
than one option is defensible, pick the best and say so in concerns.

For a WRITTEN task you are given the stem, the author's model_answer and the marking_points. Act as a \
second marker: does the model answer actually satisfy every marking point, and would the marking \
points let a tutor mark a student's answer fairly? Set marking_verdict to meets, partly or fails; \
leave chosen_index null. Say in concerns what is missing or unfair.

For every question, in order, also give your confidence (high, medium or low) and write \
teaching_explanation for the student: why the answer is right, why the alternatives or common weak \
answers fall short, and what working through this question practises from the named SILO. Three to \
six sentences, plain language, no bullet points. Write concerns if the question has a problem: more \
than one defensible answer, ambiguous wording, a level that does not fit the named assessment, or \
content the SILO does not cover. Leave it empty if there is none.

Rules that are checked automatically: one note per question, question_index copied from the input, \
chosen_index within that question's options for multiple choice, marking_verdict set for written \
tasks, and any subject code or SILO key you mention copied exactly from the input.
"""


def _render_review_context(document: QuizDocument, context: QuizContext) -> str:
    synopsis = {s.code: s for s in context.subjects}
    lines = [f"Student: {document.student_id}", ""]
    for i, item in enumerate(document.items):
        subject = synopsis.get(item.subject_code)
        lines += [
            f"Question {i} (question_index {i}): competency '{item.competency_label}' ({item.gap_kind})",
            f"  Subject {item.subject_code}" + (f" {subject.title}" if subject and subject.title else ""),
            f"  SILO {item.silo_key}: {context.plan.silo_text.get(item.silo_key, '(wording not available)')}",
            f"  Pitched at assessment {item.assessment_key}",
        ]
        if subject and subject.synopsis:
            lines.append(f"  Synopsis: {subject.synopsis}")
        if item.is_written:
            lines += ["  Kind: written task", f"  Task: {item.stem}", f"  Author's model answer: {item.model_answer}"]
            lines += [f"    marking point {j}: {m}" for j, m in enumerate(item.marking_points)]
        else:
            lines += ["  Kind: multiple choice", f"  Stem: {item.stem}"]
            lines += [f"    option {j}: {option}" for j, option in enumerate(item.options)]
        lines.append("")
    return "\n".join(lines)


def review_grounding_checks(review: EducatorReview, document: QuizDocument, context: QuizContext) -> list[ReferenceCheck]:
    prose = "\n".join(n.teaching_explanation + "\n" + n.concerns for n in review.notes)
    return [
        ReferenceCheck(
            "question index",
            [str(n.question_index) for n in review.notes],
            [str(i) for i in range(len(document.items))],
            require_complete=True,
            require_unique=True,
        ),
        ReferenceCheck("SILO mentioned in prose", extract_codes(prose, SILO_KEY_PATTERN), context.plan.known_silos),
        ReferenceCheck("subject mentioned in prose", extract_codes(prose, SUBJECT_CODE_PATTERN), context.known_subjects),
    ]


def review_structure_problems(review: EducatorReview, document: QuizDocument) -> list[str]:
    problems: list[str] = []
    for note in review.notes:
        if not 0 <= note.question_index < len(document.items):
            continue  # reported by the index check
        n = note.question_index + 1
        item = document.items[note.question_index]
        if item.is_written:
            if note.marking_verdict is None:
                problems.append(f"question {n} is a written task; set marking_verdict")
            if note.chosen_index is not None:
                problems.append(f"question {n} is a written task; chosen_index must be null")
        else:
            options = len(item.options)
            if note.chosen_index is None or not 0 <= note.chosen_index < options:
                problems.append(f"question {n}: chosen_index {note.chosen_index} is outside its {options} options")
            if note.marking_verdict is not None:
                problems.append(f"question {n} is multiple choice; marking_verdict must be null")
        if not note.teaching_explanation.strip():
            problems.append(f"question {n} has no teaching explanation")
    return problems


def validate_review(review: EducatorReview, document: QuizDocument, context: QuizContext) -> None:
    artefact = f"educator review of the quiz for {document.student_id}"
    report = check_grounding(artefact, review_grounding_checks(review, document, context))
    structure = review_structure_problems(review, document)
    if report.ok and not structure:
        return
    parts = [p.describe() for p in report.problems] + structure
    raise GroundingError(f"{artefact} failed grounding validation -- " + "; ".join(parts))


def review_quiz(
    client: LLMClient,
    document: QuizDocument,
    context: QuizContext,
    *,
    max_attempts: int = 3,
) -> EducatorReview:
    """Blind second pass. Same generate/validate/retry loop; raises if it
    never grounds. The caller decides whether a failed review blocks the
    quiz (lja.quiz writes the quiz without a review and says so)."""
    base_prompt = _render_review_context(document, context)
    last_error: GroundingError | None = None
    for _attempt in range(1, max_attempts + 1):
        user_prompt = base_prompt
        if last_error is not None:
            user_prompt += f"\n\nYour previous review was rejected: {last_error} Fix every item named there."
        review = client.complete_structured(system=_REVIEW_SYSTEM_PROMPT, user=user_prompt, schema=EducatorReview)
        try:
            validate_review(review, document, context)
            return review.model_copy(update={"reviewer": client.describe()})
        except GroundingError as exc:
            last_error = exc
            continue
    raise GroundingError(
        f"Educator review for {document.student_id} failed grounding validation on all {max_attempts} attempts. "
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
        if item.is_written:
            out += [f"*Written task.* {item.stem}", ""]
        else:
            out += [item.stem, ""]
            out += [f"- {_LETTERS[i]}. {o}" for i, o in enumerate(item.options)]
            out.append("")
    out += ["## Answers", ""]
    for n, item in enumerate(document.items, 1):
        if item.is_written:
            out += [f"**{n}.** Model answer: {item.model_answer}", ""]
            out += ["A good answer must:"] + [f"- {m}" for m in item.marking_points] + ["", item.explanation, ""]
        else:
            out += [f"**{n}.** {_LETTERS[item.correct_index]}. {item.explanation}", ""]
    if document.educator_review is not None:
        review = document.educator_review
        disagree = document.disagreements
        out += ["## Educator notes (blind check)", ""]
        out += [
            f"A second pass ({review.reviewer or 'same model'}) answered each multiple-choice question without "
            f"seeing the key, marked each written model answer against its marking points, and wrote a teaching "
            f"explanation. "
            + (f"It disagreed on question(s) {', '.join(str(i + 1) for i in disagree)}; check those first."
               if disagree else "It agreed with the author on every question."),
            "",
        ]
        for n, item in enumerate(document.items, 1):
            note = document.note_for(n - 1)
            if note is None:
                out += [f"**{n}.** No note.", ""]
                continue
            if item.is_written:
                out += [f"**{n}.** Second marker: model answer {note.marking_verdict} its marking points ({note.confidence} confidence).", ""]
            else:
                verdict = "agrees" if note.chosen_index == item.correct_index else "DISAGREES"
                out += [f"**{n}.** Blind answer {_LETTERS[note.chosen_index]} ({note.confidence} confidence), {verdict} with the key.", ""]
            out += [note.teaching_explanation, ""]
            if note.concerns.strip():
                out += [f"*Concern:* {note.concerns}", ""]
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
