"""Per-student, per-competency gap classification -- the Excel-path
equivalent of SQL Query 6 in sql/moodle_attainment_extraction.sql. Same
shape of answer (weighted attainment, persistent vs isolated gap), computed
from LLM-clustered SILOs instead of a staff-confirmed criterion map, because
that confirmation step doesn't exist yet on this path -- see
silo_clustering.py's module docstring.

Design decision worth flagging to Scott, not just burying in code: when one
assessment addresses several SILOs at once (e.g. CSE1OOF's Test covers
SILO1 and SILO2), this treats the assessment's single overall score as full
evidence for EVERY SILO it touches, weighted by that assessment's own
Weight -- it does not split or dilute the score across SILOs. That mirrors
how the rubric-criterion model would work if each SILO had its own graded
criterion, but here we only have one score per assessment, not one per
SILO, so it's an approximation. If the discrepancy that matters is
"assessment X barely touches SILO2 but heavily assesses SILO1", this
weighting can't see that -- worth asking Scott whether that distinction is
needed later.

Classification is RELATIVE, not absolute
----------------------------------------
The lodged tender, requirement 4, promises gap detection based on the
variability within an individual student's profile, explicitly "rather than
raw pass or fail thresholds". So the primary signal is where a competency
sits against *that student's own* median, measured in median-absolute
deviations (MAD).

Median and MAD rather than mean and standard deviation, deliberately:
students carry roughly 4-8 competencies, and at that n a single
catastrophic result drags the mean far enough to hide everything else. The
median barely moves.

Pure relative classification has two degenerate cases that are each *worse*
than the absolute logic this replaces, so two absolute guards remain:

  * A uniformly weak student -- every competency around 35% -- has almost no
    within-profile variance, so relative logic finds no outliers and reports
    NO GAPS to someone failing everything. The **floor** catches that.
  * A uniformly strong student -- everything at 90% except one at 85% -- has
    their merely-very-good competency flagged as a gap. That is worse than
    useless: it teaches students to distrust the tool. The **ceiling**
    catches that.

And where the profile is too flat or too short to reason about at all, this
falls back to absolute classification and *records that it did* rather than
quietly reporting a relative verdict it cannot support.

Every threshold lives in lja/config.py as an LJA_* environment variable.
There are deliberately no numeric literals in this module -- the values are
a team decision (see docs/meetings/actions.md, action A-01) and Sprint 5
sensitivity-tests them, which must not require a code change.

The full rationale, including the defaults and the cases they guard, is in
docs/adr/0001-relative-gap-detection.md.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass

from .. import config
from ..data.excel_loader import LjaDataset
from .silo_clustering import SiloClusteringResult

# How a classification was arrived at. Recorded per competency because
# tender requirement 5 promises every displayed figure is traceable to a
# source record, and "you have a gap here" with no visible basis is not
# traceable. Sprint 5's feedback evidence panel renders exactly this.
BASIS_RELATIVE = "relative position"
BASIS_FLOOR = "absolute floor"
BASIS_CEILING = "absolute ceiling"
BASIS_INSUFFICIENT = "insufficient data"

PERSISTENT_GAP = "persistent gap"
ISOLATED_GAP = "isolated gap"
DEVELOPING = "developing"
PROFICIENT = "proficient"


@dataclass(frozen=True)
class GapThresholds:
    """The tunables, defaulted from config so there is one source of truth.

    Passed as an object rather than six keyword arguments because callers
    (the CLI, the dashboard entry point, Sprint 5's sensitivity harness)
    thread them straight through, and a six-argument signature invites
    positional mistakes that type checking will not catch.
    """

    absolute_floor: float = config.GAP_ABSOLUTE_FLOOR
    absolute_ceiling: float = config.GAP_ABSOLUTE_CEILING
    relative_gap_cutoff: float = config.GAP_RELATIVE_GAP_CUTOFF
    relative_strong_cutoff: float = config.GAP_RELATIVE_STRONG_CUTOFF
    min_competencies: int = config.GAP_MIN_COMPETENCIES
    min_spread: float = config.GAP_MIN_SPREAD
    fallback_proficient: float = config.GAP_FALLBACK_PROFICIENT


@dataclass(frozen=True)
class CompetencyGap:
    student_id: str
    competency_label: str
    attainment_pct: float
    subjects_evidencing: int
    n_observations: int
    classification: str  # "persistent gap" | "isolated gap" | "developing" | "proficient"
    # How the classification was reached -- one of the BASIS_* constants.
    classification_basis: str
    # Position relative to this student's own median, in MAD units. None
    # whenever the relative path was not the one taken, because reporting a
    # number that did not drive the verdict is worse than reporting none.
    relative_position: float | None


def build_silo_to_competency_map(clustering: SiloClusteringResult) -> dict[str, str]:
    """"SUBJECT:SILOn" -> competency_label, flattened from the LLM's clusters."""
    mapping: dict[str, str] = {}
    for cluster in clustering.clusters:
        for member in cluster.members:
            mapping[f"{member.subject_code}:{member.silo_local_id}"] = cluster.competency_label
    return mapping


def profile_spread(attainments: list[float]) -> tuple[float, float]:
    """(median, median absolute deviation) for one student's whole profile.

    MAD is the median of the absolute deviations from the median -- not
    scaled by the usual 1.4826 constant that would make it approximate a
    standard deviation. Left unscaled on purpose: the cut-offs are expressed
    directly in MAD units, and introducing a normal-distribution scaling
    factor would imply an assumption about the shape of a 4-8 point
    distribution that nothing here justifies.
    """
    median = statistics.median(attainments)
    mad = statistics.median([abs(a - median) for a in attainments])
    return median, mad


def _gap_label(subjects_evidencing: int) -> str:
    """Persistent vs isolated, orthogonal to HOW the gap was detected.

    This distinction survives the move to relative classification unchanged:
    it describes whether the gap recurs across subjects or is confined to
    one, which is a different question from whether it is a gap at all.
    Sprint 5's study-strategy generation depends on it.
    """
    return PERSISTENT_GAP if subjects_evidencing >= 2 else ISOLATED_GAP


def _classify(
    attainment: float,
    subjects_evidencing: int,
    *,
    profile_median: float,
    profile_mad: float,
    n_competencies: int,
    thresholds: GapThresholds,
) -> tuple[str, str, float | None]:
    """-> (classification, basis, relative position or None).

    Order matters and is not arbitrary. The absolute guards are checked
    FIRST, before the has-enough-spread test, because they are the cases
    where the relative answer is known to be wrong rather than merely
    unsupported -- a uniformly weak student trips the floor and a uniformly
    strong one trips the ceiling, and in both the profile is also flat, so
    testing spread first would route them to the fallback and lose the
    explicit reason.
    """
    if attainment < thresholds.absolute_floor:
        return _gap_label(subjects_evidencing), BASIS_FLOOR, None

    if attainment >= thresholds.absolute_ceiling:
        return PROFICIENT, BASIS_CEILING, None

    # Not enough profile to reason about relatively. Fall back to the
    # previous absolute semantics and say so, rather than dividing by a
    # spread that is really rounding noise.
    if n_competencies < thresholds.min_competencies or profile_mad < thresholds.min_spread:
        classification = PROFICIENT if attainment >= thresholds.fallback_proficient else DEVELOPING
        return classification, BASIS_INSUFFICIENT, None

    relative_position = (attainment - profile_median) / profile_mad

    if relative_position <= thresholds.relative_gap_cutoff:
        return _gap_label(subjects_evidencing), BASIS_RELATIVE, round(relative_position, 2)
    if relative_position >= thresholds.relative_strong_cutoff:
        return PROFICIENT, BASIS_RELATIVE, round(relative_position, 2)
    return DEVELOPING, BASIS_RELATIVE, round(relative_position, 2)


def compute_gaps(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    *,
    thresholds: GapThresholds | None = None,
) -> list[CompetencyGap]:
    thresholds = thresholds or GapThresholds()
    silo_to_competency = build_silo_to_competency_map(clustering)

    # (student_id, competency_label) -> [(score, assessment_weight, subject_code), ...]
    buckets: dict[tuple[str, str], list[tuple[float, float, str]]] = defaultdict(list)

    for row in dataset.results:
        for silo_id in row.silo_ids:
            competency = silo_to_competency.get(f"{row.subject_code}:{silo_id}")
            if competency is None:
                # Shouldn't happen if cluster_silos()'s coverage check passed,
                # but don't let one bad row silently corrupt an average.
                raise KeyError(
                    f"No competency mapping for {row.subject_code}:{silo_id} "
                    f"(student {row.student_id}) -- clustering coverage check should"
                    f" have caught this before compute_gaps() ran."
                )
            buckets[(row.student_id, competency)].append((row.score, row.weight, row.subject_code))

    # Weighted attainment first, unchanged -- see the module docstring's
    # flagged approximation. Classification cannot happen in the same pass
    # any more: a competency's verdict now depends on the student's OTHER
    # competencies, so the whole profile has to exist before any of it is
    # classified.
    attainments: dict[tuple[str, str], float] = {}
    evidence: dict[tuple[str, str], tuple[int, int]] = {}
    for key, observations in buckets.items():
        total_weight = sum(weight for _, weight, _ in observations)
        attainment = (
            sum(score * weight for score, weight, _ in observations) / total_weight
            if total_weight
            else 0.0
        )
        attainments[key] = attainment
        evidence[key] = (len({subject for _, _, subject in observations}), len(observations))

    profiles: dict[str, list[float]] = defaultdict(list)
    for (student_id, _competency), attainment in attainments.items():
        profiles[student_id].append(attainment)

    gaps: list[CompetencyGap] = []
    for (student_id, competency), attainment in attainments.items():
        profile = profiles[student_id]
        median, mad = profile_spread(profile)
        subjects_evidencing, n_observations = evidence[(student_id, competency)]

        classification, basis, relative_position = _classify(
            attainment,
            subjects_evidencing,
            profile_median=median,
            profile_mad=mad,
            n_competencies=len(profile),
            thresholds=thresholds,
        )

        gaps.append(
            CompetencyGap(
                student_id=student_id,
                competency_label=competency,
                attainment_pct=round(attainment, 1),
                subjects_evidencing=subjects_evidencing,
                n_observations=n_observations,
                classification=classification,
                classification_basis=basis,
                relative_position=relative_position,
            )
        )

    return gaps
