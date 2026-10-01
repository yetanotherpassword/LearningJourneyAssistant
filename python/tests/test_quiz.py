"""Grounding and structure tests for practice quizzes (tender R8).

Same evidence role as test_study_strategy.py for tender requirement 6: a
quiz that names anything outside its input, or files a real name under the
wrong competency, is rejected, retried, and never returned. The scenario is
the learning-plan suite's: Data Structures is a persistent gap (CSE1OOF 55%,
CSE2ALG 48%), Algorithm Analysis an isolated gap (CSE2ALG only), Project
Delivery a strength.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from lja.llm.grounding import GroundingError
from lja.model.quiz import (
    Quiz,
    QuizDocument,
    QuizItem,
    SubjectInfo,
    _render_context,
    build_quiz_context,
    generate_quiz,
    render_markdown,
    validate_quiz,
)
from tests.test_learning_plan import STUDENT, _context

SUBJECTS = {
    "CSE1OOF": SubjectInfo("CSE1OOF", "Object-Oriented Programming Fundamentals", 1, "Introduces OO concepts using Java."),
    "CSE2ALG": SubjectInfo("CSE2ALG", "Algorithms and Data Structures", 2, "Linear structures, trees, hash tables and graphs."),
}


class _FakeLLMClient:
    def __init__(self, *results: Quiz) -> None:
        self._results = list(results)
        self.call_count = 0
        self.users_seen: list[str] = []
        self.systems_seen: list[str] = []

    def complete_structured(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        assert schema is Quiz
        index = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        self.users_seen.append(user)
        self.systems_seen.append(system)
        return self._results[index]


def _quiz_context(items_per_gap: int = 1):
    return build_quiz_context(_context(), SUBJECTS, items_per_gap=items_per_gap)


def _ds_item(**overrides) -> QuizItem:
    fields = dict(
        competency_label="Data Structures",
        gap_kind="persistent gap",
        subject_code="CSE2ALG",
        silo_key="CSE2ALG:SILO1",
        assessment_key="CSE2ALG:Assignment 1",
        stem="Which operation on a singly linked list is O(1) when you hold a reference to the head?",
        options=["Insert at the head", "Find the last node", "Delete a node by value"],
        correct_index=0,
        explanation="Only the head is reachable without traversal. Revisit CSE2ALG:SILO1 for list traversal cost.",
    )
    fields.update(overrides)
    return QuizItem(**fields)


def _aa_item(**overrides) -> QuizItem:
    fields = dict(
        competency_label="Algorithm Analysis",
        gap_kind="isolated gap",
        subject_code="CSE2ALG",
        silo_key="CSE2ALG:SILO2",
        assessment_key="CSE2ALG:Assignment 1",
        stem="What is the time complexity of binary search on a sorted array of n items?",
        options=["O(n)", "O(log n)", "O(n log n)", "O(1)"],
        correct_index=1,
        explanation="Each step halves the range. O(n) is linear search. See CSE2ALG:SILO2.",
    )
    fields.update(overrides)
    return QuizItem(**fields)


def _good_quiz(*items: QuizItem) -> Quiz:
    return Quiz(student_id=STUDENT, introduction="Practice questions on your two gaps; not an assessment.", items=list(items) or [_ds_item(), _aa_item()])


# --- context and prompt ----------------------------------------------------


def test_context_lists_every_known_subject_with_catalogue_info_where_present() -> None:
    ctx = _quiz_context()
    assert [s.code for s in ctx.subjects] == ["CSE1OOF", "CSE2ALG", "CSE3CAP"]
    assert ctx.subjects[0].synopsis == "Introduces OO concepts using Java."
    assert ctx.subjects[2].title == "" and ctx.subjects[2].synopsis == ""  # not in the catalogue map


def test_prompt_shows_gap_silos_assessments_and_synopses() -> None:
    text = _render_context(_quiz_context())
    assert "SILO CSE2ALG:SILO1: implement data structures" in text
    assert "Assessments covering it: CSE2ALG:Assignment 1" in text
    assert "CSE1OOF Object-Oriented Programming Fundamentals: Introduces OO concepts using Java." in text
    assert "CSE3CAP: (no synopsis available)" in text
    # A strength's SILOs are not offered as quiz material.
    assert "CSE3CAP:SILO1: deliver" not in text


def test_items_per_gap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="items_per_gap"):
        build_quiz_context(_context(), SUBJECTS, items_per_gap=0)


# --- grounding -------------------------------------------------------------


def test_grounded_quiz_passes() -> None:
    validate_quiz(_good_quiz(), _quiz_context())


def test_every_gap_needs_its_questions_and_a_strength_gets_none() -> None:
    with pytest.raises(GroundingError, match=r"gap competency in the input but absent from the output: \['Algorithm Analysis'\]"):
        validate_quiz(_good_quiz(_ds_item()), _quiz_context())
    stray = _aa_item(competency_label="Project Delivery", subject_code="CSE3CAP", silo_key="CSE3CAP:SILO1", assessment_key="CSE3CAP:Project")
    with pytest.raises(GroundingError, match=r"gap competency not present in the input: \['Project Delivery'\]"):
        validate_quiz(_good_quiz(_ds_item(), _aa_item(), stray), _quiz_context())


def test_question_count_per_gap_is_exact() -> None:
    with pytest.raises(GroundingError, match=r"'Data Structures' has 2 question\(s\); write exactly 1"):
        validate_quiz(_good_quiz(_ds_item(), _ds_item(stem="Another?"), _aa_item()), _quiz_context())
    validate_quiz(_good_quiz(_ds_item(), _ds_item(stem="Another?"), _aa_item(), _aa_item(stem="More?")), _quiz_context(items_per_gap=2))


def test_gap_kind_must_match_the_classification() -> None:
    with pytest.raises(GroundingError, match=r"gap classification not present in the input: \['Algorithm Analysis = persistent gap'\]"):
        validate_quiz(_good_quiz(_ds_item(), _aa_item(gap_kind="persistent gap")), _quiz_context())


def test_silo_and_assessment_must_belong_to_the_competency() -> None:
    with pytest.raises(GroundingError, match=r"SILO in 'Data Structures' not present in the input: \['CSE2ALG:SILO2'\]"):
        validate_quiz(_good_quiz(_ds_item(silo_key="CSE2ALG:SILO2"), _aa_item()), _quiz_context())
    with pytest.raises(GroundingError, match=r"assessment evidencing 'Data Structures' not present in the input: \['CSE3CAP:Project'\]"):
        validate_quiz(_good_quiz(_ds_item(assessment_key="CSE3CAP:Project"), _aa_item()), _quiz_context())


def test_subject_must_evidence_the_competency_and_hold_the_silo() -> None:
    with pytest.raises(GroundingError, match=r"subject evidencing 'Algorithm Analysis' not present in the input: \['CSE1OOF'\]"):
        validate_quiz(_good_quiz(_ds_item(), _aa_item(subject_code="CSE1OOF")), _quiz_context())
    with pytest.raises(GroundingError) as exc:
        validate_quiz(_good_quiz(_ds_item(subject_code="CSE1OOF"), _aa_item()), _quiz_context())
    assert "silo_key CSE2ALG:SILO1 is not in subject CSE1OOF" in str(exc.value)
    assert "assessment_key CSE2ALG:Assignment 1 is not in subject CSE1OOF" in str(exc.value)


def test_invented_codes_in_prose_and_options_are_rejected() -> None:
    bad = _aa_item(options=["O(n)", "O(log n)", "What CSE9ZZZ:SILO4 covers"], explanation="See CSE9ZZZ.")
    with pytest.raises(GroundingError) as exc:
        validate_quiz(_good_quiz(_ds_item(), bad), _quiz_context())
    assert "SILO mentioned in prose not present in the input: ['CSE9ZZZ:SILO4']" in str(exc.value)
    assert "subject mentioned in prose not present in the input: ['CSE9ZZZ'" in str(exc.value)


def test_a_subject_named_only_in_a_synopsis_is_allowed_in_prose() -> None:
    subjects = dict(SUBJECTS)
    subjects["CSE3CAP"] = SubjectInfo("CSE3CAP", "Capstone Project", 3, "Builds on CSE3PRM and CSE3CAP in consecutive semesters.")
    ctx = build_quiz_context(_context(), subjects, items_per_gap=1)
    assert "CSE3PRM" in ctx.known_subjects
    validate_quiz(_good_quiz(_ds_item(), _aa_item(explanation="Also useful before CSE3PRM. See CSE2ALG:SILO2.")), ctx)


def test_options_are_well_formed() -> None:
    with pytest.raises(ValidationError):
        _aa_item(options=["only", "two"])
    with pytest.raises(ValidationError):
        _aa_item(options=["a", "b", "c", "d", "e"])
    with pytest.raises(GroundingError) as exc:
        validate_quiz(
            _good_quiz(_ds_item(options=["x", "x", " "], correct_index=2, explanation=" "), _aa_item(options=["O(n)", "O(1)", "O(2)"], correct_index=3)),
            _quiz_context(),
        )
    message = str(exc.value)
    assert "question 1 has a blank option" in message
    assert "question 1 repeats an option" in message
    assert "question 1 has no explanation" in message
    assert "question 2: correct_index 3 is outside its 3 options" in message


# --- generation loop -------------------------------------------------------


def test_retry_quotes_the_problems_then_succeeds() -> None:
    bad = _good_quiz(_ds_item(silo_key="CSE2ALG:SILO2"), _aa_item())
    client = _FakeLLMClient(bad, _good_quiz())
    quiz = generate_quiz(client, _quiz_context())
    assert client.call_count == 2
    assert "Your previous quiz was rejected" in client.users_seen[1]
    assert "CSE2ALG:SILO2" in client.users_seen[1]
    assert quiz == _good_quiz()


def test_system_prompt_carries_the_item_count_and_extra_instructions() -> None:
    client = _FakeLLMClient(_good_quiz(_ds_item(), _ds_item(stem="B?"), _aa_item(), _aa_item(stem="C?")))
    generate_quiz(client, _quiz_context(items_per_gap=2), extra_instructions="Keep stems under 25 words.")
    assert "Write exactly 2 question(s)" in client.systems_seen[0]
    assert client.systems_seen[0].endswith("Keep stems under 25 words.")


def test_never_grounding_raises_instead_of_returning() -> None:
    client = _FakeLLMClient(_good_quiz(_ds_item()))
    with pytest.raises(GroundingError, match="failed grounding validation on all 3 attempts"):
        generate_quiz(client, _quiz_context())
    assert client.call_count == 3


def test_a_student_with_no_gap_is_refused_before_any_llm_call() -> None:
    from lja.model.learning_plan import CompetencyContext, PlanContext

    strong = PlanContext(
        student_id=STUDENT,
        competencies=(CompetencyContext("Project Delivery", "proficient", 82.0, ("CSE3CAP:SILO1",), (("CSE3CAP", 82.0),), "n/a", ()),),
    )
    client = _FakeLLMClient(_good_quiz())
    with pytest.raises(ValueError, match="no isolated or persistent gap"):
        generate_quiz(client, build_quiz_context(strong, SUBJECTS))
    assert client.call_count == 0


# --- document and rendering ------------------------------------------------


def test_document_carries_the_subject_info_the_model_saw() -> None:
    ctx = _quiz_context()
    document = QuizDocument.from_quiz(_good_quiz(), ctx)
    assert [s.code for s in document.subjects] == ["CSE1OOF", "CSE2ALG", "CSE3CAP"]
    assert document.subjects[1].synopsis == "Linear structures, trees, hash tables and graphs."
    assert document.subjects[2].synopsis == ""
    assert QuizDocument.model_validate_json(document.model_dump_json()) == document


def test_markdown_shows_questions_answers_subjects_and_evidence() -> None:
    ctx = _quiz_context()
    text = render_markdown(QuizDocument.from_quiz(_good_quiz(), ctx), ctx)
    assert "## 1. Data Structures (persistent gap)" in text
    assert "- B. O(log n)" in text
    assert "**2.** B. Each step halves the range." in text
    assert "**CSE2ALG** Algorithms and Data Structures. Linear structures" in text
    assert "staff should check the answer key" in text
    assert "| Data Structures | persistent gap | 50.8% | CSE1OOF 55.0%, CSE2ALG 48.0% |" in text


# --- educator review (blind second pass) -----------------------------------

from lja.model.quiz import EducatorNote, EducatorReview, _render_review_context, review_quiz, validate_review  # noqa: E402


class _FakeReviewClient(_FakeLLMClient):
    def complete_structured(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        assert schema is EducatorReview
        index = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        self.users_seen.append(user)
        self.systems_seen.append(system)
        return self._results[index]

    def describe(self) -> str:
        return "fake-reviewer"


def _document() -> QuizDocument:
    return QuizDocument.from_quiz(_good_quiz(), _quiz_context())


def _note(index: int, chosen: int, **overrides) -> EducatorNote:
    fields = dict(question_index=index, chosen_index=chosen, confidence="high", teaching_explanation="Because traversal costs grow with length. Practises CSE2ALG:SILO1.")
    fields.update(overrides)
    return EducatorNote(**fields)


def test_review_prompt_hides_the_key_and_shows_silo_assessment_and_synopsis() -> None:
    text = _render_review_context(_document(), _quiz_context())
    assert "correct" not in text.lower()
    assert "explanation" not in text.lower()
    assert "SILO CSE2ALG:SILO2: analyse algorithm complexity" in text
    assert "Pitched at assessment CSE2ALG:Assignment 1" in text
    assert "Synopsis: Linear structures, trees, hash tables and graphs." in text
    assert "option 1: O(log n)" in text


def test_review_must_cover_every_question_once_with_a_valid_choice() -> None:
    doc, ctx = _document(), _quiz_context()
    with pytest.raises(GroundingError, match=r"question index in the input but absent from the output: \['1'\]"):
        validate_review(EducatorReview(notes=[_note(0, 0)]), doc, ctx)
    with pytest.raises(GroundingError, match=r"question index referenced more than once: \['0'\]"):
        validate_review(EducatorReview(notes=[_note(0, 0), _note(0, 1), _note(1, 1)]), doc, ctx)
    with pytest.raises(GroundingError, match=r"question 1: chosen_index 3 is outside its 3 options"):
        validate_review(EducatorReview(notes=[_note(0, 3), _note(1, 1)]), doc, ctx)
    with pytest.raises(GroundingError, match=r"question 2 has no teaching explanation"):
        validate_review(EducatorReview(notes=[_note(0, 0), _note(1, 1, teaching_explanation=" ")]), doc, ctx)
    with pytest.raises(GroundingError, match=r"SILO mentioned in prose not present in the input: \['CSE9ZZZ:SILO1'\]"):
        validate_review(EducatorReview(notes=[_note(0, 0, concerns="Overlaps CSE9ZZZ:SILO1."), _note(1, 1)]), doc, ctx)


def test_review_agreement_is_computed_in_code_not_asked_for() -> None:
    review = EducatorReview(notes=[_note(0, 0), _note(1, 0, confidence="low", concerns="Two options are defensible.")])
    doc = _document().model_copy(update={"educator_review": review})
    assert doc.agrees(0) is True
    assert doc.agrees(1) is False
    assert doc.disagreements == [1]
    assert doc.note_for(1).concerns == "Two options are defensible."
    assert _document().agrees(0) is None and _document().disagreements == []


def test_review_retries_then_records_the_reviewer() -> None:
    bad = EducatorReview(notes=[_note(0, 0)])
    good = EducatorReview(notes=[_note(0, 0), _note(1, 1)])
    client = _FakeReviewClient(bad, good)
    review = review_quiz(client, _document(), _quiz_context())
    assert client.call_count == 2
    assert "Your previous review was rejected" in client.users_seen[1]
    assert review.reviewer == "fake-reviewer"
    assert review.notes == good.notes


def test_review_never_grounding_raises() -> None:
    client = _FakeReviewClient(EducatorReview(notes=[]))
    with pytest.raises(GroundingError, match="Educator review for S001 failed grounding validation on all 3 attempts"):
        review_quiz(client, _document(), _quiz_context())


def test_markdown_lists_educator_notes_and_flags_disagreement() -> None:
    ctx = _quiz_context()
    review = EducatorReview(notes=[_note(0, 0), _note(1, 0, confidence="medium", concerns="Stem does not say the array is sorted.")], reviewer="fake-reviewer")
    doc = _document().model_copy(update={"educator_review": review})
    text = render_markdown(doc, ctx)
    assert "## Educator notes (blind check)" in text
    assert "It disagreed on question(s) 2; check those first." in text
    assert "**1.** Blind answer A (high confidence), agrees with the key." in text
    assert "**2.** Blind answer A (medium confidence), DISAGREES with the key." in text
    assert "*Concern:* Stem does not say the array is sorted." in text


def test_a_document_without_a_review_still_loads_and_renders() -> None:
    doc = _document()
    assert "educator_review" in doc.model_dump_json()
    assert QuizDocument.model_validate_json(doc.model_dump_json()).educator_review is None
    assert "Educator notes" not in render_markdown(doc, _quiz_context())
