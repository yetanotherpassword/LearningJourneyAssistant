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
from ..model.gap_detection import CompetencyGap
from ..model.gap_evidence import describe_trend, future_subjects_sharing_competency, subject_breakdown
from ..model.silo_clustering import SiloClusteringResult
from .stats import histogram, summarise

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

# Worst first -- a reviewer scanning a student's gap table should see the
# thing that actually needs attention before "proficient" rows.
_CLASSIFICATION_ORDER = ["persistent gap", "isolated gap", "developing", "proficient"]

# Only these classifications get a "future subjects to flag" list -- a
# proficient or developing competency isn't a gap, so there's nothing to
# warn a student about yet.
_AT_RISK_CLASSIFICATIONS = {"persistent gap", "isolated gap"}


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
)

_COHORTS_BY_KEY = {cohort.key: cohort for cohort in _COHORTS}


def create_app(dataset: LjaDataset, gaps: list[CompetencyGap], clustering: SiloClusteringResult) -> FastAPI:
    app = FastAPI(title="LJA Dashboard")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    gaps_by_student: dict[str, list[CompetencyGap]] = defaultdict(list)
    for gap in gaps:
        gaps_by_student[gap.student_id].append(gap)
    students_by_id = {s.student_id: s for s in dataset.student_summaries}

    def members(cohort: _Cohort) -> list[StudentSummary]:
        return [
            summary
            for summary in sorted(dataset.student_summaries, key=lambda s: s.student_id)
            if cohort.predicate(summary, gaps_by_student.get(summary.student_id, []))
        ]

    def row_for(summary: StudentSummary) -> dict:
        student_gaps = gaps_by_student.get(summary.student_id, [])
        counts = Counter(g.classification for g in student_gaps)
        return {
            "student_id": summary.student_id,
            "average_total": summary.average_total,
            "performance_band": summary.performance_band,
            "persistent_gap_count": counts["persistent gap"],
            "isolated_gap_count": counts["isolated gap"],
        }

    def view_model(cohort: _Cohort) -> dict:
        """Rows + descriptive statistics + both charts' data, for one cohort.

        Shared by the index and every cohort page so the two can never drift
        into computing the same figure two different ways.
        """
        summaries = members(cohort)
        rows = [row_for(summary) for summary in summaries]
        averages = [summary.average_total for summary in summaries]

        cohort_gaps = [g for summary in summaries for g in gaps_by_student.get(summary.student_id, [])]
        classification_counts = Counter(g.classification for g in cohort_gaps)
        bins = histogram(averages)

        return {
            "cohort": cohort,
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
        context["tiles"] = [
            {
                "key": cohort.key,
                "count": len(members(cohort)),
                "label": cohort.tile_label,
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

    @app.get("/student/{student_id}")
    def student_detail(request: Request, student_id: str):
        summary = students_by_id.get(student_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"No student {student_id!r} in this dataset")

        student_gaps = sorted(
            gaps_by_student.get(student_id, []),
            key=lambda g: _CLASSIFICATION_ORDER.index(g.classification),
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

        return templates.TemplateResponse(
            request,
            "student.html",
            {"summary": summary, "gap_details": gap_details, "chart_data": chart_data},
        )

    return app
