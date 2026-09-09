"""Explaining a gap, not just detecting it -- the "explain this gap" hook
flagged as a follow-up in gap_detection.py / docs/sprint-plan.md's M3 row.

Deliberately grounded in structured data only, no LLM call, so it inherits
the proposal's anti-hallucination constraint by construction rather than
needing a separate grounding test suite:

1. subject_breakdown() re-derives compute_gaps()'s same weighted-average
   observations, but split per subject instead of collapsed into one
   attainment_pct -- the raw evidence a gap classification is built on.
2. describe_trend() only ever compares subjects that carry a real,
   parseable year level (see _parse_year_level's docstring for exactly
   what "real" means here). It never infers an order from assessment
   names or row position -- there is no date/sequence field backing that,
   so any such ordering would be a guess, not evidence.
3. future_subjects_sharing_competency() is a plain set difference: which
   subjects touch this competency that this specific student has no
   results in yet. On a dataset where every student has already sat every
   offered subject (true of the current 3-subject fixture -- see
   python/README.md), this is always empty. That's an honest null result,
   not a bug -- it starts finding real candidates the moment a dataset
   spans students at different points in a multi-subject sequence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from ..data.excel_loader import LjaDataset
from .gap_detection import build_silo_to_competency_map
from .silo_clustering import SiloClusteringResult

TREND_IMPROVING = "improving"
TREND_STABLE = "stable"
TREND_DECLINING = "declining"
TREND_INSUFFICIENT = "insufficient evidence"

# Below this many percentage points of difference between the earliest and
# latest year-level subject, call it "stable" rather than a direction --
# not a measured threshold, a reasoned starting point (same spirit as
# OPENAI_TEMPERATURE's default in config.py). Revisit once there's a real
# multi-cohort dataset to tune it against.
_STABLE_BAND_PCT = 5.0

# "CSE1OOF" -> 1, "CSE2ALG" -> 2, "CSE3CAP" -> 3. This is reading a real
# digit out of the subject code, not guessing -- but it assumes a
# "<prefix><year digit><suffix>" naming convention that happens to hold for
# every subject code in the current dataset. It is NOT a general Moodle or
# university convention; a dataset that doesn't follow it should get None
# back (see _parse_year_level), not a wrong year.
_YEAR_LEVEL_RE = re.compile(r"^[A-Za-z]+(\d)")


@dataclass(frozen=True)
class SubjectEvidence:
    subject_code: str
    year_level: int | None  # None if subject_code doesn't match the CSE<year>... convention
    attainment_pct: float
    n_observations: int


def _parse_year_level(subject_code: str) -> int | None:
    """Best-effort only -- see the module docstring and this constant's own
    comment above. Returns None rather than guessing when the code doesn't
    match; callers must treat that as "no ordering signal", not "year 0".
    """
    match = _YEAR_LEVEL_RE.match(subject_code)
    return int(match.group(1)) if match else None


def subject_breakdown(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    student_id: str,
    competency_label: str,
) -> list[SubjectEvidence]:
    """The same (score, weight) observations compute_gaps() collapses into
    one attainment_pct for (student_id, competency_label), broken out per
    subject instead -- this is the number a "why is this a gap" question is
    actually asking for. Sorted by year level (unparseable codes last, then
    alphabetical) so a reader sees it in the order it happened, when that's
    knowable.
    """
    silo_to_competency = build_silo_to_competency_map(clustering)

    per_subject: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in dataset.results:
        if row.student_id != student_id:
            continue
        for silo_id in row.silo_ids:
            if silo_to_competency.get(f"{row.subject_code}:{silo_id}") == competency_label:
                per_subject[row.subject_code].append((row.score, row.weight))
                break  # one row can carry >1 SILO in this competency -- count the row once per subject

    evidence = []
    for subject_code, observations in per_subject.items():
        total_weight = sum(weight for _, weight in observations)
        attainment = sum(score * weight for score, weight in observations) / total_weight if total_weight else 0.0
        evidence.append(
            SubjectEvidence(
                subject_code=subject_code,
                year_level=_parse_year_level(subject_code),
                attainment_pct=round(attainment, 1),
                n_observations=len(observations),
            )
        )

    evidence.sort(key=lambda e: (e.year_level is None, e.year_level or 0, e.subject_code))
    return evidence


def describe_trend(evidence: list[SubjectEvidence], *, stable_band: float = _STABLE_BAND_PCT) -> str:
    """Compares only the subjects with a real year_level -- see the module
    docstring for why an assessment-name ordering isn't used instead.
    Fewer than two such subjects means there's nothing to compare, which is
    the common case for a single-subject competency (it can never be a
    "persistent gap" either, by compute_gaps()'s own definition).
    """
    ordered = sorted((e for e in evidence if e.year_level is not None), key=lambda e: e.year_level)
    if len(ordered) < 2:
        return TREND_INSUFFICIENT
    delta = ordered[-1].attainment_pct - ordered[0].attainment_pct
    if delta > stable_band:
        return TREND_IMPROVING
    if delta < -stable_band:
        return TREND_DECLINING
    return TREND_STABLE


def future_subjects_sharing_competency(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    student_id: str,
    competency_label: str,
) -> list[str]:
    """Subjects that touch this competency but this student has no results
    in yet -- candidates to flag for intervention *if* they're taken later,
    never "avoid": mastery estimates here are formative signals, not a
    reason to gatekeep enrollment (see the project proposal's guardrails).
    """
    summary = next((s for s in dataset.student_summaries if s.student_id == student_id), None)
    if summary is None:
        # Unknown student -- an empty "already taken" set would make every
        # subject in the competency look like a future one, which isn't a
        # real recommendation for a student we know nothing about.
        return []
    already_taken = set(summary.subject_totals.keys())

    cluster = next((c for c in clustering.clusters if c.competency_label == competency_label), None)
    if cluster is None:
        return []
    subjects_in_competency = {member.subject_code for member in cluster.members}

    return sorted(subjects_in_competency - already_taken)
