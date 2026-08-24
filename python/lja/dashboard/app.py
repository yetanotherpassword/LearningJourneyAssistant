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
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..data.excel_loader import LjaDataset
from ..model.gap_detection import CompetencyGap
from ..model.gap_evidence import describe_trend, future_subjects_sharing_competency, subject_breakdown
from ..model.silo_clustering import SiloClusteringResult

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

# Worst first -- a reviewer scanning a student's gap table should see the
# thing that actually needs attention before "proficient" rows.
_CLASSIFICATION_ORDER = ["persistent gap", "isolated gap", "developing", "proficient"]

# Only these classifications get a "future subjects to flag" list -- a
# proficient or developing competency isn't a gap, so there's nothing to
# warn a student about yet.
_AT_RISK_CLASSIFICATIONS = {"persistent gap", "isolated gap"}


def create_app(dataset: LjaDataset, gaps: list[CompetencyGap], clustering: SiloClusteringResult) -> FastAPI:
    app = FastAPI(title="LJA Dashboard")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    gaps_by_student: dict[str, list[CompetencyGap]] = defaultdict(list)
    for gap in gaps:
        gaps_by_student[gap.student_id].append(gap)
    students_by_id = {s.student_id: s for s in dataset.student_summaries}

    @app.get("/")
    def index(request: Request):
        rows = [
            {
                "student_id": summary.student_id,
                "average_total": summary.average_total,
                "performance_band": summary.performance_band,
                "persistent_gap_count": sum(
                    1 for g in gaps_by_student.get(summary.student_id, []) if g.classification == "persistent gap"
                ),
            }
            for summary in sorted(dataset.student_summaries, key=lambda s: s.student_id)
        ]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "rows": rows,
                "student_count": len(rows),
                "students_with_persistent_gaps": sum(1 for r in rows if r["persistent_gap_count"] > 0),
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
