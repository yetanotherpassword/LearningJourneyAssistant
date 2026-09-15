"""Builds an LjaDataset from a live Moodle Postgres database.

This is the production counterpart to excel_loader.py: same output type, same
downstream job, different source. Everything after loading -- silo_clustering,
gap_detection, the dashboard -- consumes LjaDataset and nothing else, so which
loader produced it is invisible to them. That is the whole point of the vertical
slice (IOLG-104): if the Moodle path drops in with no change to the model code,
the LjaDataset abstraction was right.

How the Moodle rows become an LjaDataset:

  * SQL Query 2 (sql/moodle_attainment_extraction.sql, prefix from config per
    IOLG-105) yields one row per (student, assessment, rubric criterion): the
    level awarded, its normalised percentage, and the marker's remark.
  * Moodle rubric criteria carry no SILO tag, so the IOLG-56 mapping CSV
    (subject_code, assessment_name, criterion_text -> silo_key, weight) is the
    bridge. Each Query 2 row is joined to it to attach a SILO and a weight.
  * Each joined row becomes one ResultRow whose single silo_ids entry is that
    criterion's SILO, score is the criterion percentage, and feedback is the
    (HTML-stripped) remark. Silo and Assessment records are built from the same
    join.

The design's lja_criterion_score table (see the SQL file's header) is NOT
materialised here: this in-memory LjaDataset is its equivalent for the slice.

Read-only by construction: it only ever runs Query 2, and the caller is expected
to connect as the least-privilege lja_reader role, never the Moodle application
user (see sql/README.md). This module never writes.
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .excel_loader import Assessment, LjaDataset, ResultRow, Silo, StudentSummary
from .sql import load_query_2

_HTML_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class CriterionSiloMapping:
    """One row of the criterion->SILO bridge CSV."""

    silo_key: str  # "CSE1IOI:SILO1"
    weight: float

    @property
    def subject_code(self) -> str:
        return self.silo_key.split(":", 1)[0]

    @property
    def silo_local_id(self) -> str:
        return self.silo_key.split(":", 1)[1]


def _strip_html(text: str) -> str:
    """Rubric remarks are stored as HTML (remarkformat = 1). Query 2's header
    says strip tags downstream rather than in SQL -- here is downstream.
    """
    return html.unescape(_HTML_TAG.sub("", text or "")).strip()


def load_criterion_silo_map(
    mapping_path: str | Path,
) -> dict[tuple[str, str, str], CriterionSiloMapping]:
    """(subject_code, assessment_name, criterion_text) -> mapping.

    The staff-editable bridge from a Moodle rubric criterion to a subject SILO;
    without it the Moodle rows cannot be placed on the SILO axis the rest of the
    pipeline reasons over.
    """
    mapping: dict[tuple[str, str, str], CriterionSiloMapping] = {}
    with Path(mapping_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["subject_code"].strip(),
                row["assessment_name"].strip(),
                row["criterion_text"].strip(),
            )
            mapping[key] = CriterionSiloMapping(
                silo_key=row["silo_key"].strip(),
                weight=float(row["weight"]),
            )
    return mapping


def _rows_from_cursor(cursor) -> list[dict[str, object]]:
    """Run Query 2 and return its rows as name-keyed dicts, so the loader reads
    columns by name and a test can supply a fake cursor with a plain
    (description, rows) pair.
    """
    cursor.execute(load_query_2())
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _band(average: float) -> str:
    # Same cut points as synth_generator, for a readable summary only -- these
    # summaries are informational (the CLI prints a student count); gap
    # detection reads dataset.results, not dataset.student_summaries.
    if average < 50:
        return "At risk"
    if average < 60:
        return "P range"
    if average < 70:
        return "C range"
    if average < 80:
        return "D range"
    return "HD/D range"


def _build_student_summaries(results: list[ResultRow]) -> list[StudentSummary]:
    by_student: dict[str, list[ResultRow]] = defaultdict(list)
    for row in results:
        by_student[row.student_id].append(row)

    summaries: list[StudentSummary] = []
    for student_id, rows in by_student.items():
        by_subject: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            by_subject[row.subject_code].append(row.score)
        subject_totals = {
            subject: round(sum(scores) / len(scores), 2) for subject, scores in by_subject.items()
        }
        average_total = round(sum(subject_totals.values()) / len(subject_totals), 4)
        summaries.append(
            StudentSummary(
                student_id=student_id,
                subject_totals=subject_totals,
                average_total=average_total,
                performance_band=_band(average_total),
            )
        )
    return summaries


def load_dataset_from_moodle(conn, mapping_path: str | Path) -> LjaDataset:
    """Build an LjaDataset from a Moodle database connection and the mapping CSV.

    conn is an open, read-only DB-API connection (open it from
    config.MOODLE_DB.connect_kwargs as the lja_reader role). This function only
    reads: it runs Query 2 and closes its cursor, nothing else.
    """
    mapping = load_criterion_silo_map(mapping_path)

    cursor = conn.cursor()
    try:
        rows = _rows_from_cursor(cursor)
    finally:
        cursor.close()

    silos: dict[str, Silo] = {}
    results: list[ResultRow] = []
    # Ordered, de-duplicated SILO list per assessment.
    assessment_silos: dict[tuple[str, str], list[str]] = defaultdict(list)
    unmapped: set[tuple[str, str, str]] = set()

    for row in rows:
        subject_code = str(row["subject_code"]).strip()
        assessment_name = str(row["assessment_name"]).strip()
        criterion = str(row["criterion"]).strip()

        entry = mapping.get((subject_code, assessment_name, criterion))
        if entry is None:
            unmapped.add((subject_code, assessment_name, criterion))
            continue

        silo_local_id = entry.silo_local_id
        if entry.silo_key not in silos:
            # No authoritative SILO statement exists for these fixture criteria,
            # so the criterion text stands in as the SILO text -- it is what the
            # clustering reasons over, and what a real SILO statement would say.
            silos[entry.silo_key] = Silo(
                subject_code=subject_code, silo_local_id=silo_local_id, text=criterion
            )
        if silo_local_id not in assessment_silos[(subject_code, assessment_name)]:
            assessment_silos[(subject_code, assessment_name)].append(silo_local_id)

        idnumber = str(row.get("student_id_number") or "").strip()
        student_id = idnumber or f"user{row['user_id']}"
        score = float(row["criterion_pct"]) if row["criterion_pct"] is not None else 0.0

        results.append(
            ResultRow(
                student_id=student_id,
                subject_code=subject_code,
                assessment_name=assessment_name,
                score=score,
                feedback_comment=_strip_html(str(row.get("marker_remark") or "")),
                weight=entry.weight,
                weighted_score=round(score * entry.weight, 4),
                silo_ids=(silo_local_id,),
            )
        )

    if unmapped:
        listed = "; ".join(f"{s} / {a} / {c}" for s, a, c in sorted(unmapped))
        raise ValueError(
            f"Query 2 returned {len(unmapped)} criteria with no row in the mapping "
            f"CSV ({mapping_path}). Add them (subject_code, assessment_name, "
            f"criterion_text -> silo_key, weight) before loading: {listed}"
        )

    assessments = [
        Assessment(
            subject_code=subject_code,
            assessment_name=assessment_name,
            weight=1.0,  # per-assessment weighting is not carried by the slice
            contribution="",
            early_assessment=False,
            hurdle=False,
            silo_ids=tuple(silo_ids),
        )
        for (subject_code, assessment_name), silo_ids in assessment_silos.items()
    ]

    return LjaDataset(
        silos=silos,
        assessments=assessments,
        results=results,
        student_summaries=_build_student_summaries(results),
    )
