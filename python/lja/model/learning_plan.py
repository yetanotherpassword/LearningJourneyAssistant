"""Personalised learning-plan generation (S4-6) -- the first LLM feature
built on top of the gap output, and the first consumer of the shared
grounding validator in lja/llm/grounding.py (S4-3).

The proposal's hard constraint, restated as tender requirement 6: a plan
may only ever name SILOs, subjects, assessments and competencies that were
in its input. That is enforced here in three layers, because a prompt
instruction alone is not a guarantee (silo_clustering.py has the live
evidence for that):

1. The plan's schema puts every reference in an explicit field
   (competency_label, silo_keys, subject_codes, assessment_keys) so there
   is something concrete to check, not just prose.
2. Every one of those fields is validated against the exact set of names
   the student's context contained. Prose fields are additionally scanned
   for inline subject codes and SILO keys, so "revise CSE9XYZ" in a
   sentence is caught too.
3. A failed plan is retried with the validation errors quoted back to the
   model, and if every attempt fails the call raises. Nothing ungrounded
   is ever returned -- the build fails, as the requirement says.

What goes into the context is deliberately narrow: this student's
competency classifications from compute_gaps(), the per-subject evidence
behind each one (gap_evidence.subject_breakdown), the SILO wording for the
competencies' members, and this student's own assessment scores and marker
feedback. No cohort data, no other students. The plan can therefore only
be as good as the gap output -- see docs/adr/0001 and the flat-profile
finding for what that output can and cannot currently show.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from ..data.excel_loader import LjaDataset
from ..llm.base import LLMClient
from ..llm.grounding import (
    SILO_KEY_PATTERN,
    SUBJECT_CODE_PATTERN,
    GroundingError,
    ReferenceCheck,
    check_grounding,
    extract_codes,
)
from .gap_detection import CompetencyGap, build_silo_to_competency_map
from .gap_evidence import describe_trend, future_subjects_sharing_competency, subject_breakdown
from .silo_clustering import SiloClusteringResult

# --- Output schema ---------------------------------------------------------
# extra="forbid" on every model: required by the Anthropic structured-output
# endpoint (see silo_clustering.py), and it also means a model cannot smuggle
# an unchecked field past validation.


class PlanPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_label: str
    silo_keys: list[str]  # "SUBJECT:SILOn" -- exactly the keys given in the context
    subject_codes: list[str]
    assessment_keys: list[str]  # "SUBJECT:Assessment name" -- assessments worth revisiting
    evidence: str  # why this is a priority, citing the student's own results and feedback
    actions: str  # what the student should actually do


class LearningPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str
    summary: str
    priorities: list[PlanPriority]
    strengths_to_build_on: list[str] = []  # competency labels, from the context


# --- Input context ---------------------------------------------------------


@dataclass(frozen=True)
class AssessmentEvidence:
    key: str  # "SUBJECT:Assessment name"
    subject_code: str
    assessment_name: str
    score: float
    weight: float
    silo_keys: tuple[str, ...]
    feedback_comment: str


@dataclass(frozen=True)
class CompetencyContext:
    competency_label: str
    classification: str
    attainment_pct: float
    silo_keys: tuple[str, ...]
    per_subject: tuple[tuple[str, float], ...]  # (subject_code, attainment_pct) in year order where known
    trend: str
    future_subjects: tuple[str, ...]


@dataclass(frozen=True)
class PlanContext:
    """Everything the model is shown for one student, and therefore the
    complete vocabulary the plan is allowed to use. The `known_*` sets are
    derived from the same records that are rendered into the prompt, so the
    validator and the prompt cannot drift apart.
    """

    student_id: str
    competencies: tuple[CompetencyContext, ...]
    silo_text: dict[str, str] = field(default_factory=dict)  # "SUBJECT:SILOn" -> wording
    assessments: tuple[AssessmentEvidence, ...] = ()

    @property
    def known_competencies(self) -> frozenset[str]:
        return frozenset(c.competency_label for c in self.competencies)

    @property
    def known_silos(self) -> frozenset[str]:
        return frozenset(self.silo_text.keys())

    @property
    def known_subjects(self) -> frozenset[str]:
        subjects = {s for c in self.competencies for s, _ in c.per_subject}
        subjects.update(s for c in self.competencies for s in c.future_subjects)
        subjects.update(a.subject_code for a in self.assessments)
        subjects.update(key.split(":", 1)[0] for key in self.silo_text)
        return frozenset(subjects)

    @property
    def known_assessments(self) -> frozenset[str]:
        return frozenset(a.key for a in self.assessments)


def build_plan_context(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    gaps: list[CompetencyGap],
    student_id: str,
) -> PlanContext:
    """Assemble one student's evidence from the pipeline's existing outputs.
    Raises ValueError for a student with no gap rows -- a plan for someone
    the gap engine has nothing to say about would be pure invention.
    """
    student_gaps = sorted((g for g in gaps if g.student_id == student_id), key=lambda g: g.attainment_pct)
    if not student_gaps:
        raise ValueError(f"No gap rows for student {student_id!r}; cannot build a grounded plan.")

    members_by_label: dict[str, list[str]] = defaultdict(list)
    for cluster in clustering.clusters:
        for m in cluster.members:
            members_by_label[cluster.competency_label].append(f"{m.subject_code}:{m.silo_local_id}")

    competencies: list[CompetencyContext] = []
    silo_text: dict[str, str] = {}
    for gap in student_gaps:
        breakdown = subject_breakdown(dataset, clustering, student_id, gap.competency_label)
        silo_keys = tuple(members_by_label.get(gap.competency_label, ()))
        for key in silo_keys:
            silo = dataset.silos.get(key)
            if silo is not None:
                silo_text[key] = silo.text
        competencies.append(
            CompetencyContext(
                competency_label=gap.competency_label,
                classification=gap.classification,
                attainment_pct=gap.attainment_pct,
                silo_keys=silo_keys,
                per_subject=tuple((e.subject_code, e.attainment_pct) for e in breakdown),
                trend=describe_trend(breakdown),
                future_subjects=tuple(
                    future_subjects_sharing_competency(dataset, clustering, student_id, gap.competency_label)
                ),
            )
        )

    silo_to_competency = build_silo_to_competency_map(clustering)
    assessments: list[AssessmentEvidence] = []
    for row in dataset.results:
        if row.student_id != student_id:
            continue
        silo_keys = tuple(f"{row.subject_code}:{s}" for s in row.silo_ids if f"{row.subject_code}:{s}" in silo_to_competency)
        assessments.append(
            AssessmentEvidence(
                key=f"{row.subject_code}:{row.assessment_name}",
                subject_code=row.subject_code,
                assessment_name=row.assessment_name,
                score=row.score,
                weight=row.weight,
                silo_keys=silo_keys,
                feedback_comment=row.feedback_comment,
            )
        )
    assessments.sort(key=lambda a: (a.subject_code, a.assessment_name))

    return PlanContext(
        student_id=student_id,
        competencies=tuple(competencies),
        silo_text=silo_text,
        assessments=tuple(assessments),
    )


# --- Grounding -------------------------------------------------------------

_PROSE_FIELDS = ("summary",)
_PRIORITY_PROSE_FIELDS = ("evidence", "actions")


def plan_grounding_checks(plan: LearningPlan, context: PlanContext) -> list[ReferenceCheck]:
    """The full set of checks a plan must pass. Kept separate from the
    generator so the grounding test suite can exercise it directly on
    hand-written plans, and so a stored plan can be re-validated later.
    """
    prose = [getattr(plan, f) for f in _PROSE_FIELDS]
    prose += [getattr(p, f) for p in plan.priorities for f in _PRIORITY_PROSE_FIELDS]
    prose_text = "\n".join(prose)

    priority_labels = [p.competency_label for p in plan.priorities]
    return [
        ReferenceCheck("student", [plan.student_id], [context.student_id]),
        ReferenceCheck("competency", priority_labels, context.known_competencies, require_unique=True),
        ReferenceCheck("strength competency", plan.strengths_to_build_on, context.known_competencies),
        ReferenceCheck("SILO", [k for p in plan.priorities for k in p.silo_keys], context.known_silos),
        ReferenceCheck("subject", [s for p in plan.priorities for s in p.subject_codes], context.known_subjects),
        ReferenceCheck("assessment", [a for p in plan.priorities for a in p.assessment_keys], context.known_assessments),
        ReferenceCheck("SILO mentioned in prose", extract_codes(prose_text, SILO_KEY_PATTERN), context.known_silos),
        ReferenceCheck("subject mentioned in prose", extract_codes(prose_text, SUBJECT_CODE_PATTERN), context.known_subjects),
    ]


def validate_plan(plan: LearningPlan, context: PlanContext) -> None:
    """Raise GroundingError if the plan names anything its context did not
    contain. Every problem is listed at once so a retry can fix them all.
    """
    check_grounding(f"learning plan for {context.student_id}", plan_grounding_checks(plan, context)).raise_if_failed()


# --- Prompt ----------------------------------------------------------------

_SYSTEM_PROMPT = """You are helping a university student understand their own learning and decide \
what to work on next. You will be given ONE student's results: how they have attained each \
cross-subject competency, the evidence behind that per subject, the wording of the learning \
outcomes (SILOs) each competency is built from, and their own assessment scores and marker \
feedback.

Write a short, honest, encouraging learning plan. Mastery estimates here are formative \
signals to guide study, never a verdict on the student and never a reason to avoid a subject.

Rules that are checked automatically -- a plan that breaks them is rejected and you will be \
asked again:

1. Use ONLY the competency labels, SILO keys (e.g. CSE1OOF:SILO2), subject codes and \
assessment keys (e.g. CSE1OOF:Test) that appear in the input below, copied exactly. Do not \
invent, rename, abbreviate or reformat any of them. If you want to mention a subject or SILO \
in a sentence, use its exact key.
2. Each priority must name a competency from the input, at most once across the plan. List \
in silo_keys only SILO keys shown under that competency, in subject_codes only subjects that \
evidence it or will in future, and in assessment_keys only the student's own assessments shown \
below.
3. Ground every claim in the numbers and feedback you were given. The evidence field must \
refer to the student's actual attainment, per-subject figures, trend or marker comments. Do \
not speculate about causes you cannot see in the data.
4. Prioritise competencies classified as a gap first, then the lowest attainment. Two to four \
priorities is usually right; a strong profile may need only one. strengths_to_build_on lists \
competency labels from the input the student is doing well in, if any.
5. Actions must be concrete things the student can do -- revisit a named assessment's \
feedback, re-attempt a specific kind of exercise tied to a named SILO -- not generic advice.
"""


def _render_context(context: PlanContext) -> str:
    lines = [f"Student: {context.student_id}", "", "Competencies (lowest attainment first):"]
    for c in context.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject) or "no per-subject evidence"
        future = f"; not yet taken but also assesses this: {', '.join(c.future_subjects)}" if c.future_subjects else ""
        lines.append(
            f"- {c.competency_label}: {c.classification}, attainment {c.attainment_pct:.1f}% "
            f"(per subject: {per_subject}; trend across subjects: {c.trend}{future})"
        )
        for key in c.silo_keys:
            lines.append(f"    SILO {key}: {context.silo_text.get(key, '(wording not available)')}")
    lines += ["", "This student's assessments (score is a percentage; feedback is the marker's comment):"]
    for a in context.assessments:
        silos = ", ".join(a.silo_keys) or "no clustered SILO"
        feedback = a.feedback_comment.strip() or "(no feedback recorded)"
        lines.append(f"- {a.key}: {a.score:.1f}%, weight {a.weight:g}, SILOs {silos}. Feedback: {feedback}")
    return "\n".join(lines)


# --- Generation ------------------------------------------------------------


def generate_learning_plan(
    client: LLMClient,
    context: PlanContext,
    *,
    max_attempts: int = 3,
    extra_instructions: str | None = None,
) -> LearningPlan:
    """Generate, validate, retry -- the same loop as cluster_silos(), for the
    same reason: one ungrounded sample from a model that is usually fine is
    worth a retry with the specific errors quoted back. If every attempt
    fails, raise: an ungrounded plan is never returned.
    """
    system_prompt = _SYSTEM_PROMPT
    if extra_instructions:
        system_prompt = f"{system_prompt}\n\n{extra_instructions}"
    base_prompt = _render_context(context)

    last_error: GroundingError | None = None
    for _attempt in range(1, max_attempts + 1):
        user_prompt = base_prompt
        if last_error is not None:
            user_prompt += (
                f"\n\nYour previous plan was rejected by the grounding check: {last_error} "
                "Fix every item named there. Every label, key and code must be copied exactly "
                "from the input above; remove anything that is not in it."
            )
        plan = client.complete_structured(system=system_prompt, user=user_prompt, schema=LearningPlan)
        try:
            validate_plan(plan, context)
            return plan
        except GroundingError as exc:
            last_error = exc
            continue

    raise GroundingError(
        f"Learning plan for {context.student_id} failed grounding validation on all {max_attempts} attempts. "
        f"Last error: {last_error}"
    ) from last_error


# --- Rendering -------------------------------------------------------------


def render_markdown(plan: LearningPlan, context: PlanContext) -> str:
    """A readable version of the plan, with the evidence table alongside so
    a reader can check any claim against the numbers it was grounded in.
    """
    out = [f"# Learning plan for {plan.student_id}", "", plan.summary, ""]
    for i, p in enumerate(plan.priorities, 1):
        out.append(f"## {i}. {p.competency_label}")
        out.append("")
        out.append(f"**Evidence.** {p.evidence}")
        out.append("")
        out.append(f"**Actions.** {p.actions}")
        out.append("")
        if p.silo_keys:
            out.append("Learning outcomes involved:")
            for key in p.silo_keys:
                out.append(f"- `{key}` -- {context.silo_text.get(key, '')}")
            out.append("")
        if p.assessment_keys:
            out.append(f"Assessments to revisit: {', '.join(f'`{k}`' for k in p.assessment_keys)}")
            out.append("")
    if plan.strengths_to_build_on:
        out.append("## Strengths to build on")
        out.append("")
        out.extend(f"- {label}" for label in plan.strengths_to_build_on)
        out.append("")
    out.append("## The evidence this plan was grounded in")
    out.append("")
    out.append("| Competency | Classification | Attainment | Per subject | Trend |")
    out.append("| --- | --- | --- | --- | --- |")
    for c in context.competencies:
        per_subject = ", ".join(f"{s} {pct:.1f}%" for s, pct in c.per_subject)
        out.append(f"| {c.competency_label} | {c.classification} | {c.attainment_pct:.1f}% | {per_subject} | {c.trend} |")
    out.append("")
    return "\n".join(out)
