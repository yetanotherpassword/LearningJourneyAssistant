"""Trajectory of one student in one competency across the intended subject
sequence (IOLG-106, tender requirement 5 "progress").

A trajectory is the per-subject evidence behind a competency verdict
(gap_evidence.subject_breakdown) placed in the order the degree intends
the subjects to be taken, with the subjects the student has not sat yet
shown ahead of them. It answers two questions the gap card asks: is this
weakness recurring as the student moves through the sequence, and where
will it be assessed next.

ORDER, NOT TIME. The workbook carries no dates and no attempt timestamps
(1,650 rows, 11 assessments, no time dimension), so "progress" here means
position in the declared sequence and nothing more. Every Trajectory says
which source decided its order, exactly as every gap says which rule
decided its classification:

- "declared sequence": the subject is listed in LJA_SUBJECT_SEQUENCE. This is
  the configuration the ticket asked for -- a declared order, never parsed
  from the course code -- and it is where a course map from the project
  owner (FR-1.7) plugs in.
- "year digit": the subject is not declared, so its order falls back to the
  digit in the subject code (CSE2ALG -> 2), the convention gap_evidence.py
  documents. Subjects with the same year digit have no order between them.
- "unknown": neither applies. The subject is listed last and takes no part
  in the trend.

The trend label (improving / stable / declining / insufficient evidence)
compares the first and last ordered subjects the student has sat, inside a
stable band that is configuration (LJA_TREND_STABLE_BAND), not a literal.
Fewer than two ordered subjects is "insufficient evidence", which is the
normal case for a single-subject competency.

Nothing here predicts. A delta between two or three points is not a slope
to extrapolate, and the "ahead" subjects are where the competency is
assessed next, never advice about what to enrol in: mastery estimates are
formative indicators (tender guardrail), and subject choice is an academic
decision the system does not hold the rules for.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..data.excel_loader import LjaDataset
from ..model.silo_clustering import SiloClusteringResult
from .gap_evidence import (
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_INSUFFICIENT,
    TREND_STABLE,
    SubjectEvidence,
    _parse_year_level,
    subject_breakdown,
)

_UNSET: object = object()  # "year_level not supplied; parse it from the code"

SOURCE_DECLARED = "declared sequence"
SOURCE_YEAR_DIGIT = "year digit"
SOURCE_UNKNOWN = "unknown"

BASIS_DECLARED = SOURCE_DECLARED
BASIS_YEAR_DIGIT = SOURCE_YEAR_DIGIT
BASIS_MIXED = "mixed"
BASIS_NONE = "none"


@dataclass(frozen=True)
class SequencePosition:
    subject_code: str
    source: str
    # Declared subjects sort by their index; year-digit subjects after them by
    # year; unknown subjects last, alphabetically. The tuple is the whole
    # story, so two positions compare without knowing which source made them.
    sort_key: tuple[int, int, str]

    @property
    def ordered(self) -> bool:
        return self.source != SOURCE_UNKNOWN


@dataclass(frozen=True)
class SubjectSequence:
    """The intended order of subjects, as declared. Subjects not declared fall
    back to the year digit in their code; see the module docstring."""

    declared: tuple[str, ...] = ()

    @classmethod
    def from_string(cls, spec: str) -> SubjectSequence:
        """'CSE1OOF, CSE2ALG,CSE3CAP' -> SubjectSequence(('CSE1OOF', 'CSE2ALG', 'CSE3CAP')).
        Whitespace and empty entries are ignored; a repeated code keeps its
        first position."""
        seen: list[str] = []
        for raw in spec.split(","):
            code = raw.strip()
            if code and code not in seen:
                seen.append(code)
        return cls(tuple(seen))

    @classmethod
    def from_config(cls) -> SubjectSequence:
        return cls.from_string(config.SUBJECT_SEQUENCE)

    def position(self, subject_code: str, year_level: int | None | object = _UNSET) -> SequencePosition:
        """Where this subject sits. `year_level` may be passed when the caller
        already parsed it (SubjectEvidence carries it); by default it is read
        from the code."""
        if subject_code in self.declared:
            return SequencePosition(subject_code, SOURCE_DECLARED, (0, self.declared.index(subject_code), subject_code))
        year = _parse_year_level(subject_code) if year_level is _UNSET else year_level
        if year is not None:
            return SequencePosition(subject_code, SOURCE_YEAR_DIGIT, (1, year, subject_code))
        return SequencePosition(subject_code, SOURCE_UNKNOWN, (2, 0, subject_code))

    def sort_key(self, subject_code: str, year_level: int | None | object = _UNSET) -> tuple[int, int, str]:
        return self.position(subject_code, year_level).sort_key


@dataclass(frozen=True)
class TrajectoryPoint:
    subject_code: str
    source: str  # which rule placed it: declared sequence, year digit, unknown
    year_level: int | None
    taken: bool
    attainment_pct: float | None  # None when not taken
    n_observations: int


@dataclass(frozen=True)
class Trajectory:
    student_id: str
    competency_label: str
    points: tuple[TrajectoryPoint, ...]  # every subject in the competency, in sequence order
    delta: float | None  # last ordered taken subject minus first; None below two
    label: str  # improving | stable | declining | insufficient evidence
    basis: str  # what ordered the taken subjects: declared sequence | year digit | mixed | none
    stable_band: float

    @property
    def taken(self) -> tuple[TrajectoryPoint, ...]:
        return tuple(p for p in self.points if p.taken)

    @property
    def ahead(self) -> tuple[TrajectoryPoint, ...]:
        """Subjects in the competency the student has no results in yet, in
        sequence order. Where the weakness will be assessed next -- flag for
        preparation, never 'avoid'."""
        return tuple(p for p in self.points if not p.taken)


def trend_label(ordered_attainments: list[float], stable_band: float) -> tuple[float | None, str]:
    """First-to-last delta and its label. The caller supplies the attainments
    already in sequence order, ordered subjects only."""
    if len(ordered_attainments) < 2:
        return None, TREND_INSUFFICIENT
    delta = round(ordered_attainments[-1] - ordered_attainments[0], 1)
    if delta > stable_band:
        return delta, TREND_IMPROVING
    if delta < -stable_band:
        return delta, TREND_DECLINING
    return delta, TREND_STABLE


def describe_trend(
    evidence: list[SubjectEvidence],
    *,
    sequence: SubjectSequence | None = None,
    stable_band: float | None = None,
) -> str:
    """The trend word for a list of per-subject evidence, ordered by the
    declared sequence with the year-digit fallback. gap_evidence.describe_trend
    is a thin alias of this so every caller (dashboard, plans, export) orders
    the same way."""
    sequence = sequence or SubjectSequence.from_config()
    band = config.TREND_STABLE_BAND if stable_band is None else stable_band
    ordered = sorted(
        (e for e in evidence if sequence.position(e.subject_code, e.year_level).ordered),
        key=lambda e: sequence.sort_key(e.subject_code, e.year_level),
    )
    return trend_label([e.attainment_pct for e in ordered], band)[1]


def compute_trajectory(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    student_id: str,
    competency_label: str,
    *,
    sequence: SubjectSequence | None = None,
    stable_band: float | None = None,
) -> Trajectory:
    """One student, one competency: every subject whose SILOs the competency
    contains, in sequence order, marked taken (with the same per-subject
    attainment the gap card shows) or ahead."""
    sequence = sequence or SubjectSequence.from_config()
    band = config.TREND_STABLE_BAND if stable_band is None else stable_band

    evidence = {e.subject_code: e for e in subject_breakdown(dataset, clustering, student_id, competency_label)}
    cluster = next((c for c in clustering.clusters if c.competency_label == competency_label), None)
    subjects_in_competency = {m.subject_code for m in cluster.members} if cluster else set()
    summary = next((s for s in dataset.student_summaries if s.student_id == student_id), None)
    # An unknown student has no "already taken" set, and without one every
    # subject would look like a future one -- not a real statement about a
    # student we know nothing about (same rule as future_subjects_sharing_competency),
    # so nothing is listed ahead of them.
    if summary is None:
        subjects_in_competency = set()
    already_taken = set(summary.subject_totals) if summary is not None else set(evidence)

    points: list[TrajectoryPoint] = []
    for code in subjects_in_competency | set(evidence):
        pos = sequence.position(code, evidence[code].year_level if code in evidence else _UNSET)
        e = evidence.get(code)
        points.append(
            TrajectoryPoint(
                subject_code=code,
                source=pos.source,
                year_level=e.year_level if e else _parse_year_level(code),
                taken=code in evidence or code in already_taken,
                attainment_pct=e.attainment_pct if e else None,
                n_observations=e.n_observations if e else 0,
            )
        )
    points.sort(key=lambda p: sequence.sort_key(p.subject_code, p.year_level))

    ordered_taken = [p for p in points if p.taken and p.attainment_pct is not None and p.source != SOURCE_UNKNOWN]
    delta, label = trend_label([p.attainment_pct for p in ordered_taken if p.attainment_pct is not None], band)
    sources = {p.source for p in ordered_taken}
    if not sources:
        basis = BASIS_NONE
    elif sources == {SOURCE_DECLARED}:
        basis = BASIS_DECLARED
    elif sources == {SOURCE_YEAR_DIGIT}:
        basis = BASIS_YEAR_DIGIT
    else:
        basis = BASIS_MIXED

    return Trajectory(
        student_id=student_id,
        competency_label=competency_label,
        points=tuple(points),
        delta=delta,
        label=label,
        basis=basis,
        stable_band=band,
    )


def compute_trajectories(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    pairs: list[tuple[str, str]],
    *,
    sequence: SubjectSequence | None = None,
    stable_band: float | None = None,
) -> dict[tuple[str, str], Trajectory]:
    """compute_trajectory over (student_id, competency_label) pairs -- the
    gap report's own grain -- keyed the same way."""
    sequence = sequence or SubjectSequence.from_config()
    return {
        (s, c): compute_trajectory(dataset, clustering, s, c, sequence=sequence, stable_band=stable_band)
        for s, c in pairs
    }
