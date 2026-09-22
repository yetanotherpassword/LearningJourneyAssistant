"""Outcome (SILO) quality and cross-subject progression, computed from a
finished pipeline run -- no LLM call, no new stage.

Why this exists
---------------
The clustering step already tells us which SILOs are badly written
(`SiloClusteringResult.flagged_silos`, with a reason each) and which SILOs
link to nothing outside their own subject (a cluster with one member). Until
now that surfaced only in the CLI's printout and clusters.csv; the
dashboard never showed it, so a coordinator could not see that CSE2ALG's
first outcome was flagged "vague wording". This module turns the clustering,
the dataset and the gap rows into three things a page can draw:

* per-SILO and per-subject quality: flagged, unlinked, unassessed, vaguely
  worded, and how students actually fare on it;
* the vocabulary of the outcomes themselves, with each term classed as a
  measurable verb (analyse, implement, evaluate) or a vague one (understand,
  appreciate, be aware of), which is the oldest test of an outcome's
  assessability there is (Bloom, 1956; Anderson & Krathwohl, 2001);
* progression: for a competency that several subjects claim to teach, mean
  attainment and gap rate subject by subject in year order, so "students get
  worse at this between first and second year" is a figure, not a feeling.

Everything is a pure function of (dataset, clustering, gaps). Attainment
per SILO uses the same weight-weighted mean as gap_detection.py, so a figure
here and a figure on the student page cannot disagree about the same rows.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import fmean

from ..data.excel_loader import LjaDataset
from .gap_detection import CompetencyGap, build_silo_to_competency_map
from .gap_evidence import _STABLE_BAND_PCT, _parse_year_level
from .silo_clustering import SiloClusteringResult

_GAP_CLASSIFICATIONS = frozenset({"persistent gap", "isolated gap"})

# Vocabulary classes for the outcome word cloud. "Vague" terms are the ones
# that cannot be observed in a student's work -- an assessor cannot mark
# "appreciate". "Measurable" terms name something a student does that can
# be seen and scored. Matched on simple stems so "analysing" and "analysed"
# both count as "analyse". Everything else is "other" and rendered muted.
VAGUE_STEMS: frozenset[str] = frozenset(
    {
        # Verbs (and their noun forms) that name a mental state rather than an
        # observable act. Deliberately NOT qualifiers like "basic" or
        # "general": "basic data structures" is a perfectly specific outcome.
        "understand", "appreciat", "aware", "familiar", "know", "learn", "gain", "expos",
        "introduc", "overview", "recogni", "comprehend", "grasp", "insight", "acquir", "realis", "realiz",
    }
)
MEASURABLE_STEMS: frozenset[str] = frozenset(
    {
        "analys", "analyz", "appl", "design", "implement", "evaluat", "compar", "construct", "build",
        "develop", "demonstrat", "creat", "test", "justif", "critiqu", "critical", "explain", "identif",
        "select", "solv", "writ", "communicat", "present", "plan", "manag", "measur", "deriv", "model",
        "specif", "assess", "argu", "interpret", "classif", "calculat", "comput", "document", "report",
        "produc", "program", "debug", "refactor", "optimis", "optimiz", "verif", "validat", "formulat",
        "estimat", "predict", "simulat", "prove", "derive", "synthesis", "synthesiz", "organis", "organiz",
    }
)
_STOPWORDS: frozenset[str] = frozenset(
    """a an the and or of to in on for with by as at from into is are be been being that this these those
    their its it they them which who whose when where while than then such using use used via per each
    both all any own other more most also not but will can may should would could well one two three
    how what within between across through about over under after before during upon out up down off
    i we you he she your our his her etc e.g i.e including include includes related relating""".split()
)
_TOKEN = re.compile(r"[a-z][a-z\-]{2,}")


def slugify(label: str) -> str:
    """URL-safe key for a competency label: lowercase, hyphens, nothing else."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "competency"


def term_kind(term: str) -> str:
    """'vague' | 'measurable' | 'other' for one lowercase token."""
    for stem in MEASURABLE_STEMS:
        if term.startswith(stem):
            return "measurable"
    for stem in VAGUE_STEMS:
        if term.startswith(stem):
            return "vague"
    return "other"


def _terms(text: str) -> list[str]:
    """Distinct content words of one SILO, in order of first appearance."""
    seen: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        token = token.strip("-")
        if len(token) < 3 or token in _STOPWORDS or token in seen:
            continue
        seen.append(token)
    return seen


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """Mean of (score, weight) pairs, weight-weighted like gap_detection.py.
    None when there is nothing to average; a zero-weight set falls back to
    an unweighted mean so a row with weight 0 still counts as evidence."""
    if not pairs:
        return None
    total_weight = sum(w for _, w in pairs)
    if total_weight <= 0:
        return round(fmean(s for s, _ in pairs), 2)
    return round(sum(s * w for s, w in pairs) / total_weight, 2)


@dataclass(frozen=True)
class SiloQuality:
    key: str
    subject_code: str
    silo_local_id: str
    text: str
    competency_label: str | None  # None when the clustering never placed it
    cluster_span: int  # subjects represented in its cluster; 1 = links to nothing else
    flagged: bool
    flag_reason: str
    vague_terms: tuple[str, ...]
    n_assessments: int
    n_students: int
    mean_attainment: float | None
    gap_rate: float | None  # share of evidenced students whose competency is a gap

    @property
    def orphan(self) -> bool:
        return self.cluster_span <= 1

    @property
    def issues(self) -> tuple[str, ...]:
        found: list[str] = []
        if self.flagged:
            found.append("flagged")
        if self.orphan:
            found.append("no cross-subject link")
        if self.n_assessments == 0:
            found.append("not assessed")
        if self.vague_terms:
            found.append("vague wording")
        return tuple(found)


@dataclass(frozen=True)
class SubjectQuality:
    subject_code: str
    year_level: int | None
    n_silos: int
    n_flagged: int
    n_orphan: int
    n_unassessed: int
    n_vague: int
    n_clean: int
    n_students: int
    mean_attainment: float | None
    gap_rate: float | None

    @property
    def health(self) -> float:
        """Share of this subject's SILOs with no issue at all, as a percentage.
        Deliberately a count, not a weighted score: a weighting would be a
        number nobody has agreed, and the four counts are shown beside it."""
        if self.n_silos == 0:
            return 0.0
        return round(100.0 * self.n_clean / self.n_silos, 1)


@dataclass(frozen=True)
class TermWeight:
    term: str
    kind: str  # vague | measurable | other
    count: int  # SILOs containing the term
    n_subjects: int
    mean_attainment: float | None  # mean over the SILOs containing it


@dataclass(frozen=True)
class ProgressionPoint:
    subject_code: str
    year_level: int | None
    n_students: int
    mean_attainment: float | None
    gap_rate: float | None
    flagged: bool
    silo_keys: tuple[str, ...]


@dataclass(frozen=True)
class CompetencyProgression:
    label: str
    slug: str
    rationale: str
    points: tuple[ProgressionPoint, ...] = field(default_factory=tuple)

    @property
    def n_subjects(self) -> int:
        return len(self.points)

    @property
    def delta(self) -> float | None:
        """Mean attainment in the last subject minus the first, in year order."""
        measured = [p.mean_attainment for p in self.points if p.mean_attainment is not None]
        if len(measured) < 2:
            return None
        return round(measured[-1] - measured[0], 2)

    @property
    def trend(self) -> str:
        delta = self.delta
        if delta is None:
            return "insufficient evidence"
        if delta > _STABLE_BAND_PCT:
            return "improving"
        if delta < -_STABLE_BAND_PCT:
            return "declining"
        return "stable"


def _cluster_spans(clustering: SiloClusteringResult) -> dict[str, int]:
    """competency_label -> number of distinct subjects in that cluster."""
    return {
        cluster.competency_label: len({m.subject_code for m in cluster.members})
        for cluster in clustering.clusters
    }


def _gap_index(gaps: list[CompetencyGap]) -> dict[tuple[str, str], CompetencyGap]:
    return {(g.student_id, g.competency_label): g for g in gaps}


def assess_silos(dataset: LjaDataset, clustering: SiloClusteringResult, gaps: list[CompetencyGap]) -> list[SiloQuality]:
    """One row per SILO in the dataset, in subject then SILO order."""
    to_competency = build_silo_to_competency_map(clustering)
    spans = _cluster_spans(clustering)
    flags = {(f.subject_code, f.silo_local_id): f.reason for f in clustering.flagged_silos}
    gap_index = _gap_index(gaps)

    assessments_per_silo: Counter[str] = Counter()
    for assessment in dataset.assessments:
        for silo_id in assessment.silo_ids:
            assessments_per_silo[f"{assessment.subject_code}:{silo_id}"] += 1

    scores: dict[str, list[tuple[float, float]]] = defaultdict(list)
    students: dict[str, set[str]] = defaultdict(set)
    for row in dataset.results:
        for silo_id in row.silo_ids:
            key = f"{row.subject_code}:{silo_id}"
            scores[key].append((row.score, row.weight))
            students[key].add(row.student_id)

    rows: list[SiloQuality] = []
    for key in sorted(dataset.silos, key=_silo_sort_key):
        silo = dataset.silos[key]
        label = to_competency.get(key)
        evidenced = students.get(key, set())
        gap_rate: float | None = None
        if label is not None and evidenced:
            gap_hits = sum(
                1 for sid in evidenced
                if (g := gap_index.get((sid, label))) is not None and g.classification in _GAP_CLASSIFICATIONS
            )
            gap_rate = round(100.0 * gap_hits / len(evidenced), 1)
        rows.append(
            SiloQuality(
                key=key,
                subject_code=silo.subject_code,
                silo_local_id=silo.silo_local_id,
                text=silo.text,
                competency_label=label,
                cluster_span=spans.get(label, 0) if label is not None else 0,
                flagged=(silo.subject_code, silo.silo_local_id) in flags,
                flag_reason=flags.get((silo.subject_code, silo.silo_local_id), ""),
                vague_terms=tuple(t for t in _terms(silo.text) if term_kind(t) == "vague"),
                n_assessments=assessments_per_silo.get(key, 0),
                n_students=len(evidenced),
                mean_attainment=_weighted_mean(scores.get(key, [])),
                gap_rate=gap_rate,
            )
        )
    return rows


def _silo_sort_key(key: str) -> tuple[str, int, str]:
    subject, _, local = key.partition(":")
    digits = re.sub(r"\D", "", local)
    return (subject, int(digits) if digits else 0, local)


def summarise_subjects(silo_rows: list[SiloQuality], dataset: LjaDataset, gaps: list[CompetencyGap]) -> list[SubjectQuality]:
    """One row per subject, worst health first, then by code."""
    by_subject: dict[str, list[SiloQuality]] = defaultdict(list)
    for row in silo_rows:
        by_subject[row.subject_code].append(row)

    scores: dict[str, list[tuple[float, float]]] = defaultdict(list)
    students: dict[str, set[str]] = defaultdict(set)
    for r in dataset.results:
        scores[r.subject_code].append((r.score, r.weight))
        students[r.subject_code].add(r.student_id)
    gap_index = _gap_index(gaps)

    out: list[SubjectQuality] = []
    for subject, silos in by_subject.items():
        labels = {s.competency_label for s in silos if s.competency_label is not None}
        pairs = 0
        hits = 0
        for sid in students.get(subject, set()):
            for label in labels:
                gap = gap_index.get((sid, label))
                if gap is None:
                    continue
                pairs += 1
                if gap.classification in _GAP_CLASSIFICATIONS:
                    hits += 1
        out.append(
            SubjectQuality(
                subject_code=subject,
                year_level=_parse_year_level(subject),
                n_silos=len(silos),
                n_flagged=sum(1 for s in silos if s.flagged),
                n_orphan=sum(1 for s in silos if s.orphan),
                n_unassessed=sum(1 for s in silos if s.n_assessments == 0),
                n_vague=sum(1 for s in silos if s.vague_terms),
                n_clean=sum(1 for s in silos if not s.issues),
                n_students=len(students.get(subject, set())),
                mean_attainment=_weighted_mean(scores.get(subject, [])),
                gap_rate=round(100.0 * hits / pairs, 1) if pairs else None,
            )
        )
    return sorted(out, key=lambda s: (s.health, s.subject_code))


def term_weights(silo_rows: list[SiloQuality]) -> list[TermWeight]:
    """Vocabulary of every SILO text, most frequent first.

    A term counts once per SILO it appears in, however many times that SILO
    repeats it, so a single wordy outcome cannot dominate the cloud."""
    count: Counter[str] = Counter()
    subjects: dict[str, set[str]] = defaultdict(set)
    attainments: dict[str, list[float]] = defaultdict(list)
    for row in silo_rows:
        for term in _terms(row.text):
            count[term] += 1
            subjects[term].add(row.subject_code)
            if row.mean_attainment is not None:
                attainments[term].append(row.mean_attainment)
    return [
        TermWeight(
            term=term,
            kind=term_kind(term),
            count=n,
            n_subjects=len(subjects[term]),
            mean_attainment=round(fmean(attainments[term]), 2) if attainments[term] else None,
        )
        for term, n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def competency_progressions(
    dataset: LjaDataset, clustering: SiloClusteringResult, gaps: list[CompetencyGap]
) -> list[CompetencyProgression]:
    """For every competency taught in two or more subjects: attainment and gap
    rate per subject, subjects in year order. Single-subject competencies are
    left out because there is no progression to show; they appear on the
    SILO table as 'no cross-subject link' instead."""
    flags = {(f.subject_code, f.silo_local_id) for f in clustering.flagged_silos}
    gap_index = _gap_index(gaps)

    scores: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    students: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in dataset.results:
        for silo_id in row.silo_ids:
            scores[(row.subject_code, silo_id)].append((row.score, row.weight))
            students[(row.subject_code, silo_id)].add(row.student_id)

    out: list[CompetencyProgression] = []
    for cluster in clustering.clusters:
        by_subject: dict[str, list[str]] = defaultdict(list)
        for m in cluster.members:
            by_subject[m.subject_code].append(m.silo_local_id)
        if len(by_subject) < 2:
            continue
        points: list[ProgressionPoint] = []
        for subject, local_ids in by_subject.items():
            pairs = [p for lid in local_ids for p in scores.get((subject, lid), [])]
            evidenced = set().union(*(students.get((subject, lid), set()) for lid in local_ids))
            hits = sum(
                1 for sid in evidenced
                if (g := gap_index.get((sid, cluster.competency_label))) is not None
                and g.classification in _GAP_CLASSIFICATIONS
            )
            points.append(
                ProgressionPoint(
                    subject_code=subject,
                    year_level=_parse_year_level(subject),
                    n_students=len(evidenced),
                    mean_attainment=_weighted_mean(pairs),
                    gap_rate=round(100.0 * hits / len(evidenced), 1) if evidenced else None,
                    flagged=any((subject, lid) in flags for lid in local_ids),
                    silo_keys=tuple(f"{subject}:{lid}" for lid in sorted(local_ids, key=_silo_sort_key)),
                )
            )
        points.sort(key=lambda p: (p.year_level if p.year_level is not None else 99, p.subject_code))
        out.append(
            CompetencyProgression(
                label=cluster.competency_label,
                slug=slugify(cluster.competency_label),
                rationale=cluster.rationale,
                points=tuple(points),
            )
        )
    return sorted(out, key=lambda c: c.label.lower())


@dataclass(frozen=True)
class SubjectLinks:
    """Symmetric matrix of how many competencies each pair of subjects shares --
    the input a chord diagram wants -- plus the labels behind every cell."""

    subjects: tuple[str, ...]
    matrix: tuple[tuple[int, ...], ...]
    shared: dict[tuple[str, str], tuple[str, ...]]


def subject_links(clustering: SiloClusteringResult) -> SubjectLinks:
    subjects = sorted({m.subject_code for c in clustering.clusters for m in c.members})
    index = {s: i for i, s in enumerate(subjects)}
    matrix = [[0] * len(subjects) for _ in subjects]
    shared: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cluster in clustering.clusters:
        members = sorted({m.subject_code for m in cluster.members})
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                matrix[index[a]][index[b]] += 1
                matrix[index[b]][index[a]] += 1
                shared[(a, b)].append(cluster.competency_label)
    return SubjectLinks(
        subjects=tuple(subjects),
        matrix=tuple(tuple(r) for r in matrix),
        shared={k: tuple(v) for k, v in shared.items()},
    )


@dataclass(frozen=True)
class AttainmentMatrix:
    subjects: tuple[str, ...]  # year order
    competencies: tuple[str, ...]
    cells: tuple[tuple[float | None, ...], ...]  # [subject][competency], None = not taught there


def subject_competency_matrix(dataset: LjaDataset, clustering: SiloClusteringResult) -> AttainmentMatrix:
    """Mean attainment per subject x competency; None where the subject has no
    SILO in that competency, which is different from a low score and is drawn
    as an empty cell rather than a zero."""
    to_competency = build_silo_to_competency_map(clustering)
    competencies = sorted({c.competency_label for c in clustering.clusters}, key=str.lower)
    subjects = sorted(
        {s.subject_code for s in dataset.silos.values()},
        key=lambda s: (_parse_year_level(s) if _parse_year_level(s) is not None else 99, s),
    )
    scores: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in dataset.results:
        for silo_id in row.silo_ids:
            label = to_competency.get(f"{row.subject_code}:{silo_id}")
            if label is not None:
                scores[(row.subject_code, label)].append((row.score, row.weight))
    cells = tuple(
        tuple(_weighted_mean(scores.get((subject, label), [])) for label in competencies)
        for subject in subjects
    )
    return AttainmentMatrix(subjects=tuple(subjects), competencies=tuple(competencies), cells=cells)
