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
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..data.excel_loader import LjaDataset
from .silo_clustering import SiloClusteringResult

# Placeholders, same as sql/moodle_attainment_extraction.sql Query 6 -- do
# not treat these as settled; confirm with the project owner.
DEFAULT_LOW_THRESHOLD = 50.0
DEFAULT_HIGH_THRESHOLD = 65.0


@dataclass(frozen=True)
class CompetencyGap:
    student_id: str
    competency_label: str
    attainment_pct: float
    subjects_evidencing: int
    n_observations: int
    classification: str  # "persistent gap" | "isolated gap" | "developing" | "proficient"


def build_silo_to_competency_map(clustering: SiloClusteringResult) -> dict[str, str]:
    """"SUBJECT:SILOn" -> competency_label, flattened from the LLM's clusters."""
    mapping: dict[str, str] = {}
    for cluster in clustering.clusters:
        for member in cluster.members:
            mapping[f"{member.subject_code}:{member.silo_local_id}"] = cluster.competency_label
    return mapping


def _classify(attainment_pct: float, subjects_evidencing: int, low: float, high: float) -> str:
    if attainment_pct < low and subjects_evidencing >= 2:
        return "persistent gap"
    if attainment_pct < low:
        return "isolated gap"
    if attainment_pct < high:
        return "developing"
    return "proficient"


def compute_gaps(
    dataset: LjaDataset,
    clustering: SiloClusteringResult,
    *,
    low_threshold: float = DEFAULT_LOW_THRESHOLD,
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
) -> list[CompetencyGap]:
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

    gaps: list[CompetencyGap] = []
    for (student_id, competency), observations in buckets.items():
        total_weight = sum(weight for _, weight, _ in observations)
        attainment = (
            sum(score * weight for score, weight, _ in observations) / total_weight
            if total_weight
            else 0.0
        )
        subjects_evidencing = len({subject for _, _, subject in observations})
        gaps.append(
            CompetencyGap(
                student_id=student_id,
                competency_label=competency,
                attainment_pct=round(attainment, 1),
                subjects_evidencing=subjects_evidencing,
                n_observations=len(observations),
                classification=_classify(attainment, subjects_evidencing, low_threshold, high_threshold),
            )
        )

    return gaps
