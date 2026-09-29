"""FastAPI dashboard -- a read-only view over an already-computed pipeline
run (a loaded LjaDataset + the CompetencyGap list compute_gaps() produced).

Deliberately a factory (create_app) rather than a module-level `app` object:
it takes its data as arguments instead of loading Excel/cache files itself,
so tests can hand it small in-memory fixtures with no real dataset, no
clustering cache, and no LLM involved -- see tests/test_dashboard.py. The
actual "load real data and serve it" wiring lives in __main__.py.

This app never calls an LLM and never writes anything -- it only reads what
`python -m lja.cli` already computed. See __main__.py for what happens if
the clustering cache doesn't exist yet.

Cohorts and the stat strip
--------------------------
Each tile on the index is a link into /cohort/{key}, and both pages render
the same view model (student table + descriptive statistics + charts) over a
different subset. The subsets live in _COHORTS below rather than in the
templates, so adding one is a registry entry and not a new route plus a new
page -- see the Sec 9 note there about the "At Risk" cohort that is
deliberately *not* registered yet.

All the aggregation happens here, not in Jinja. That is a house rule from
the sprint runbook (Sec 7) and it is what makes the numbers testable: a
template that computes its own totals can only be checked by scraping HTML.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..data.excel_loader import LjaDataset, StudentSummary
from ..model.gap_detection import (
    BASIS_CEILING,
    BASIS_FLOOR,
    BASIS_INSUFFICIENT,
    BASIS_RELATIVE,
    CompetencyGap,
    GapThresholds,
)
from ..model.gap_evidence import describe_trend, future_subjects_sharing_competency, subject_breakdown
from ..model.learning_plan import LearningPlan
from ..model.silo_clustering import SiloClusteringResult
from ..model.silo_quality import (
    assess_silos,
    competency_progressions,
    discipline_links,
    discipline_of,
    slugify,
    subject_competency_matrix,
    subject_links,
    summarise_subjects,
    term_weights,
)
from .run_info import RunInfo
from .stats import histogram, summarise

# The progress chart on the student page draws at most this many competency
# lines; beyond that a line chart is unreadable and the table carries the rest.
PROGRESS_CHART_MAX = 8

# Below this many subjects the chord draws one arc per subject; above it,
# one arc per discipline (subject-code prefix), because a subject-level chord
# is a hairball well before a hundred arcs. The subject explorer below the
# chord carries the per-subject detail at any size.
_MAX_SUBJECT_CHORD = 16

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

# Worst first -- a reviewer scanning a student's gap table should see the
# thing that actually needs attention before "proficient" rows.
_CLASSIFICATION_ORDER = ["persistent gap", "isolated gap", "developing", "proficient"]

# Only these classifications get a "future subjects to flag" list -- a
# proficient or developing competency isn't a gap, so there's nothing to
# warn a student about yet.
_AT_RISK_CLASSIFICATIONS = {"persistent gap", "isolated gap"}

# A gap is persistent when this many subjects evidence it (gap_detection's
# _gap_label). Stated here so the rules panel prints the same number the
# classifier uses rather than a hand-typed copy of it.
PERSISTENT_MIN_SUBJECTS = 2

# Each priority group on the index shows this many of its students; the
# group's cohort page and the full table underneath carry everyone.
PRIORITY_PREVIEW_SIZE = 10

# Priority groups. Three, because that is how many distinctions the
# classifier's existing rules make between flagged students without a new
# number: a floor breach is a gap whatever the profile (absolute rule), a
# persistent relative gap recurs across subjects, an isolated one does not.
# Splitting any group further (by depth, by count) needs a cut-off nobody
# has ratified -- that is the A-01 decision, not a dashboard default.
_PRIORITY_DEFINITIONS: tuple[dict, ...] = (
    {"rank": 1, "key": "priority-1", "ordinal": "1st", "label": "below the {floor}% floor",
     "blurb": ("At least one competency below the absolute floor of {floor}% -- a gap regardless of how "
               "the rest of the profile looks. Ordered by the student's lowest flagged mark.")},
    {"rank": 2, "key": "priority-2", "ordinal": "2nd", "label": "persistent gap, relative only",
     "blurb": ("No mark below the {floor}% floor, but at least one persistent gap: a competency evidenced in "
               "{persistent_min_subjects}+ subjects that sits {gap_cutoff} MAD or more below the student's own "
               "median. These students are weaker in one area than in their others, not failing it. "
               "Ordered by the student's lowest flagged mark.")},
    {"rank": 3, "key": "priority-3", "ordinal": "3rd", "label": "isolated gaps only",
     "blurb": ("No floor breach and no persistent gap; every flag is an isolated gap, seen in a single "
               "subject. Ordered by the student's lowest flagged mark.")},
)

# One row per threshold for the /run page: which GapThresholds field, how it
# is set, and what it means. The meaning is text because the number alone
# ("-1.0") tells a coordinator nothing. Defaults are read from GapThresholds()
# at request time, not copied here, so this list cannot go stale on a value.
_THRESHOLD_ROWS: tuple[dict, ...] = (
    {"field": "absolute_floor", "unit": "%", "env": "LJA_GAP_ABSOLUTE_FLOOR", "flag": "--absolute-floor",
     "dashboard_flag": True,
     "meaning": "Attainment below this is a gap regardless of the student's own profile."},
    {"field": "absolute_ceiling", "unit": "%", "env": "LJA_GAP_ABSOLUTE_CEILING", "flag": "--absolute-ceiling",
     "dashboard_flag": True,
     "meaning": "Attainment at or above this is never a gap and always proficient."},
    {"field": "relative_gap_cutoff", "unit": "MAD", "env": "LJA_GAP_RELATIVE_GAP_CUTOFF", "flag": "--relative-gap-cutoff",
     "dashboard_flag": False,
     "meaning": "A competency this many MAD or more below the student's own median is a gap."},
    {"field": "relative_strong_cutoff", "unit": "MAD", "env": "LJA_GAP_RELATIVE_STRONG_CUTOFF", "flag": "--relative-strong-cutoff",
     "dashboard_flag": False,
     "meaning": "A competency this many MAD or more above the student's own median is proficient."},
    {"field": "min_competencies", "unit": "", "env": "LJA_GAP_MIN_COMPETENCIES", "flag": "--min-competencies",
     "dashboard_flag": False,
     "meaning": "Fewer competencies than this and the relative rule is not used for that student."},
    {"field": "min_spread", "unit": "MAD", "env": "LJA_GAP_MIN_SPREAD", "flag": "--min-spread",
     "dashboard_flag": False,
     "meaning": "A profile whose MAD is below this is treated as flat and the relative rule is not used."},
    {"field": "fallback_proficient", "unit": "%", "env": "LJA_GAP_FALLBACK_PROFICIENT", "flag": None,
     "dashboard_flag": False,
     "meaning": "When the relative rule is not used, attainment at or above this is proficient, below it developing."},
)

# Gap-mark histogram bins. Finer than the 10-point cohort histogram because
# the interesting question -- how many flagged gaps sit just under the
# ceiling versus under the floor -- lives inside a ten-point band.
_GAP_MARK_BIN = 5.0


@dataclass(frozen=True)
class _Cohort:
    """A named subset of students, with the sentence that explains it.

    `blurb` is not decoration. Tender requirement 5 asks that every displayed
    figure be traceable to a source record, and a page headed "23 students"
    with no statement of what put those 23 there fails that on its own terms.
    """

    key: str
    title: str
    tile_label: str
    blurb: str
    predicate: Callable[[StudentSummary, list[CompetencyGap]], bool]


def _has_persistent_gap(_summary: StudentSummary, gaps: list[CompetencyGap]) -> bool:
    return any(g.classification == "persistent gap" for g in gaps)


def _is_gap(gap: CompetencyGap) -> bool:
    return gap.classification in _AT_RISK_CLASSIFICATIONS


def priority_of(gaps: list[CompetencyGap]) -> int | None:
    """1, 2, 3 per _PRIORITY_DEFINITIONS, or None for a student with no gap."""
    gap_rows = [g for g in gaps if _is_gap(g)]
    if not gap_rows:
        return None
    if any(g.classification_basis == BASIS_FLOOR for g in gap_rows):
        return 1
    if any(g.classification == "persistent gap" for g in gap_rows):
        return 2
    return 3


def _priority_predicate(rank: int) -> Callable[[StudentSummary, list[CompetencyGap]], bool]:
    return lambda _summary, gaps: priority_of(gaps) == rank


# Registry, in tile order. Adding the "At Risk" cohort the team asked for is
# one entry here plus one tile in index.html -- but it is NOT added yet, and
# that is a decision rather than an oversight. Sprint 3 runbook Sec 9 lists the
# at-risk threshold as a stop-and-ask: Scott confirmed there is no
# institutional "at risk" number to match, so the definition is the team's to
# choose and defend, and it is due to be settled at WP2 planning alongside the
# relative-gap thresholds it will almost certainly be expressed in terms of.
# Guessing it here would bake an undefended number into a student-facing page.
_COHORTS: tuple[_Cohort, ...] = (
    _Cohort(
        key="all",
        title="All students",
        tile_label="students",
        blurb="Every student in the loaded dataset.",
        predicate=lambda _summary, _gaps: True,
    ),
    _Cohort(
        key="persistent-gap",
        title="Students with a persistent gap",
        tile_label="with a persistent gap",
        blurb=(
            "Students with at least one competency classified as a persistent gap -- "
            "a gap evidenced across two or more subjects, rather than confined to one."
        ),
        predicate=_has_persistent_gap,
    ),
    # The priority groups are not the "At Risk" cohort (see above): they add
    # no new number. Each is a combination of classifications the pipeline
    # already made, and the relative rule flags the weakest competencies of
    # almost everyone (the A-01 threshold finding, IOLG-113), so the split
    # that matters is floor breach versus relative-only. Blurbs and labels
    # are format strings so they print the thresholds actually in force.
    *(
        _Cohort(
            key=d["key"],
            title=f"{d['ordinal']} priority: {d['label']}",
            tile_label=f"{d['ordinal']} priority: {d['label']}",
            blurb=d["blurb"],
            predicate=_priority_predicate(d["rank"]),
        )
        for d in _PRIORITY_DEFINITIONS
    ),
)

_COHORTS_BY_KEY = {cohort.key: cohort for cohort in _COHORTS}


def create_app(
    dataset: LjaDataset,
    gaps: list[CompetencyGap],
    clustering: SiloClusteringResult,
    review_warning: str | None = None,
    thresholds: GapThresholds | None = None,
    run_info: RunInfo | None = None,
    plans_dir: Path | None = None,
) -> FastAPI:
    """`thresholds` must be the object compute_gaps() was given for `gaps`.

    The dashboard cannot recover the cut-offs from the gap rows, and the
    /run page prints them, so a caller that classified with one set and
    displays another would put an untrue statement on the page. Defaults
    to GapThresholds() because that is also compute_gaps()'s default.
    `run_info` is the provenance __main__.py collected; None (tests, or an
    embedding caller) leaves the /run page's command section out honestly.
    """
    thresholds = thresholds or GapThresholds()
    app = FastAPI(title="LJA Dashboard")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    templates.env.filters["slug"] = slugify
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Outcome quality and progression: computed once at start-up from the
    # same three inputs as everything else. Pure functions in
    # model/silo_quality.py; the page only formats what they return.
    silo_rows = assess_silos(dataset, clustering, gaps)
    silo_by_key = {row.key: row for row in silo_rows}
    subject_rows = summarise_subjects(silo_rows, dataset, gaps)
    terms = term_weights(silo_rows)
    progressions = competency_progressions(dataset, clustering, gaps)
    progression_by_slug = {p.slug: p for p in progressions}
    matrix = subject_competency_matrix(dataset, clustering)
    links = subject_links(clustering)
    disc_links = discipline_links(clustering)

    # Chord input, computed once: subject level for a small catalogue, the
    # discipline roll-up otherwise (or when every subject is one discipline,
    # where a one-arc chord would say nothing).
    if len(links.subjects) <= _MAX_SUBJECT_CHORD or len(disc_links.disciplines) < 2:
        chord_level = "subject"
        chord_payload = {
            "level": chord_level,
            "names": list(links.subjects),
            "sizes": [1] * len(links.subjects),
            "matrix": [list(r) for r in links.matrix],
            "shared": {f"{a}|{b}": list(v) for (a, b), v in links.shared.items()},
        }
    else:
        chord_level = "discipline"
        chord_payload = {
            "level": chord_level,
            "names": list(disc_links.disciplines),
            "sizes": list(disc_links.subject_counts),
            # The diagonal (links inside a discipline) is reported in the
            # tooltip but not drawn: a self-ribbon reads as noise.
            "matrix": [[0 if i == j else v for j, v in enumerate(r)] for i, r in enumerate(disc_links.matrix)],
            "internal": [disc_links.matrix[i][i] for i in range(len(disc_links.disciplines))],
            "shared": {f"{a}|{b}": list(v) for (a, b), v in disc_links.shared.items()},
        }

    # Subject explorer: every subject's partners, most shared first.
    partners: dict[str, list[dict]] = {s: [] for s in links.subjects}
    for (a, b), labels in links.shared.items():
        partners[a].append({"code": b, "labels": list(labels)})
        partners[b].append({"code": a, "labels": list(labels)})
    for rows in partners.values():
        rows.sort(key=lambda r: (-len(r["labels"]), r["code"]))
    explorer_subjects = sorted(links.subjects, key=lambda s: (-len(partners[s]), s))
    explorer_payload = {
        "subjects": [{"code": s, "discipline": discipline_of(s), "n": len(partners[s])} for s in explorer_subjects],
        "partners": partners,
    }

    gaps_by_student: dict[str, list[CompetencyGap]] = defaultdict(list)
    for gap in gaps:
        gaps_by_student[gap.student_id].append(gap)
    students_by_id = {s.student_id: s for s in dataset.student_summaries}
    # Header picker (base.html) -- every page needs it, so it is computed once.
    student_ids = sorted(students_by_id)

    # The rules in force, for the panel every cohort page opens with. One
    # dict built once from the thresholds object, so the panel cannot say
    # one thing while the classifier did another.
    rules = {
        "absolute_floor": thresholds.absolute_floor,
        "absolute_ceiling": thresholds.absolute_ceiling,
        "relative_gap_cutoff": thresholds.relative_gap_cutoff,
        "relative_strong_cutoff": thresholds.relative_strong_cutoff,
        "min_competencies": thresholds.min_competencies,
        "min_spread": thresholds.min_spread,
        "fallback_proficient": thresholds.fallback_proficient,
        "persistent_min_subjects": PERSISTENT_MIN_SUBJECTS,
    }

    def members(cohort: _Cohort) -> list[StudentSummary]:
        return [
            summary
            for summary in sorted(dataset.student_summaries, key=lambda s: s.student_id)
            if cohort.predicate(summary, gaps_by_student.get(summary.student_id, []))
        ]

    def row_for(summary: StudentSummary) -> dict:
        student_gaps = gaps_by_student.get(summary.student_id, [])
        counts = Counter(g.classification for g in student_gaps)
        student_gap_rows = [g for g in student_gaps if _is_gap(g)]
        positions = [g.relative_position for g in student_gap_rows if g.relative_position is not None]
        return {
            "student_id": summary.student_id,
            "average_total": summary.average_total,
            "performance_band": summary.performance_band,
            "persistent_gap_count": counts["persistent gap"],
            "isolated_gap_count": counts["isolated gap"],
            "strength_count": counts["proficient"],
            # Severity, from the classifier's own outputs and nothing else:
            # how many gaps tripped the absolute floor, the student's lowest
            # flagged mark, and how far below their own median it sits.
            "floor_gap_count": sum(1 for g in student_gap_rows if g.classification_basis == BASIS_FLOOR),
            "lowest_gap_pct": min((g.attainment_pct for g in student_gap_rows), default=None),
            # The student's lowest mark over every competency, gap or not:
            # the same measure for an unflagged student, so they can sit on
            # the same chart as a grey point.
            "lowest_pct": min((g.attainment_pct for g in student_gaps), default=None),
            "deepest_position": min(positions, default=None),
            "priority": priority_of(student_gaps),
        }

    def severity_key(row: dict) -> tuple:
        # Priority group first, then the lowest flagged mark within it, then
        # the number of persistent gaps. Student id last so the order is
        # total and a page reload cannot reshuffle equal rows.
        lowest = row["lowest_gap_pct"]
        return (
            row["priority"] if row["priority"] is not None else 99,
            lowest if lowest is not None else float("inf"),
            -row["persistent_gap_count"],
            row["student_id"],
        )

    def format_text(text: str) -> str:
        return text.format(
            floor=f"{thresholds.absolute_floor:g}",
            gap_cutoff=f"{-thresholds.relative_gap_cutoff:g}",
            persistent_min_subjects=PERSISTENT_MIN_SUBJECTS,
        )

    def view_model(cohort: _Cohort) -> dict:
        """Rows + descriptive statistics + both charts' data, for one cohort.

        Shared by the index and every cohort page so the two can never drift
        into computing the same figure two different ways.
        """
        summaries = members(cohort)
        rows = sorted((row_for(summary) for summary in summaries), key=severity_key)
        averages = [summary.average_total for summary in summaries]

        cohort_gaps = [g for summary in summaries for g in gaps_by_student.get(summary.student_id, [])]
        classification_counts = Counter(g.classification for g in cohort_gaps)
        bins = histogram(averages)

        # What actually put the flagged competencies where they are: how
        # many gap rows tripped the floor versus the relative rule, and how
        # the flagged marks are spread. This is the context the raw
        # "N with a persistent gap" tile lacks.
        gap_rows = [g for g in cohort_gaps if _is_gap(g)]
        basis_counts = Counter(g.classification_basis for g in gap_rows)
        gap_bins = histogram([g.attainment_pct for g in gap_rows], bin_width=_GAP_MARK_BIN)
        flagged_students = sum(1 for r in rows if r["persistent_gap_count"] or r["isolated_gap_count"])
        floor_students = sum(1 for r in rows if r["floor_gap_count"])

        return {
            "cohort": cohort,
            "cohort_title": format_text(cohort.title),
            "cohort_blurb": format_text(cohort.blurb),
            # One entry per priority group: definition, size, and a preview
            # of its worst rows. The cohort page for the group has them all.
            "priority_groups": [
                {
                    **d,
                    "label": format_text(d["label"]),
                    "blurb": format_text(d["blurb"]),
                    "count": sum(1 for r in rows if r["priority"] == d["rank"]),
                    "rows": [r for r in rows if r["priority"] == d["rank"]][:PRIORITY_PREVIEW_SIZE],
                }
                for d in _PRIORITY_DEFINITIONS
            ],
            "unflagged_count": sum(1 for r in rows if r["priority"] is None),
            "preview_size": PRIORITY_PREVIEW_SIZE,
            # Outlier chart: one point per student. Flagged students are
            # placed at their lowest flagged mark; unflagged ones (p = 0)
            # at their lowest competency mark, which by definition was not
            # a gap, so they show where the "no flag" region sits.
            "severity_scatter": json.dumps(
                [
                    {"id": r["student_id"], "x": round(r["average_total"], 1),
                     "y": round(r["lowest_gap_pct"] if r["priority"] is not None else r["lowest_pct"], 1),
                     "p": r["priority"] or 0}
                    for r in rows if (r["lowest_gap_pct"] if r["priority"] is not None else r["lowest_pct"]) is not None
                ]
            ),
            "severity_scatter_n": sum(1 for r in rows if r["priority"] is not None),
            "severity_scatter_unflagged": sum(1 for r in rows if r["priority"] is None and r["lowest_pct"] is not None),
            # The two absolute rules, drawn on the chart as the lines they are.
            "severity_lines": json.dumps({"floor": thresholds.absolute_floor, "ceiling": thresholds.absolute_ceiling}),
            "rules": rules,
            "gap_summary": {
                "students": len(rows),
                "flagged_students": flagged_students,
                "floor_students": floor_students,
                "relative_only_students": flagged_students - floor_students,
                "gap_rows": len(gap_rows),
                "basis_floor": basis_counts[BASIS_FLOOR],
                "basis_relative": basis_counts[BASIS_RELATIVE],
                # Counted so the panel can say "none" honestly; neither basis
                # can produce a gap (the ceiling means proficient, and the
                # fallback path never classifies below developing).
                "basis_other": basis_counts[BASIS_CEILING] + basis_counts[BASIS_INSUFFICIENT],
            },
            "gap_marks_data": json.dumps(
                {
                    "labels": [b.label for b in gap_bins],
                    "values": [b.count for b in gap_bins],
                    "below_floor": [b.upper <= thresholds.absolute_floor for b in gap_bins],
                    "floor": thresholds.absolute_floor,
                    "ceiling": thresholds.absolute_ceiling,
                }
            ),
            # Banner from base.html (IOLG-116): the same warning on every
            # page, sourced once here rather than per route.
            "review_warning": review_warning,
            "student_ids": student_ids,
            "rows": rows,
            "stats": summarise(averages),
            # Charts read their colours from the CSS custom properties at
            # render time (see _cohort_body.html), the same technique
            # student.html already uses, so a bar and a badge for the same
            # classification cannot drift apart.
            "distribution_data": json.dumps(
                {"labels": [b.label for b in bins], "values": [b.count for b in bins]}
            ),
            "classification_data": json.dumps(
                {
                    "labels": _CLASSIFICATION_ORDER,
                    "values": [classification_counts[c] for c in _CLASSIFICATION_ORDER],
                    "total": sum(classification_counts.values()),
                }
            ),
        }

    @app.get("/")
    def index(request: Request):
        context = view_model(_COHORTS_BY_KEY["all"])
        # Priority tiles sit on their own row, coloured by rank; the rest
        # on the row above. The rank comes from the registry key so the
        # template never has to know which cohorts are priorities.
        priority_rank = {d["key"]: d["rank"] for d in _PRIORITY_DEFINITIONS}
        context["tiles"] = [
            {
                "key": cohort.key,
                "count": len(members(cohort)),
                "label": format_text(cohort.tile_label),
                "rank": priority_rank.get(cohort.key),
            }
            for cohort in _COHORTS
        ]
        return templates.TemplateResponse(request, "index.html", context)

    @app.get("/cohort/{cohort_key}")
    def cohort_view(request: Request, cohort_key: str):
        cohort = _COHORTS_BY_KEY.get(cohort_key)
        if cohort is None:
            known = ", ".join(sorted(_COHORTS_BY_KEY))
            raise HTTPException(status_code=404, detail=f"No cohort {cohort_key!r} -- known cohorts: {known}")
        return templates.TemplateResponse(request, "cohort.html", view_model(cohort))

    @app.get("/cohort/{cohort_key}/students")
    def cohort_students(request: Request, cohort_key: str):
        """The whole cohort as one searchable, sortable table.

        The cohort page previews each priority group and scroll-boxes the
        rest under its charts; this page is the group and nothing else, so
        a coordinator working through 1,000 students has one long table
        with a filter box rather than a 60vh window. Same rows, same order,
        same row_for(): only the framing differs.
        """
        cohort = _COHORTS_BY_KEY.get(cohort_key)
        if cohort is None:
            known = ", ".join(sorted(_COHORTS_BY_KEY))
            raise HTTPException(status_code=404, detail=f"No cohort {cohort_key!r} -- known cohorts: {known}")
        rows = sorted((row_for(summary) for summary in members(cohort)), key=severity_key)
        return templates.TemplateResponse(
            request,
            "cohort_students.html",
            {
                "cohort": cohort,
                "cohort_title": format_text(cohort.title),
                "cohort_blurb": format_text(cohort.blurb),
                "rows": rows,
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    @app.get("/student/{student_id}")
    def student_detail(request: Request, student_id: str):
        summary = students_by_id.get(student_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"No student {student_id!r} in this dataset")

        student_gaps = sorted(
            gaps_by_student.get(student_id, []),
            key=lambda g: _CLASSIFICATION_ORDER.index(g.classification),
        )
        # Strongest first: furthest above the student's own median, then by
        # attainment for those classified on the absolute ceiling (no position).
        strengths = sorted(
            (g for g in student_gaps if g.classification == "proficient"),
            key=lambda g: (-(g.relative_position or 0.0), -g.attainment_pct),
        )
        chart_data = json.dumps(
            {
                "labels": [g.competency_label for g in student_gaps],
                "values": [g.attainment_pct for g in student_gaps],
                # Bar colors are resolved client-side from these CSS custom
                # properties (see student.html) so the chart and the
                # classification badges always share one color source.
                "classifications": [g.classification for g in student_gaps],
            }
        )

        # Evidence/trend/future-subjects per gap -- see gap_evidence.py for
        # what's grounded here vs deliberately not claimed (no LLM call).
        gap_details = []
        for gap in student_gaps:
            evidence = subject_breakdown(dataset, clustering, student_id, gap.competency_label)
            gap_details.append(
                {
                    "gap": gap,
                    "evidence": evidence,
                    "trend": describe_trend(evidence),
                    "future_subjects": (
                        future_subjects_sharing_competency(dataset, clustering, student_id, gap.competency_label)
                        if gap.classification in _AT_RISK_CLASSIFICATIONS
                        else None
                    ),
                }
            )

        # Progress across subjects (IOLG-107): the same per-subject evidence,
        # pivoted so each competency is a row and each subject a column, in
        # year-level order. Order, not time: the data carries no dates, so
        # this is "first-year subject, then second, then third" and nothing
        # more. The trend word is the one the gap card already shows.
        year_of = {e.subject_code: e.year_level for d in gap_details for e in d["evidence"]}
        progress_subjects = sorted(year_of, key=lambda c: (year_of[c] is None, year_of[c] or 0, c))
        progress_rows = []
        for d in gap_details:
            by_subject = {e.subject_code: e.attainment_pct for e in d["evidence"]}
            progress_rows.append(
                {
                    "competency_label": d["gap"].competency_label,
                    "classification": d["gap"].classification,
                    "values": [by_subject.get(c) for c in progress_subjects],
                    "trend": d["trend"],
                }
            )

        # The chart draws only competencies seen in two or more subjects (a
        # single point is not a progression) and at most PROGRESS_CHART_MAX
        # of them, gaps first because gap_details is already in severity
        # order; the table underneath always carries every row.
        chartable = [r for r in progress_rows if sum(v is not None for v in r["values"]) >= 2]
        progress_chart = json.dumps(
            {
                "labels": progress_subjects,
                "rows": chartable[:PROGRESS_CHART_MAX],
                "omitted": max(0, len(chartable) - PROGRESS_CHART_MAX),
            }
        )

        plan = None
        if plans_dir is not None:
            plan_path = plans_dir / f"learning_plan_{student_id}.json"
            if plan_path.exists():
                plan = LearningPlan.model_validate_json(
                    plan_path.read_text(encoding="utf-8")
                )

        return templates.TemplateResponse(
            request,
            "student.html",
            {
                "summary": summary,
                "plan": plan,
                "strengths": strengths,
                "gap_details": gap_details,
                "progress_subjects": progress_subjects,
                "progress_rows": progress_rows,
                "progress_chart": progress_chart,
                "chart_data": chart_data,
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    @app.get("/run")
    def run_details(request: Request):
        """Provenance and rules for the run every other page is showing."""
        defaults = GapThresholds()
        threshold_rows = []
        for spec in _THRESHOLD_ROWS:
            value = getattr(thresholds, spec["field"])
            default = getattr(defaults, spec["field"])
            env_value = run_info.environment.get(spec["env"]) if run_info else None
            threshold_rows.append(
                {
                    **spec,
                    "value": value,
                    "default": default,
                    "env_value": env_value,
                    # "changed" means the value on this page differs from the
                    # code default in gap_detection/config; how it was changed
                    # (env var or flag) is shown beside it when known.
                    "changed": value != default,
                }
            )
        everyone = view_model(_COHORTS_BY_KEY["all"])
        n_clusters = len(clustering.clusters)
        n_silos_clustered = sum(len(c.members) for c in clustering.clusters)
        return templates.TemplateResponse(
            request,
            "run.html",
            {
                "run_info": run_info,
                "rules": rules,
                "threshold_rows": threshold_rows,
                "gap_summary": everyone["gap_summary"],
                "gap_marks_data": everyone["gap_marks_data"],
                "inputs": {
                    "students": len(dataset.student_summaries),
                    "subjects": len(subject_rows),
                    "silos": len(dataset.silos),
                    "assessments": len(dataset.assessments),
                    "results": len(dataset.results),
                    "clusters": n_clusters,
                    "silos_clustered": n_silos_clustered,
                    "gap_rows": len(gaps),
                },
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    @app.get("/glossary")
    def glossary(request: Request):
        """Every term, defined once, with this run's values where a rule applies."""
        return templates.TemplateResponse(
            request,
            "glossary.html",
            {"rules": rules, "review_warning": review_warning, "student_ids": student_ids},
        )

    # --- list pages: every count tile links to one of these -----------------
    #
    # A tile that shows "448 SILOs" links to the 448; "5 link to no other
    # subject" links to the 5. Same rule as the cohort tiles on the index
    # (tender requirement 5: a displayed figure is traceable), applied to
    # every page. Membership is decided here, never in a template.

    subject_by_code = {s.subject_code: s for s in subject_rows}
    silos_by_subject: dict[str, list] = defaultdict(list)
    for row in silo_rows:
        silos_by_subject[row.subject_code].append(row)
    results_per_assessment = Counter((r.subject_code, r.assessment_name) for r in dataset.results)
    mapped_assessments = {(a.subject_code, a.assessment_name) for a in dataset.assessments}
    unmapped_results = sum(n for key, n in results_per_assessment.items() if key not in mapped_assessments)
    gap_counts_by_label: dict[str, Counter] = defaultdict(Counter)
    for gap in gaps:
        gap_counts_by_label[gap.competency_label][gap.classification] += 1

    score_sums: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    for r in dataset.results:
        acc = score_sums[(r.subject_code, r.assessment_name)]
        acc[0] += r.score
        acc[1] += 1

    def mean_score(subject_code: str, name: str) -> float | None:
        total, n = score_sums.get((subject_code, name), (0.0, 0))
        return round(total / n, 1) if n else None

    def assessment_rows(subject_code: str | None = None) -> list[dict]:
        return [
            {
                "subject_code": a.subject_code,
                "assessment_name": a.assessment_name,
                "mean_score": mean_score(a.subject_code, a.assessment_name),
                # The supplied workbook carries weights as percentages (40.0);
                # the catalogue generator as fractions (0.15). Show both as %.
                "weight": a.weight * 100 if 0 < a.weight <= 1 else a.weight,
                "contribution": a.contribution,
                "hurdle": a.hurdle,
                "early_assessment": a.early_assessment,
                "silo_ids": a.silo_ids,
                "n_results": results_per_assessment.get((a.subject_code, a.assessment_name), 0),
            }
            for a in dataset.assessments
            if subject_code is None or a.subject_code == subject_code
        ]

    silo_listings = (
        {"key": "all", "short": "every outcome", "title": "Every outcome",
         "blurb": "All SILOs in the loaded dataset, outcomes with the most issues first.",
         "predicate": lambda r: True},
        {"key": "flagged", "short": "flagged", "title": "Outcomes flagged by the clustering",
         "blurb": "SILOs the clustering model declined to place in a competency, with its reason.",
         "predicate": lambda r: r.flagged},
        {"key": "orphan", "short": "unlinked", "title": "Outcomes that link to no other subject",
         "blurb": "SILOs whose competency contains outcomes from this one subject only, so a student's work here is evidence about nothing else.",
         "predicate": lambda r: r.orphan},
        {"key": "unassessed", "short": "never assessed", "title": "Outcomes never assessed",
         "blurb": "SILOs no assessment in the subject's map evidences, so no student can have a mark against them.",
         "predicate": lambda r: r.n_assessments == 0},
        {"key": "vague", "short": "vaguely worded", "title": "Vaguely worded outcomes",
         "blurb": "SILOs containing a verb that cannot be assessed as written (understand, appreciate, be aware of).",
         "predicate": lambda r: bool(r.vague_terms)},
    )
    silo_listing_by_key = {d["key"]: d for d in silo_listings}
    issue_order = sorted(silo_rows, key=lambda r: (-len(r.issues), r.key))

    # --- summary charts above the long lists ------------------------------
    #
    # Each list page gets one or two charts drawn from exactly the rows the
    # table below it shows, so a point on the chart is a row in the table.

    def subject_chart_data() -> str:
        by_year: dict[int | None, list] = defaultdict(list)
        for s in subject_rows:
            by_year[s.year_level].append(s)
        years = []
        for year in sorted(by_year, key=lambda y: (y is None, y or 0)):
            group = [s for s in by_year[year] if s.mean_attainment is not None]
            weight = sum(s.n_students for s in group) or 1
            years.append(
                {
                    "year": year,
                    "n_subjects": len(by_year[year]),
                    "mean_attainment": round(sum(s.mean_attainment * s.n_students for s in group) / weight, 1) if group else None,
                    "gap_rate": round(sum((s.gap_rate or 0) * s.n_students for s in group) / weight, 1) if group else None,
                }
            )
        return json.dumps(
            {
                "years": years,
                "subjects": [
                    {"code": s.subject_code, "year": s.year_level, "mean_attainment": s.mean_attainment,
                     "gap_rate": s.gap_rate, "n_students": s.n_students, "health": s.health}
                    for s in subject_rows
                ],
            }
        )

    def silo_chart_data(rows: list) -> str:
        scored = [r for r in rows if r.mean_attainment is not None]
        bins = histogram([r.mean_attainment for r in scored], bin_width=_GAP_MARK_BIN)
        return json.dumps(
            {
                "hist": {"labels": [b.label for b in bins], "values": [b.count for b in bins]},
                "points": [
                    {"key": r.key, "subject": r.subject_code, "x": r.mean_attainment, "y": r.gap_rate or 0.0, "issues": len(r.issues)}
                    for r in scored
                ],
            }
        )

    subject_charts = subject_chart_data()

    def listing_counts() -> list[dict]:
        return [
            {"key": d["key"], "short": d["short"], "count": sum(1 for r in silo_rows if d["predicate"](r))}
            for d in silo_listings
        ]

    @app.get("/subjects")
    def subjects_page(request: Request):
        return templates.TemplateResponse(
            request, "subjects.html",
            {"subjects": subject_rows, "subject_charts": subject_charts,
             "review_warning": review_warning, "student_ids": student_ids},
        )

    @app.get("/subject/{code}")
    def subject_page(request: Request, code: str):
        subject = subject_by_code.get(code)
        if subject is None:
            raise HTTPException(status_code=404, detail=f"No subject {code!r} in this dataset")
        return templates.TemplateResponse(
            request, "subject.html",
            {
                "subject": subject,
                "silo_rows": sorted(silos_by_subject.get(code, []), key=lambda r: (-len(r.issues), r.key)),
                "assessments": assessment_rows(code),
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    @app.get("/silos/list/{listing_key}")
    def silo_list(request: Request, listing_key: str):
        listing = silo_listing_by_key.get(listing_key)
        if listing is None:
            known = ", ".join(d["key"] for d in silo_listings)
            raise HTTPException(status_code=404, detail=f"No outcome list {listing_key!r} -- known lists: {known}")
        listed = [r for r in issue_order if listing["predicate"](r)]
        return templates.TemplateResponse(
            request, "silo_list.html",
            {
                "listing": listing,
                "silo_rows": listed,
                "silo_charts": silo_chart_data(listed),
                "total": len(silo_rows),
                "others": [c for c in listing_counts() if c["key"] != listing_key],
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    # --- competency traceability ------------------------------------------
    #
    # Competency -> discipline -> subject -> SILO -> assessments. Built from
    # the clustering (membership), the dataset (SILO text, assessment map)
    # and silo_rows (flags, vague terms). Pure data; the template draws it.

    cluster_by_slug = {slugify(c.competency_label): c for c in clustering.clusters}
    assessments_by_silo: dict[tuple[str, str], list] = defaultdict(list)
    for a in dataset.assessments:
        for sid in a.silo_ids:
            assessments_by_silo[(a.subject_code, sid)].append(a)
    year_by_subject = {s.subject_code: s.year_level for s in subject_rows}
    disciplines_all = sorted({discipline_of(s.subject_code) for s in subject_rows})

    def trace_for(cluster) -> dict:
        by_disc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for m in cluster.members:
            row = silo_by_key.get(f"{m.subject_code}:{m.silo_local_id}")
            silo = dataset.silos.get(f"{m.subject_code}:{m.silo_local_id}")
            by_disc[discipline_of(m.subject_code)][m.subject_code].append(
                {
                    "id": m.silo_local_id,
                    "text": silo.text if silo else "(outcome text not in the workbook)",
                    "flagged": bool(row and row.flagged),
                    "flag_reason": row.flag_reason if row else "",
                    "vague_terms": list(row.vague_terms) if row else [],
                    "assessments": [
                        {"name": a.assessment_name, "weight": a.weight * 100 if 0 < a.weight <= 1 else a.weight}
                        for a in assessments_by_silo.get((m.subject_code, m.silo_local_id), [])
                    ],
                }
            )
        disciplines = [
            {
                "code": disc,
                "subjects": [
                    {"code": code, "year": year_by_subject.get(code), "silos": sorted(silos, key=lambda o: o["id"])}
                    for code, silos in sorted(by_disc[disc].items())
                ],
            }
            for disc in sorted(by_disc)
        ]
        # Layered layout: one row per subject on the middle column, one per
        # SILO on the right; the competency sits at the vertical middle.
        row_h, top = 28, 30
        subjects, silos = [], []
        y_silo = top
        y_subj_next = top
        for di, d in enumerate(disciplines):
            for s in d["subjects"]:
                first = y_silo
                for o in s["silos"]:
                    silos.append({"y": y_silo, "subject": s["code"], "id": o["id"], "text": o["text"], "flagged": o["flagged"],
                                  "flag_reason": o["flag_reason"], "vague": o["vague_terms"], "disc_index": di % 8})
                    y_silo += row_h
                last = y_silo - row_h
                sy = max(y_subj_next, (first + last) // 2)
                subjects.append({"code": s["code"], "year": s["year"], "n_silos": len(s["silos"]), "y": sy, "disc_index": di % 8})
                y_subj_next = sy + row_h
                for o in silos[-len(s["silos"]):]:
                    o["subject_y"] = sy
        height = max(y_silo, y_subj_next) + 10
        return {
            "label": cluster.competency_label,
            "slug": slugify(cluster.competency_label),
            "rationale": cluster.rationale,
            "disciplines": disciplines,
            "layout": {
                "width": 980, "height": max(height, 90), "x_comp": 10, "y_comp": max(height, 90) // 2,
                "x_subj": 250, "x_silo": 430, "silo_w": 540, "subjects": subjects, "silos": silos,
                "n_subjects": len(subjects), "n_silos": len(silos),
            },
        }

    @app.get("/competencies")
    def competencies_page(request: Request):
        rows = []
        for cluster in clustering.clusters:
            counts = gap_counts_by_label.get(cluster.competency_label, Counter())
            rows.append(
                {
                    "label": cluster.competency_label,
                    "slug": slugify(cluster.competency_label),
                    "has_progression": slugify(cluster.competency_label) in progression_by_slug,
                    "rationale": cluster.rationale,
                    "members": cluster.members,
                    "n_silos": len(cluster.members),
                    "n_subjects": len({m.subject_code for m in cluster.members}),
                    "n_rows": sum(counts.values()),
                    "counts": {c: counts[c] for c in _CLASSIFICATION_ORDER},
                }
            )
        rows.sort(key=lambda r: r["label"].lower())
        # Chart order: gap-heaviest first, so the eye lands on the problem.
        chart = []
        for r in sorted(rows, key=lambda r: -((r["counts"]["persistent gap"] + r["counts"]["isolated gap"]) / (r["n_rows"] or 1))):
            n = r["n_rows"] or 1
            chart.append(
                {
                    "label": r["label"], "slug": r["slug"], "n": r["n_rows"],
                    "share": {c: round(100 * r["counts"][c] / n, 1) for c in _CLASSIFICATION_ORDER},
                }
            )
        # Organisation map: competency x discipline, cell = SILOs. Shows at a
        # glance which disciplines feed each competency and which are shared.
        heat = []
        for r in rows:
            counts = Counter(discipline_of(m.subject_code) for m in r["members"])
            heat.append({"label": r["label"], "slug": r["slug"], "cells": [counts.get(d, 0) for d in disciplines_all], "total": len(r["members"])})
        heat.sort(key=lambda h: (-sum(1 for c in h["cells"] if c), h["label"].lower()))
        heat_max = max((c for h in heat for c in h["cells"]), default=1)
        return templates.TemplateResponse(
            request, "competencies.html",
            {"rows": rows, "competency_chart": json.dumps(chart), "total_gap_rows": len(gaps),
             "heat": heat, "heat_disciplines": disciplines_all, "heat_max": heat_max,
             "review_warning": review_warning, "student_ids": student_ids},
        )

    @app.get("/assessments")
    def assessments_page(request: Request):
        rows = assessment_rows()
        scored = [a for a in rows if a["mean_score"] is not None]
        bins = histogram([a["mean_score"] for a in scored], bin_width=_GAP_MARK_BIN)
        charts = {
            "hist": {"labels": [b.label for b in bins], "values": [b.count for b in bins]},
            "points": [
                {"subject": a["subject_code"], "name": a["assessment_name"], "x": a["weight"], "y": a["mean_score"],
                 "n": a["n_results"], "hurdle": a["hurdle"]}
                for a in scored
            ],
        }
        return templates.TemplateResponse(
            request, "assessments.html",
            {
                "rows": rows,
                "assessment_charts": json.dumps(charts),
                "total_results": len(dataset.results),
                "unmapped_results": unmapped_results,
                "review_warning": review_warning,
                "student_ids": student_ids,
            },
        )

    @app.get("/silos")
    def outcome_quality(request: Request):
        context = {
            "totals": {
                "subjects": len(subject_rows),
                "silos": len(silo_rows),
                "flagged": sum(1 for r in silo_rows if r.flagged),
                "orphan": sum(1 for r in silo_rows if r.orphan),
                "unassessed": sum(1 for r in silo_rows if r.n_assessments == 0),
                "vague": sum(1 for r in silo_rows if r.vague_terms),
            },
            "silo_rows": issue_order,
            "silo_charts": silo_chart_data(issue_order),
            "subjects": subject_rows,
            "subject_charts": subject_charts,
            "review_warning": review_warning,
            "student_ids": student_ids,
            "terms": terms,
            "terms_json": json.dumps(
                [
                    {"term": t.term, "kind": t.kind, "count": t.count, "n_subjects": t.n_subjects, "mean_attainment": t.mean_attainment}
                    for t in terms
                ]
            ),
            "progressions": progressions,
            "matrix": matrix,
            "links": {"level": chord_level, "n_subjects": len(links.subjects), "n_disciplines": len(disc_links.disciplines),
                      "max_subject_chord": _MAX_SUBJECT_CHORD},
            "chord_json": json.dumps(chord_payload),
            "explorer_json": json.dumps(explorer_payload),
        }
        return templates.TemplateResponse(request, "silos.html", context)

    @app.get("/competency/{slug}")
    def competency_detail(request: Request, slug: str):
        """Every competency has a page: the trace always, the progression
        chart only when two or more subjects teach it."""
        cluster = cluster_by_slug.get(slug)
        if cluster is None:
            raise HTTPException(status_code=404, detail=f"No competency {slug!r}")
        progression = progression_by_slug.get(slug)
        chart_json = json.dumps(
            {
                "labels": [p.subject_code for p in progression.points],
                "attainment": [p.mean_attainment for p in progression.points],
                "gap_rate": [p.gap_rate for p in progression.points],
                "flagged": [p.flagged for p in progression.points],
            }
        ) if progression else "null"
        return templates.TemplateResponse(
            request,
            "competency.html",
            {"progression": progression, "trace": trace_for(cluster), "silo_by_key": silo_by_key,
             "chart_json": chart_json, "review_warning": review_warning, "student_ids": student_ids},
        )

    return app
