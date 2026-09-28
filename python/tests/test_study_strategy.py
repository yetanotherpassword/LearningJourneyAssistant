"""Grounding and structure tests for study strategies (IOLG-123).

Same evidence role as test_learning_plan.py for tender requirement 6: a
strategy that names anything outside its input, or files a real name under
the wrong competency, is rejected, retried, and never returned. On top of
that, the rules that make a persistent-gap strategy different in kind from
an isolated-gap one are tested here, because the brief asks for
"structurally different" and a prompt instruction alone is not a guarantee.

The scenario is the learning-plan suite's: Data Structures is a persistent
gap (CSE1OOF 55%, CSE2ALG 48%), Algorithm Analysis an isolated gap
(CSE2ALG only), Project Delivery a strength.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from lja.llm.grounding import GroundingError
from lja.model.study_strategy import (
    STUDY_TECHNIQUES,
    StrategyEntry,
    StudyStrategy,
    _render_context,
    assessments_for,
    gap_competencies,
    generate_study_strategy,
    render_markdown,
    validate_strategy,
)
from tests.test_learning_plan import STUDENT, _context


class _FakeLLMClient:
    def __init__(self, *results: StudyStrategy) -> None:
        self._results = list(results)
        self.call_count = 0
        self.users_seen: list[str] = []
        self.systems_seen: list[str] = []

    def complete_structured(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        assert schema is StudyStrategy
        index = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        self.users_seen.append(user)
        self.systems_seen.append(system)
        return self._results[index]


def _persistent() -> StrategyEntry:
    return StrategyEntry(
        competency_label="Data Structures",
        gap_kind="persistent gap",
        subject_codes=["CSE1OOF", "CSE2ALG"],
        assessment_keys=["CSE1OOF:Test", "CSE2ALG:Assignment 1"],
        silo_keys=["CSE1OOF:SILO1", "CSE2ALG:SILO1"],
        evidence="50.8% overall, falling from CSE1OOF 55.0% to CSE2ALG 48.0%; feedback cites linked list bugs.",
        techniques=["interleaving", "retrieval practice"],
        how_to_apply="Alternate CSE1OOF:SILO1 class exercises with CSE2ALG:SILO1 linked list problems in each session.",
        schedule="Three 30-minute sessions a week, two days apart, for three weeks.",
        check_progress="Implement a linked list from memory with passing tests.",
    )


def _isolated() -> StrategyEntry:
    return StrategyEntry(
        competency_label="Algorithm Analysis",
        gap_kind="isolated gap",
        subject_codes=["CSE2ALG"],
        assessment_keys=["CSE2ALG:Assignment 1"],
        silo_keys=["CSE2ALG:SILO2"],
        evidence="48.0% in CSE2ALG only.",
        techniques=["feedback review", "worked examples"],
        how_to_apply="Rework CSE2ALG:Assignment 1's complexity answers against the marker's comment.",
        schedule="One session this week.",
        check_progress="State the complexity of each operation in the assignment without notes.",
    )


def _good() -> StudyStrategy:
    return StudyStrategy(student_id=STUDENT, overview="Rebuild data structures across subjects; fix one local gap.", entries=[_persistent(), _isolated()])


# --- context ---------------------------------------------------------------


def test_only_gaps_need_a_strategy_and_assessments_follow_the_silos() -> None:
    ctx = _context()
    assert [c.competency_label for c in gap_competencies(ctx)] == ["Algorithm Analysis", "Data Structures"]
    ds = next(c for c in ctx.competencies if c.competency_label == "Data Structures")
    assert assessments_for(ctx, ds) == {"CSE1OOF:Test", "CSE2ALG:Assignment 1"}  # not CSE3CAP:Project


def test_prompt_lists_every_technique_and_the_gap_silos() -> None:
    client = _FakeLLMClient(_good())
    generate_study_strategy(client, _context())
    for name in STUDY_TECHNIQUES:
        assert name in client.systems_seen[0]
    assert "SILO CSE2ALG:SILO2: analyse algorithm complexity" in client.users_seen[0]
    assert "Assessments covering it: CSE1OOF:Test, CSE2ALG:Assignment 1" in client.users_seen[0]
    # The strength's SILO wording is not offered for study.
    assert "SILO CSE3CAP:SILO1" not in _render_context(_context())


# --- grounding ---------------------------------------------------------------


def test_grounded_strategy_passes() -> None:
    validate_strategy(_good(), _context())


def test_every_gap_needs_exactly_one_entry() -> None:
    missing = StudyStrategy(student_id=STUDENT, overview="x", entries=[_persistent()])
    with pytest.raises(GroundingError, match=r"gap competency in the input but absent from the output: \['Algorithm Analysis'\]"):
        validate_strategy(missing, _context())
    twice = StudyStrategy(student_id=STUDENT, overview="x", entries=[_persistent(), _persistent(), _isolated()])
    with pytest.raises(GroundingError, match=r"gap competency referenced more than once: \['Data Structures'\]"):
        validate_strategy(twice, _context())


def test_a_strength_gets_no_entry() -> None:
    strength = _isolated().model_copy(update={"competency_label": "Project Delivery"})
    strategy = StudyStrategy(student_id=STUDENT, overview="x", entries=[_persistent(), _isolated(), strength])
    with pytest.raises(GroundingError, match=r"gap competency not present in the input: \['Project Delivery'\]"):
        validate_strategy(strategy, _context())


def test_gap_kind_must_match_the_classification() -> None:
    strategy = _good()
    strategy.entries[1] = _isolated().model_copy(update={"gap_kind": "persistent gap"})
    with pytest.raises(GroundingError, match=r"gap classification not present in the input: \['Algorithm Analysis = persistent gap'\]"):
        validate_strategy(strategy, _context())


def test_real_assessment_filed_under_the_wrong_competency_is_rejected() -> None:
    # CSE3CAP:Project exists, but it evidences Project Delivery, not Data Structures.
    strategy = _good()
    strategy.entries[0].assessment_keys.append("CSE3CAP:Project")
    with pytest.raises(GroundingError, match=r"assessment evidencing 'Data Structures' not present in the input: \['CSE3CAP:Project'\]"):
        validate_strategy(strategy, _context())


def test_silo_and_subject_from_another_competency_are_rejected() -> None:
    strategy = _good()
    strategy.entries[1].silo_keys.append("CSE1OOF:SILO1")
    strategy.entries[1].subject_codes.append("CSE3CAP")
    with pytest.raises(GroundingError) as exc:
        validate_strategy(strategy, _context())
    assert "SILO in 'Algorithm Analysis' not present in the input: ['CSE1OOF:SILO1']" in str(exc.value)
    assert "subject evidencing 'Algorithm Analysis' not present in the input: ['CSE3CAP']" in str(exc.value)


def test_invented_codes_in_prose_are_rejected() -> None:
    strategy = _good()
    strategy.entries[0].how_to_apply += " Then read ahead for CSE4NET and CSE2ALG:SILO9."
    with pytest.raises(GroundingError) as exc:
        validate_strategy(strategy, _context())
    assert "subject mentioned in prose not present in the input: ['CSE4NET']" in str(exc.value)
    assert "SILO mentioned in prose not present in the input: ['CSE2ALG:SILO9']" in str(exc.value)


def test_prepare_for_only_names_future_subjects() -> None:
    strategy = _good()
    strategy.entries[0].prepare_for.append("CSE3CAP")  # already taken, and not in this competency
    with pytest.raises(GroundingError, match=r"future subject for 'Data Structures' not present in the input: \['CSE3CAP'\]"):
        validate_strategy(strategy, _context())


def test_techniques_are_a_closed_list() -> None:
    with pytest.raises(ValidationError):
        StrategyEntry.model_validate({**_isolated().model_dump(), "techniques": ["highlighting"]})


# --- structure: persistent and isolated strategies differ in kind -------------


def test_persistent_gap_must_span_at_least_two_subjects() -> None:
    strategy = _good()
    strategy.entries[0] = _persistent().model_copy(update={"subject_codes": ["CSE2ALG"]})
    with pytest.raises(GroundingError, match=r"'Data Structures' is a persistent gap but names 1 subject\(s\)"):
        validate_strategy(strategy, _context())


def test_persistent_gap_must_use_a_cross_subject_technique() -> None:
    strategy = _good()
    strategy.entries[0] = _persistent().model_copy(update={"techniques": ["retrieval practice", "elaboration"]})
    with pytest.raises(GroundingError, match=r"include interleaving or spaced practice"):
        validate_strategy(strategy, _context())


def test_isolated_gap_must_include_feedback_review() -> None:
    strategy = _good()
    strategy.entries[1] = _isolated().model_copy(update={"techniques": ["worked examples"]})
    with pytest.raises(GroundingError, match=r"'Algorithm Analysis' is an isolated gap; include feedback review"):
        validate_strategy(strategy, _context())


def test_every_entry_cites_an_assessment_and_a_silo() -> None:
    strategy = _good()
    strategy.entries[1] = _isolated().model_copy(update={"assessment_keys": [], "silo_keys": []})
    with pytest.raises(GroundingError) as exc:
        validate_strategy(strategy, _context())
    assert "'Algorithm Analysis' cites no assessment" in str(exc.value)
    assert "'Algorithm Analysis' names no SILO" in str(exc.value)


# --- generation --------------------------------------------------------------


def test_retry_quotes_the_problems_then_succeeds() -> None:
    bad = _good()
    bad.entries[1] = _isolated().model_copy(update={"techniques": ["worked examples"]})
    client = _FakeLLMClient(bad, _good())
    result = generate_study_strategy(client, _context())
    assert result == _good()
    assert client.call_count == 2
    assert "include feedback review" in client.users_seen[1]


def test_never_grounding_raises_instead_of_returning() -> None:
    bad = StudyStrategy(student_id=STUDENT, overview="x", entries=[_persistent()])
    client = _FakeLLMClient(bad)
    with pytest.raises(GroundingError, match="failed grounding validation on all 3 attempts"):
        generate_study_strategy(client, _context())
    assert client.call_count == 3


def test_a_student_with_no_gap_is_refused_before_any_llm_call() -> None:
    ctx = _context()
    no_gaps = ctx.__class__(
        student_id=ctx.student_id,
        competencies=tuple(c for c in ctx.competencies if c.competency_label == "Project Delivery"),
        silo_text=ctx.silo_text,
        assessments=ctx.assessments,
    )
    client = _FakeLLMClient(_good())
    with pytest.raises(ValueError, match="no isolated or persistent gap"):
        generate_study_strategy(client, no_gaps)
    assert client.call_count == 0


def test_markdown_shows_kind_techniques_and_evidence() -> None:
    md = render_markdown(_good(), _context())
    assert "*Persistent gap: shows across subjects* (CSE1OOF, CSE2ALG)" in md
    assert "*Isolated gap: one subject* (CSE2ALG)" in md
    assert f"- **feedback review.** {STUDY_TECHNIQUES['feedback review']}" in md
    assert "`CSE2ALG:SILO2` -- analyse algorithm complexity" in md
    assert "| Data Structures | persistent gap | 50.8% | CSE1OOF 55.0%, CSE2ALG 48.0% |" in md
