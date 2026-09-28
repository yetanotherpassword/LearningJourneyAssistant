"""Personalised study-strategy recommendations (IOLG-123).

A learning plan (learning_plan.py) says WHAT to work on. A study strategy
says HOW to study it: for every competency the gap engine classified as a
gap, which evidence-based study techniques to use, applied to which of the
student's own SILOs and assessments, on what schedule, and how the student
will know it worked.

It mirrors learning_plan.py on purpose -- same context, same fail-closed
generate/validate/retry loop, same grounding checks -- and adds one thing
the plan does not have: rules that make the two kinds of gap produce
structurally different strategies, checked in code rather than asked for
in the prompt.

- A PERSISTENT gap shows in two or more subjects, so it is a habit or a
  foundation problem rather than one bad assessment. Its strategy must name
  at least two of the subjects that evidence it and must use a technique
  that works ACROSS subjects over time: interleaving or spaced practice.
- An ISOLATED gap shows in one subject only, so it is local. Its strategy
  must stay in that subject and must include feedback review: rework the
  named assessment against the marker's comment.

Techniques come from a closed list (STUDY_TECHNIQUES) rather than free
text, so a model cannot recommend something that sounds plausible but has
no evidence behind it. The list is the six strategies in Weinstein, Madan
and Sumeracki (2018), "Teaching the science of learning", Cognitive Research:
Principles and Implications 3:2, plus worked examples and feedback review,
which fit how this dataset records assessments. Retrieval practice and
spaced practice are the two Dunlosky et al. (2013) rate highest.

Grounding, as for plans (tender requirement 6): every competency, subject,
assessment and SILO in a strategy must be one the student's own context
contained, and each is checked against the competency it is filed under,
not just against the student as a whole. Prose fields are scanned for
inline codes. A strategy that fails is retried with the problems quoted
back, and if it never grounds the generator raises; nothing ungrounded is
returned.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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

# The same context as a learning plan: this student's competencies, the
# per-subject evidence, SILO wording and their own assessments. Reusing it
# keeps the two artefacts' vocabularies identical.
StrategyContext = PlanContext

# --- Techniques ------------------------------------------------------------

Technique = Literal[
    "spaced practice",
    "retrieval practice",
    "interleaving",
    "elaboration",
    "concrete examples",
    "dual coding",
    "worked examples",
    "feedback review",
]

STUDY_TECHNIQUES: dict[str, str] = {
    "spaced practice": "Spread study of the same material over several short sessions on different days instead of one long one.",
    "retrieval practice": "Recall the material from memory -- self-test, write out what you know, then check -- rather than re-reading.",
    "interleaving": "Mix problems from different topics or subjects in one session, so you practise choosing the method as well as using it.",
    "elaboration": "Explain how and why an idea works and how it connects to what you already know.",
    "concrete examples": "Tie each abstract idea to specific, varied examples, and say what the examples have in common.",
    "dual coding": "Pair words with a visual -- a diagram, timeline or flowchart -- and explain one in terms of the other.",
    "worked examples": "Study a fully solved example step by step, then solve a similar problem yourself without looking.",
    "feedback review": "Rework the marked assessment against the marker's comment until you can do what the comment asked for.",
}

# What each kind of gap must include. Kept as data so the prompt, the
# validator and the tests all read the same rule.
PERSISTENT_REQUIRES_ONE_OF = ("interleaving", "spaced practice")
ISOLATED_REQUIRES = "feedback review"
GAP_KINDS = (PERSISTENT_GAP, ISOLATED_GAP)

# --- Output schema ---------------------------------------------------------
# extra="forbid" for the same reasons as learning_plan.py.


class StrategyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_label: str
    gap_kind: Literal["persistent gap", "isolated gap"]
    subject_codes: list[str]  # subjects where this gap shows in the student's results
    assessment_keys: list[str]  # "SUBJECT:Assessment name" -- this student's assessments that evidence it
    silo_keys: list[str]  # "SUBJECT:SILOn" -- the outcomes to study
    evidence: str  # why this is a gap for this student, from their numbers and feedback
    techniques: list[Technique]
    how_to_apply: str  # the techniques applied to the named SILOs and assessments
    schedule: str  # when and how often
    check_progress: str  # how the student will know it is working
    prepare_for: list[str] = []  # subjects not yet taken that also assess this competency


class StudyStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str
    overview: str
    entries: list[StrategyEntry]


# --- Context helpers -------------------------------------------------------


def gap_competencies(context: StrategyContext) -> tuple[CompetencyContext, ...]:
    """The competencies a strategy must cover: every isolated or persistent
    gap, and nothing else."""
    return tuple(c for c in context.competencies if c.classification in GAP_KINDS)


def evidencing_subjects(competency: CompetencyContext) -> frozenset[str]:
    return frozenset(s for s, _ in competency.per_subject)


def assessments_for(context: StrategyContext, competency: CompetencyContext) -> frozenset[str]:
    """This student's assessments that cover at least one of the
    competency's SILOs -- the only assessments a strategy may cite for it."""
    silos = set(competency.silo_keys)
    return frozenset(a.key for a in context.assessments if silos & set(a.silo_keys))


def has_gaps(context: StrategyContext) -> bool:
    return bool(gap_competencies(context))


# --- Grounding -------------------------------------------------------------

_ENTRY_PROSE_FIELDS = ("evidence", "how_to_apply", "schedule", "check_progress")


def strategy_grounding_checks(strategy: StudyStrategy, context: StrategyContext) -> list[ReferenceCheck]:
    """Name checks: every reference must come from the context, filed under
    the right competency. Separate from the structural rules so each can be
    tested on its own."""
    gaps = {c.competency_label: c for c in gap_competencies(context)}
    prose = [strategy.overview] + [getattr(e, f) for e in strategy.entries for f in _ENTRY_PROSE_FIELDS]
    prose_text = "\n".join(prose)

    checks = [
        ReferenceCheck("student", [strategy.student_id], [context.student_id]),
        # Exactly one entry per gap: none missing, none twice, none for a
        # competency that is not a gap.
        ReferenceCheck(
            "gap competency",
            [e.competency_label for e in strategy.entries],
            gaps.keys(),
            require_complete=True,
            require_unique=True,
        ),
        ReferenceCheck(
            "gap classification",
            [f"{e.competency_label} = {e.gap_kind}" for e in strategy.entries],
            [f"{label} = {c.classification}" for label, c in gaps.items()],
        ),
        ReferenceCheck("SILO mentioned in prose", extract_codes(prose_text, SILO_KEY_PATTERN), context.known_silos),
        ReferenceCheck("subject mentioned in prose", extract_codes(prose_text, SUBJECT_CODE_PATTERN), context.known_subjects),
    ]
    for entry in strategy.entries:
        competency = gaps.get(entry.competency_label)
        if competency is None:
            continue  # already reported by the gap-competency check
        label = entry.competency_label
        checks += [
            ReferenceCheck(f"subject evidencing '{label}'", entry.subject_codes, evidencing_subjects(competency), require_unique=True),
            ReferenceCheck(f"assessment evidencing '{label}'", entry.assessment_keys, assessments_for(context, competency), require_unique=True),
            ReferenceCheck(f"SILO in '{label}'", entry.silo_keys, competency.silo_keys, require_unique=True),
            ReferenceCheck(f"future subject for '{label}'", entry.prepare_for, competency.future_subjects, require_unique=True),
            ReferenceCheck(f"technique for '{label}'", entry.techniques, STUDY_TECHNIQUES.keys(), require_unique=True),
        ]
    return checks


def strategy_structure_problems(strategy: StudyStrategy, context: StrategyContext) -> list[str]:
    """The rules that make persistent and isolated strategies different in
    kind, plus the minimum every entry must cite. Returns plain sentences,
    quoted back to the model on retry."""
    gaps = {c.competency_label: c for c in gap_competencies(context)}
    problems: list[str] = []
    for entry in strategy.entries:
        competency = gaps.get(entry.competency_label)
        if competency is None:
            continue
        label = entry.competency_label
        if not entry.assessment_keys:
            problems.append(f"'{label}' cites no assessment; name at least one of the student's assessments that evidence it")
        if not entry.silo_keys:
            problems.append(f"'{label}' names no SILO; name the outcomes to study")
        if not entry.techniques:
            problems.append(f"'{label}' lists no technique")
        # Structure follows the context's classification, not the entry's
        # own gap_kind, so a mislabelled entry cannot dodge its rules.
        if competency.classification == PERSISTENT_GAP:
            available = evidencing_subjects(competency)
            if len(set(entry.subject_codes)) < min(2, len(available)):
                problems.append(
                    f"'{label}' is a persistent gap but names {len(set(entry.subject_codes))} subject(s); "
                    f"name at least two of {sorted(available)}"
                )
            if not set(entry.techniques) & set(PERSISTENT_REQUIRES_ONE_OF):
                problems.append(
                    f"'{label}' is a persistent gap; include {' or '.join(PERSISTENT_REQUIRES_ONE_OF)} "
                    "so practice connects the subjects over time"
                )
        elif competency.classification == ISOLATED_GAP:
            if ISOLATED_REQUIRES not in entry.techniques:
                problems.append(f"'{label}' is an isolated gap; include {ISOLATED_REQUIRES} on the named assessment")
    return problems


def validate_strategy(strategy: StudyStrategy, context: StrategyContext) -> None:
    """Raise GroundingError listing every name and structure problem at once."""
    artefact = f"study strategy for {context.student_id}"
    report = check_grounding(artefact, strategy_grounding_checks(strategy, context))
    structure = strategy_structure_problems(strategy, context)
    if report.ok and not structure:
        return
    parts = [p.describe() for p in report.problems] + structure
    raise GroundingError(f"{artefact} failed grounding validation -- " + "; ".join(parts))


# --- Prompt ----------------------------------------------------------------


def _technique_list() -> str:
    return "\n".join(f"- {name}: {text}" for name, text in STUDY_TECHNIQUES.items())


_SYSTEM_PROMPT = f"""You are a university learning adviser helping ONE student decide how to study. \
You will be given their results: how they attain each cross-subject competency, which of those are \
gaps, the evidence per subject, the wording of the learning outcomes (SILOs) involved, and their own \
assessment scores and marker feedback.

Write a study strategy: for each gap, HOW to study -- which techniques, applied to which outcomes \
and assessments, when, and how the student will know it is working. Mastery estimates are formative \
signals, never a verdict on the student.

Choose techniques ONLY from this list, using the names exactly:
{_technique_list()}

Rules that are checked automatically -- a strategy that breaks them is rejected and you will be asked again:

1. Write exactly one entry for every competency marked "persistent gap" or "isolated gap", and no \
entry for any other competency. Copy gap_kind from the input.
2. Use ONLY competency labels, subject codes, SILO keys (e.g. CSE1OOF:SILO2) and assessment keys \
(e.g. CSE1OOF:Test) that appear in the input, copied exactly. In an entry, subject_codes, \
assessment_keys and silo_keys must belong to THAT competency: subjects listed in its per-subject \
evidence, assessments of this student that cover its SILOs, SILOs listed under it. prepare_for may \
only name subjects listed as "not yet taken but also assesses this". If a sentence mentions a subject \
or SILO, use its exact key.
3. A persistent gap shows in two or more subjects, so treat it as a foundation to rebuild across \
subjects: name at least two of its subjects and include interleaving or spaced practice. An isolated \
gap shows in one subject, so keep it local: stay in that subject and include feedback review on the \
named assessment.
4. Every entry cites at least one assessment and one SILO. evidence must refer to the student's \
actual figures or marker comments. how_to_apply must say what to do with which SILO or assessment -- \
not generic advice. schedule is concrete (sessions, spacing, before which assessment or subject). \
check_progress says how the student can tell it is working, e.g. a self-test they can now pass.
5. overview is two or three sentences on the overall approach.
"""


def _render_context(context: StrategyContext) -> str:
    lines = [f"Student: {context.student_id}", "", "Competencies (lowest attainment first):"]
    for c in context.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject) or "no per-subject evidence"
        future = f"; not yet taken but also assesses this: {', '.join(c.future_subjects)}" if c.future_subjects else ""
        lines.append(
            f"- {c.competency_label}: {c.classification}, attainment {c.attainment_pct:.1f}% "
            f"(per subject: {per_subject}; trend across subjects: {c.trend}{future})"
        )
        if c.classification in GAP_KINDS:
            for key in c.silo_keys:
                lines.append(f"    SILO {key}: {context.silo_text.get(key, '(wording not available)')}")
            covering = sorted(assessments_for(context, c))
            lines.append(f"    Assessments covering it: {', '.join(covering) or 'none'}")
    lines += ["", "This student's assessments (score is a percentage; feedback is the marker's comment):"]
    for a in context.assessments:
        silos = ", ".join(a.silo_keys) or "no clustered SILO"
        feedback = a.feedback_comment.strip() or "(no feedback recorded)"
        lines.append(f"- {a.key}: {a.score:.1f}%, weight {a.weight:g}, SILOs {silos}. Feedback: {feedback}")
    return "\n".join(lines)


# --- Generation ------------------------------------------------------------


def generate_study_strategy(
    client: LLMClient,
    context: StrategyContext,
    *,
    max_attempts: int = 3,
    extra_instructions: str | None = None,
) -> StudyStrategy:
    """Generate, validate, retry with the problems quoted back; raise if it
    never grounds. Raises ValueError up front for a student with no gaps --
    a strategy for nothing would be pure invention."""
    if not has_gaps(context):
        raise ValueError(f"Student {context.student_id} has no isolated or persistent gap; no study strategy is needed.")

    system_prompt = _SYSTEM_PROMPT
    if extra_instructions:
        system_prompt = f"{system_prompt}\n\n{extra_instructions}"
    base_prompt = _render_context(context)

    last_error: GroundingError | None = None
    for _attempt in range(1, max_attempts + 1):
        user_prompt = base_prompt
        if last_error is not None:
            user_prompt += (
                f"\n\nYour previous strategy was rejected: {last_error} "
                "Fix every item named there. Copy every label, key and code exactly from the input above."
            )
        strategy = client.complete_structured(system=system_prompt, user=user_prompt, schema=StudyStrategy)
        try:
            validate_strategy(strategy, context)
            return strategy
        except GroundingError as exc:
            last_error = exc
            continue

    raise GroundingError(
        f"Study strategy for {context.student_id} failed grounding validation on all {max_attempts} attempts. "
        f"Last error: {last_error}"
    ) from last_error


# --- Rendering -------------------------------------------------------------


def render_markdown(strategy: StudyStrategy, context: StrategyContext) -> str:
    """Readable strategy with the technique definitions and the evidence it
    was grounded in, so a reader can check any claim against the numbers."""
    out = [f"# Study strategy for {strategy.student_id}", "", strategy.overview, ""]
    used: list[str] = []
    for i, e in enumerate(strategy.entries, 1):
        kind = "Persistent gap: shows across subjects" if e.gap_kind == PERSISTENT_GAP else "Isolated gap: one subject"
        out += [f"## {i}. {e.competency_label}", "", f"*{kind}* ({', '.join(e.subject_codes)})", ""]
        out += [f"**Why.** {e.evidence}", ""]
        out += [f"**Techniques.** {', '.join(e.techniques)}", ""]
        out += [f"**How.** {e.how_to_apply}", ""]
        out += [f"**When.** {e.schedule}", ""]
        out += [f"**How you will know it is working.** {e.check_progress}", ""]
        if e.silo_keys:
            out.append("Outcomes to study:")
            out += [f"- `{k}` -- {context.silo_text.get(k, '')}" for k in e.silo_keys]
            out.append("")
        out += [f"Assessments: {', '.join(f'`{k}`' for k in e.assessment_keys)}", ""]
        if e.prepare_for:
            out += [f"Also prepares you for: {', '.join(e.prepare_for)}", ""]
        used += [t for t in e.techniques if t not in used]
    if used:
        out += ["## The techniques", ""]
        out += [f"- **{t}.** {STUDY_TECHNIQUES[t]}" for t in used]
        out.append("")
    out += ["## The evidence this strategy was grounded in", "", "| Competency | Classification | Attainment | Per subject |", "| --- | --- | --- | --- |"]
    for c in context.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject)
        out.append(f"| {c.competency_label} | {c.classification} | {c.attainment_pct:.1f}% | {per_subject} |")
    out.append("")
    return "\n".join(out)
