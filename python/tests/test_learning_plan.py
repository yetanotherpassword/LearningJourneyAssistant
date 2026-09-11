"""Grounding test suite for learning-plan generation (S4-6).

The sprint plan's M3 row is explicit: the anti-hallucination constraint
"needs a test, not just a prompt instruction". So this file is the
requirement-6 evidence: a plan that names any SILO, subject, assessment or
competency not in its input is rejected, retried, and if it never grounds
the generator raises rather than returning it. A scripted fake LLMClient
keeps it offline and deterministic, the same pattern as
test_silo_clustering.py.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lja.data.excel_loader import Assessment, LjaDataset, ResultRow, Silo, StudentSummary
from lja.llm.grounding import GroundingError
from lja.model.gap_detection import CompetencyGap
from lja.model.learning_plan import (
    LearningPlan,
    PlanPriority,
    build_plan_context,
    generate_learning_plan,
    render_markdown,
    validate_plan,
)
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef

STUDENT = "S001"


class _FakeLLMClient:
    def __init__(self, *results: LearningPlan) -> None:
        self._results = list(results)
        self.call_count = 0
        self.users_seen: list[str] = []

    def complete_structured(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        assert schema is LearningPlan
        index = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        self.users_seen.append(user)
        return self._results[index]

    def describe(self) -> str:
        return "fake"

    def usage_summary(self) -> str:
        return "none"


def _dataset() -> LjaDataset:
    silos = {
        "CSE1OOF:SILO1": Silo("CSE1OOF", "SILO1", "write object-oriented programs"),
        "CSE2ALG:SILO1": Silo("CSE2ALG", "SILO1", "implement data structures"),
        "CSE2ALG:SILO2": Silo("CSE2ALG", "SILO2", "analyse algorithm complexity"),
        "CSE3CAP:SILO1": Silo("CSE3CAP", "SILO1", "deliver a software project in a team"),
    }
    assessments = [
        Assessment("CSE1OOF", "Test", 20.0, "Individual", True, False, ("SILO1",)),
        Assessment("CSE2ALG", "Assignment 1", 30.0, "Individual", False, False, ("SILO1", "SILO2")),
        Assessment("CSE3CAP", "Project", 60.0, "Group", False, True, ("SILO1",)),
    ]
    results = [
        ResultRow(STUDENT, "CSE1OOF", "Test", 55.0, "Encapsulation is shaky.", 20.0, 11.0, ("SILO1",)),
        ResultRow(STUDENT, "CSE2ALG", "Assignment 1", 48.0, "Linked list bugs; complexity fine.", 30.0, 14.4, ("SILO1", "SILO2")),
        ResultRow(STUDENT, "CSE3CAP", "Project", 82.0, "Strong teamwork.", 60.0, 49.2, ("SILO1",)),
        # Another student's row must never leak into S001's context.
        ResultRow("S002", "CSE1OOF", "Test", 95.0, "Excellent.", 20.0, 19.0, ("SILO1",)),
    ]
    summaries = [
        StudentSummary(STUDENT, {"CSE1OOF": 55.0, "CSE2ALG": 48.0, "CSE3CAP": 82.0}, 61.7, "Pass"),
        StudentSummary("S002", {"CSE1OOF": 95.0}, 95.0, "HD"),
    ]
    return LjaDataset(silos=silos, assessments=assessments, results=results, student_summaries=summaries)


def _clustering() -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Data Structures",
                rationale="test",
                members=[SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1"), SiloRef(subject_code="CSE2ALG", silo_local_id="SILO1")],
            ),
            CompetencyCluster(
                competency_label="Algorithm Analysis",
                rationale="test",
                members=[SiloRef(subject_code="CSE2ALG", silo_local_id="SILO2")],
            ),
            CompetencyCluster(
                competency_label="Project Delivery",
                rationale="test",
                members=[SiloRef(subject_code="CSE3CAP", silo_local_id="SILO1")],
            ),
        ]
    )


def _gaps() -> list[CompetencyGap]:
    def gap(label: str, pct: float, classification: str, subjects: int) -> CompetencyGap:
        return CompetencyGap(STUDENT, label, pct, subjects, subjects, classification, "test", None)

    return [
        gap("Data Structures", 50.8, "persistent gap", 2),
        gap("Algorithm Analysis", 48.0, "isolated gap", 1),
        gap("Project Delivery", 82.0, "proficient", 1),
        CompetencyGap("S002", "Data Structures", 95.0, 1, 1, "proficient", "test", None),
    ]


def _context():
    return build_plan_context(_dataset(), _clustering(), _gaps(), STUDENT)


def _good_plan() -> LearningPlan:
    return LearningPlan(
        student_id=STUDENT,
        summary="Data structures need work across CSE1OOF and CSE2ALG; project delivery is a strength.",
        priorities=[
            PlanPriority(
                competency_label="Data Structures",
                silo_keys=["CSE1OOF:SILO1", "CSE2ALG:SILO1"],
                subject_codes=["CSE1OOF", "CSE2ALG"],
                assessment_keys=["CSE2ALG:Assignment 1"],
                evidence="Attainment 50.8%: CSE1OOF 55.0% and CSE2ALG 48.0%; feedback mentions linked list bugs.",
                actions="Re-implement the linked list from CSE2ALG:Assignment 1 with tests before the next assessment.",
            )
        ],
        strengths_to_build_on=["Project Delivery"],
    )


# --- context ---------------------------------------------------------------


def test_context_contains_only_this_students_evidence_lowest_first() -> None:
    ctx = _context()
    assert [c.competency_label for c in ctx.competencies] == ["Algorithm Analysis", "Data Structures", "Project Delivery"]
    assert {a.key for a in ctx.assessments} == {"CSE1OOF:Test", "CSE2ALG:Assignment 1", "CSE3CAP:Project"}
    assert all(a.feedback_comment != "Excellent." for a in ctx.assessments)  # S002's row excluded
    assert ctx.known_silos == {"CSE1OOF:SILO1", "CSE2ALG:SILO1", "CSE2ALG:SILO2", "CSE3CAP:SILO1"}
    assert ctx.known_subjects == {"CSE1OOF", "CSE2ALG", "CSE3CAP"}
    assert ctx.known_competencies == {"Data Structures", "Algorithm Analysis", "Project Delivery"}


def test_context_carries_per_subject_evidence_and_trend() -> None:
    ctx = _context()
    ds = next(c for c in ctx.competencies if c.competency_label == "Data Structures")
    assert ds.per_subject == (("CSE1OOF", 55.0), ("CSE2ALG", 48.0))
    assert ds.trend == "declining"
    assert ds.classification == "persistent gap"


def test_context_refuses_a_student_with_no_gap_rows() -> None:
    with pytest.raises(ValueError, match="No gap rows for student 'S999'"):
        build_plan_context(_dataset(), _clustering(), _gaps(), "S999")


# --- grounding: every kind of invention is caught ---------------------------


def test_grounded_plan_passes() -> None:
    validate_plan(_good_plan(), _context())


def test_invented_silo_key_is_rejected() -> None:
    plan = _good_plan()
    plan.priorities[0].silo_keys.append("CSE2ALG:SILO9")
    with pytest.raises(GroundingError, match=r"SILO not present in the input: \['CSE2ALG:SILO9'\]"):
        validate_plan(plan, _context())


def test_invented_subject_code_is_rejected() -> None:
    plan = _good_plan()
    plan.priorities[0].subject_codes.append("CSE4NET")
    with pytest.raises(GroundingError, match=r"subject not present in the input: \['CSE4NET'\]"):
        validate_plan(plan, _context())


def test_invented_assessment_is_rejected() -> None:
    plan = _good_plan()
    plan.priorities[0].assessment_keys.append("CSE2ALG:Final Exam")
    with pytest.raises(GroundingError, match=r"assessment not present in the input: \['CSE2ALG:Final Exam'\]"):
        validate_plan(plan, _context())


def test_invented_competency_is_rejected() -> None:
    plan = _good_plan()
    plan.priorities.append(
        PlanPriority(
            competency_label="Quantum Computing",
            silo_keys=[],
            subject_codes=[],
            assessment_keys=[],
            evidence="none",
            actions="none",
        )
    )
    with pytest.raises(GroundingError, match=r"competency not present in the input: \['Quantum Computing'\]"):
        validate_plan(plan, _context())


def test_invented_strength_is_rejected() -> None:
    plan = _good_plan()
    plan.strengths_to_build_on.append("Public Speaking")
    with pytest.raises(GroundingError, match="strength competency not present in the input"):
        validate_plan(plan, _context())


def test_wrong_student_is_rejected() -> None:
    plan = _good_plan()
    plan.student_id = "S002"
    with pytest.raises(GroundingError, match=r"student not present in the input: \['S002'\]"):
        validate_plan(plan, _context())


def test_same_competency_twice_is_rejected() -> None:
    plan = _good_plan()
    plan.priorities.append(plan.priorities[0].model_copy())
    with pytest.raises(GroundingError, match="competency referenced more than once"):
        validate_plan(plan, _context())


def test_codes_invented_inside_prose_are_caught() -> None:
    """Structured fields are not the only place a model can hallucinate:
    a sentence recommending a subject that does not exist must fail too.
    """
    plan = _good_plan()
    plan.priorities[0].actions = "Take CSE2NET next semester and revisit CSE1OOF:SILO7."
    with pytest.raises(GroundingError) as excinfo:
        validate_plan(plan, _context())
    message = str(excinfo.value)
    assert "subject mentioned in prose not present in the input: ['CSE2NET']" in message
    assert "SILO mentioned in prose not present in the input: ['CSE1OOF:SILO7']" in message


def test_every_problem_is_reported_in_one_error() -> None:
    plan = _good_plan()
    plan.priorities[0].silo_keys.append("CSE2ALG:SILO9")
    plan.priorities[0].subject_codes.append("CSE4NET")
    plan.strengths_to_build_on.append("Public Speaking")
    with pytest.raises(GroundingError) as excinfo:
        validate_plan(plan, _context())
    message = str(excinfo.value)
    assert "CSE2ALG:SILO9" in message and "CSE4NET" in message and "Public Speaking" in message


# --- generation: retry, recover, or fail the build -------------------------


def test_generation_returns_a_grounded_plan_first_time() -> None:
    client = _FakeLLMClient(_good_plan())
    plan = generate_learning_plan(client, _context())
    assert plan.student_id == STUDENT
    assert client.call_count == 1
    # The prompt is built from the context, so the vocabulary the validator
    # checks against is exactly what the model was shown.
    assert "CSE2ALG:Assignment 1" in client.users_seen[0]
    assert "Linked list bugs" in client.users_seen[0]
    assert "Excellent." not in client.users_seen[0]


def test_generation_retries_with_the_errors_quoted_and_recovers() -> None:
    bad = _good_plan()
    bad.priorities[0].silo_keys.append("CSE2ALG:SILO9")
    client = _FakeLLMClient(bad, _good_plan())
    plan = generate_learning_plan(client, _context())
    assert client.call_count == 2
    assert "CSE2ALG:SILO9" in client.users_seen[1]
    assert "rejected by the grounding check" in client.users_seen[1]
    assert "CSE2ALG:SILO9" not in plan.priorities[0].silo_keys


def test_generation_fails_the_build_when_no_attempt_grounds() -> None:
    bad = _good_plan()
    bad.priorities[0].subject_codes.append("CSE4NET")
    client = _FakeLLMClient(bad)
    with pytest.raises(GroundingError, match="failed grounding validation on all 2 attempts"):
        generate_learning_plan(client, _context(), max_attempts=2)
    assert client.call_count == 2


# --- rendering -------------------------------------------------------------


def test_markdown_shows_the_plan_alongside_its_evidence() -> None:
    text = render_markdown(_good_plan(), _context())
    assert "# Learning plan for S001" in text
    assert "## 1. Data Structures" in text
    assert "`CSE1OOF:SILO1` -- write object-oriented programs" in text
    assert "| Data Structures | persistent gap | 50.8% | CSE1OOF 55.0%, CSE2ALG 48.0% | declining |" in text
    assert "- Project Delivery" in text
