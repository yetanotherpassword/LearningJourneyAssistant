"""Unit tests for lja.llm.grounding: the reusable validator that generalises
silo_clustering.py's coverage check (S4-3, IOLG-85). Pure functions over
plain data, so nothing here touches a model. The clustering adapter's own
behaviour -- including the retry loop -- is still covered in
test_silo_clustering.py; these tests pin down the generic contract that
S4-6's learning-plan generator will build on.
"""

from __future__ import annotations

import pytest

from lja.data.excel_loader import Assessment, LjaDataset, Silo
from lja.llm.grounding import (
    SILO_KEY_PATTERN,
    SUBJECT_CODE_PATTERN,
    GroundingError,
    InputVocabulary,
    ReferenceCheck,
    check_grounding,
    extract_codes,
    validate_grounding,
)

KNOWN = ["CSE1OOF:SILO1", "CSE1OOF:SILO2", "CSE2ALG:SILO1"]


def test_clean_artefact_is_ok() -> None:
    report = check_grounding("plan", [ReferenceCheck("SILO", ["CSE1OOF:SILO1", "CSE2ALG:SILO1"], KNOWN)])
    assert report.ok
    assert report.problems == ()
    assert report.describe() == "plan is grounded in its input"


def test_unknown_reference_is_always_a_problem() -> None:
    report = check_grounding("plan", [ReferenceCheck("SILO", ["CSE1OOF:SILO1", "CSE9XYZ:SILO4"], KNOWN)])
    assert not report.ok
    (problem,) = report.problems
    assert problem.category == "unknown"
    assert problem.items == ("CSE9XYZ:SILO4",)
    assert "SILO not present in the input" in report.describe()


def test_missing_is_only_a_problem_when_completeness_is_required() -> None:
    partial = ["CSE1OOF:SILO1"]
    assert check_grounding("plan", [ReferenceCheck("SILO", partial, KNOWN)]).ok

    report = check_grounding("clustering", [ReferenceCheck("SILO", partial, KNOWN, require_complete=True)])
    (problem,) = report.problems
    assert problem.category == "missing"
    assert problem.items == ("CSE1OOF:SILO2", "CSE2ALG:SILO1")


def test_duplicate_is_only_a_problem_when_uniqueness_is_required() -> None:
    repeated = ["CSE1OOF:SILO1", "CSE1OOF:SILO1"]
    assert check_grounding("plan", [ReferenceCheck("SILO", repeated, KNOWN)]).ok

    report = check_grounding("clustering", [ReferenceCheck("SILO", repeated, KNOWN, require_unique=True)])
    (problem,) = report.problems
    assert problem.category == "duplicated"
    assert problem.items == ("CSE1OOF:SILO1",)


def test_all_three_categories_are_reported_together() -> None:
    """A retry prompt should be able to quote every problem at once, not
    discover them one per attempt.
    """
    report = check_grounding(
        "clustering",
        [
            ReferenceCheck(
                "SILO",
                ["CSE1OOF:SILO1", "CSE1OOF:SILO1", "CSE9XYZ:SILO4"],
                KNOWN,
                require_complete=True,
                require_unique=True,
            )
        ],
    )
    assert [p.category for p in report.problems] == ["unknown", "missing", "duplicated"]


def test_checks_across_namespaces_are_aggregated() -> None:
    """The S4-6 shape: several kinds of name in one artefact, validated in
    one call, each kind reported under its own label.
    """
    report = check_grounding(
        "learning plan",
        [
            ReferenceCheck("SILO", ["CSE1OOF:SILO1"], KNOWN),
            ReferenceCheck("subject", ["CSE1OOF", "CSE4NEW"], ["CSE1OOF", "CSE2ALG"]),
            ReferenceCheck("competency", ["Data Structures", "Quantum Computing"], ["Data Structures"]),
        ],
    )
    assert [(p.kind, p.category) for p in report.problems] == [("subject", "unknown"), ("competency", "unknown")]
    text = report.describe()
    assert "subject not present in the input: ['CSE4NEW']" in text
    assert "competency not present in the input: ['Quantum Computing']" in text


def test_names_are_compared_after_stripping_but_otherwise_exactly() -> None:
    assert check_grounding("plan", [ReferenceCheck("subject", [" CSE1OOF "], ["CSE1OOF"])]).ok
    assert not check_grounding("plan", [ReferenceCheck("subject", ["cse1oof"], ["CSE1OOF"])]).ok


def test_empty_artefact_against_empty_input_is_ok() -> None:
    assert check_grounding("plan", [ReferenceCheck("SILO", [], [], require_complete=True, require_unique=True)]).ok


def test_validate_grounding_raises_a_value_error_subclass() -> None:
    """GroundingError must remain a ValueError so cluster_silos()'s existing
    `except ValueError` retry loop keeps catching it.
    """
    with pytest.raises(GroundingError, match="plan failed grounding validation") as excinfo:
        validate_grounding("plan", [ReferenceCheck("SILO", ["CSE9XYZ:SILO4"], KNOWN)])
    assert isinstance(excinfo.value, ValueError)

    validate_grounding("plan", [ReferenceCheck("SILO", ["CSE1OOF:SILO1"], KNOWN)])  # no raise


def test_extract_codes_keeps_order_and_repetition() -> None:
    prose = "Revisit CSE1OOF:SILO2 before CSE2ALG, then CSE1OOF:SILO2 again; CSE3CAP builds on it."
    assert extract_codes(prose, SILO_KEY_PATTERN) == ["CSE1OOF:SILO2", "CSE1OOF:SILO2"]
    assert extract_codes(prose, SUBJECT_CODE_PATTERN) == ["CSE1OOF", "CSE2ALG", "CSE1OOF", "CSE3CAP"]


def test_extracted_codes_feed_straight_into_a_check() -> None:
    prose = "Focus on CSE1OOF:SILO1 and the invented CSE7ZZZ:SILO3."
    report = check_grounding("plan", [ReferenceCheck("SILO", extract_codes(prose, SILO_KEY_PATTERN), KNOWN)])
    (problem,) = report.problems
    assert problem.items == ("CSE7ZZZ:SILO3",)


def _dataset() -> LjaDataset:
    silos = {
        "CSE1OOF:SILO1": Silo("CSE1OOF", "SILO1", "alpha"),
        "CSE2ALG:SILO1": Silo("CSE2ALG", "SILO1", "beta"),
    }
    assessments = [
        Assessment("CSE1OOF", "Test", 20.0, "Individual", True, False, ("SILO1",)),
        Assessment("CSE3CAP", "Project", 60.0, "Group", False, True, ()),
    ]
    return LjaDataset(silos=silos, assessments=assessments, results=[], student_summaries=[])


def test_input_vocabulary_mirrors_the_dataset_key_shapes() -> None:
    vocab = InputVocabulary.from_dataset(_dataset())
    assert vocab.silos == {"CSE1OOF:SILO1", "CSE2ALG:SILO1"}
    # Subjects come from both SILO rows and assessment rows: CSE3CAP has an
    # assessment but no SILO in this fixture and must still count as known.
    assert vocab.subjects == {"CSE1OOF", "CSE2ALG", "CSE3CAP"}
    assert vocab.assessments == {"CSE1OOF:Test", "CSE3CAP:Project"}
