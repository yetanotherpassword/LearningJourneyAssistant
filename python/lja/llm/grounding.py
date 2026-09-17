"""Grounding validation for anything the LLM generates (S4-3, IOLG-85).

The proposal's anti-hallucination constraint -- and tender requirement 6 --
is that a generated artefact may only ever name things that were in its
input: SILOs, subjects, assessments, competencies. A prompt instruction is
not enough to guarantee that. silo_clustering.py learned this the hard way
when a live model silently dropped 3 of 13 SILOs on two separate runs, and
its `_validate_coverage()` is what caught it. This module is that check
generalised so every generated artefact (the clustering today, the S4-6
learning plan next) is validated the same way, against the input rather
than just against a schema.

Three things can go wrong, and each is a separate `ReferenceCheck` flag so
an artefact only asserts what it actually needs:

* **unknown** -- the artefact names something the input does not contain.
  Always checked. This is the hallucination case and the reason the
  module exists.
* **missing** -- something in the input never appears in the artefact.
  Only when `require_complete=True`. Clustering needs this (every SILO
  must land in a cluster); a learning plan does not (it is allowed to
  focus on a few competencies).
* **duplicated** -- something is referenced more than once. Only when
  `require_unique=True`. Clustering needs this (a SILO in two clusters
  double-counts a student's evidence); most prose artefacts do not.

Names are compared exactly, after nothing more than `str.strip()`. Any
canonicalisation beyond that (case folding, alias tables) belongs to the
caller, where the domain knowledge is -- doing it here would let a
near-miss like "CSE1OOF" vs "CSE10OF" through as a match.

Structured output first. `LLMClient.complete_structured()` is the only
generation path this package supports, so the expected use is: the
artefact's Pydantic schema carries explicit fields naming what it
references, and those fields are handed to `check_grounding()`. For any
free-text field that is allowed to mention codes inline, `extract_codes()`
pulls them out by pattern so they can be checked too; it cannot recover an
arbitrary invented assessment title from prose, which is exactly why the
names should live in structured fields in the first place.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from ..data.excel_loader import LjaDataset

ProblemCategory = Literal["unknown", "missing", "duplicated"]


class GroundingError(ValueError):
    """Raised when a generated artefact fails grounding validation.

    Subclasses ValueError so existing retry loops that catch ValueError
    (cluster_silos) keep working unchanged.
    """


@dataclass(frozen=True)
class ReferenceCheck:
    """One namespace to validate: what the artefact says, against what the
    input actually contained.

    `kind` is the human label used in error text ("SILO", "subject",
    "competency"). `referenced` keeps repetition -- pass every mention, not
    a set, or the duplicate check has nothing to see.
    """

    kind: str
    referenced: Sequence[str]
    known: Collection[str]
    require_complete: bool = False
    require_unique: bool = False


@dataclass(frozen=True)
class GroundingProblem:
    kind: str
    category: ProblemCategory
    items: tuple[str, ...]

    def describe(self) -> str:
        items = list(self.items)
        if self.category == "unknown":
            return f"{self.kind} not present in the input: {items}"
        if self.category == "missing":
            return f"{self.kind} in the input but absent from the output: {items}"
        return f"{self.kind} referenced more than once: {items}"


@dataclass(frozen=True)
class GroundingReport:
    """The outcome of validating one artefact. `ok` is the only thing most
    callers need; `problems` is there for tests and for feeding a precise
    correction back to the model on retry.
    """

    artefact: str
    problems: tuple[GroundingProblem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def describe(self) -> str:
        if self.ok:
            return f"{self.artefact} is grounded in its input"
        return f"{self.artefact} failed grounding validation -- " + "; ".join(p.describe() for p in self.problems)

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise GroundingError(self.describe())


def _clean(names: Iterable[str]) -> list[str]:
    return [name.strip() for name in names]


def check_grounding(artefact: str, checks: Iterable[ReferenceCheck]) -> GroundingReport:
    """Validate an artefact and return a report rather than raising, for
    callers that want to decide what to do (retry, warn, fail the build).
    """
    problems: list[GroundingProblem] = []
    for check in checks:
        referenced = _clean(check.referenced)
        known = set(_clean(check.known))
        counts = Counter(referenced)

        unknown = sorted(set(referenced) - known)
        if unknown:
            problems.append(GroundingProblem(check.kind, "unknown", tuple(unknown)))

        if check.require_complete:
            missing = sorted(known - set(referenced))
            if missing:
                problems.append(GroundingProblem(check.kind, "missing", tuple(missing)))

        if check.require_unique:
            duplicated = sorted(name for name, count in counts.items() if count > 1)
            if duplicated:
                problems.append(GroundingProblem(check.kind, "duplicated", tuple(duplicated)))

    return GroundingReport(artefact=artefact, problems=tuple(problems))


def validate_grounding(artefact: str, checks: Iterable[ReferenceCheck]) -> None:
    """Fail-loudly form of check_grounding(): raises GroundingError with
    every problem listed, so a retry prompt can quote the whole list.
    """
    check_grounding(artefact, checks).raise_if_failed()


# Patterns for the identifiers that appear inline in this project's data.
# Subject codes are La Trobe's three letters, one digit, three letters
# (CSE1OOF); SILO ids are the workbook's SILOn. Keep them here so every
# artefact extracts the same way.
SUBJECT_CODE_PATTERN = re.compile(r"\b[A-Z]{3}\d[A-Z]{3}\b")
SILO_KEY_PATTERN = re.compile(r"\b[A-Z]{3}\d[A-Z]{3}:SILO\d+\b")


def extract_codes(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Every match of `pattern` in `text`, in order and with repetition, so
    the result can be fed straight into a ReferenceCheck. Free-text fields
    only -- structured fields should be checked directly.
    """
    return pattern.findall(text)


@dataclass(frozen=True)
class InputVocabulary:
    """The names a dataset makes available to a generator, in the exact
    form a ReferenceCheck should compare against. Competency labels are
    not here because they come from a clustering result, not the workbook
    -- the S4-6 caller passes those from whatever clustering it was given.
    """

    silos: frozenset[str]  # "SUBJECT:SILOn", same keys as LjaDataset.silos
    subjects: frozenset[str]  # "SUBJECT"
    assessments: frozenset[str]  # "SUBJECT:Assessment name", mirroring the SILO key shape

    @classmethod
    def from_dataset(cls, dataset: LjaDataset) -> InputVocabulary:
        subjects = {silo.subject_code for silo in dataset.silos.values()}
        subjects.update(a.subject_code for a in dataset.assessments)
        assessments = {f"{a.subject_code}:{a.assessment_name}" for a in dataset.assessments}
        return cls(
            silos=frozenset(dataset.silos.keys()),
            subjects=frozenset(subjects),
            assessments=frozenset(assessments),
        )


__all__ = [
    "GroundingError",
    "GroundingProblem",
    "GroundingReport",
    "InputVocabulary",
    "ReferenceCheck",
    "SILO_KEY_PATTERN",
    "SUBJECT_CODE_PATTERN",
    "check_grounding",
    "extract_codes",
    "validate_grounding",
]
