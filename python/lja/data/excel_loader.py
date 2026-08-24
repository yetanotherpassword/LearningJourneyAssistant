"""Loads the project owner's CSE_results_*.xlsx workbook (three sheets:
Assessment Map, Results, Student Summary) into typed, in-memory structures.

This is the Excel-fed equivalent of the SQL bundle's extraction queries --
same downstream job (get scored SILO evidence per student), different
upstream source. Scott handed this workbook over already extracted and
structured, which is why this path exists ahead of the Moodle-DB path
sql/moodle_attainment_extraction.sql was written for.

One fact that shapes everything downstream: SILO numbering is LOCAL to each
subject. "SILO1" in CSE1OOF and "SILO1" in CSE2ALG describe unrelated
things -- only (subject_code, silo_local_id) together are a stable key, and
only the SILO *text* carries meaning across subjects. See silo_clustering.py
for where that gets resolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_SILO_ENTRY = re.compile(r"(SILO\d+):\s*([^;]+?)(?=;\s*SILO\d+:|$)")


@dataclass(frozen=True)
class Silo:
    subject_code: str
    silo_local_id: str  # e.g. "SILO1" -- unique only combined with subject_code
    text: str

    @property
    def key(self) -> str:
        return f"{self.subject_code}:{self.silo_local_id}"


@dataclass(frozen=True)
class Assessment:
    subject_code: str
    assessment_name: str
    weight: float
    contribution: str
    early_assessment: bool
    hurdle: bool
    silo_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResultRow:
    student_id: str
    subject_code: str
    assessment_name: str
    score: float
    feedback_comment: str
    weight: float
    weighted_score: float
    silo_ids: tuple[str, ...]


@dataclass(frozen=True)
class StudentSummary:
    student_id: str
    subject_totals: dict[str, float]
    average_total: float
    performance_band: str


@dataclass(frozen=True)
class LjaDataset:
    silos: dict[str, Silo]  # keyed by "SUBJECT:SILOn"
    assessments: list[Assessment]
    results: list[ResultRow]
    student_summaries: list[StudentSummary]


def _parse_silo_list(raw: str) -> list[tuple[str, str]]:
    """'SILO1: text one; SILO2: text two' -> [("SILO1", "text one"), ...].

    Verified against every row of the real Assessment Map sheet -- see
    python/tests/test_excel_loader.py. Silo text must not itself contain a
    semicolon or this splits early; none of the supplied SILOs do.
    """
    return [(m.group(1), m.group(2).strip()) for m in _SILO_ENTRY.finditer(str(raw))]


def _split_assessment_type(assessment_type: str) -> tuple[str, str]:
    """'CSE1OOF - Test' -> ('CSE1OOF', 'Test'). Assessment names can
    themselves contain ' - ' (e.g. 'Assignment: Final written Project
    Report' does not, but be safe) so only the FIRST ' - ' is the split
    point between subject code and name.
    """
    subject_code, _, name = str(assessment_type).partition(" - ")
    return subject_code.strip(), name.strip()


def load_dataset(path: str) -> LjaDataset:
    assessment_map = pd.read_excel(path, sheet_name="Assessment Map")
    results_sheet = pd.read_excel(path, sheet_name="Results")
    student_summary_sheet = pd.read_excel(path, sheet_name="Student Summary")

    silos: dict[str, Silo] = {}
    assessments: list[Assessment] = []
    for _, row in assessment_map.iterrows():
        subject_code = str(row["Subject Code"]).strip()
        _, assessment_name = _split_assessment_type(str(row["Assessment Type"]))

        silo_ids: list[str] = []
        for silo_id, text in _parse_silo_list(row["SILO Theme Summary"]):
            key = f"{subject_code}:{silo_id}"
            if key not in silos:
                silos[key] = Silo(subject_code=subject_code, silo_local_id=silo_id, text=text)
            silo_ids.append(silo_id)

        assessments.append(
            Assessment(
                subject_code=subject_code,
                assessment_name=assessment_name,
                weight=float(row["Weight"]),
                contribution=str(row["Contribution"]).strip(),
                early_assessment=str(row["Early Assessment"]).strip().lower() == "yes",
                hurdle=str(row["Hurdle"]).strip().lower() == "yes",
                silo_ids=tuple(silo_ids),
            )
        )

    results: list[ResultRow] = []
    for _, row in results_sheet.iterrows():
        subject_code, assessment_name = _split_assessment_type(str(row["Assessment Type"]))
        silo_ids = tuple(silo_id for silo_id, _ in _parse_silo_list(row["SILO's"]))
        results.append(
            ResultRow(
                student_id=str(row["Student ID"]).strip(),
                subject_code=subject_code,
                assessment_name=assessment_name,
                score=float(row["Score (1-100)"]),
                feedback_comment=str(row["Feedback Comment"]).strip(),
                weight=float(row["Weight"]),
                weighted_score=float(row["Weighted Score"]),
                silo_ids=silo_ids,
            )
        )

    # "Average Total" also ends with " Total" -- exclude it explicitly, it's
    # not a subject and is already carried separately as average_total.
    subject_total_columns = [
        c
        for c in student_summary_sheet.columns
        if str(c).endswith(" Total") and c != "Average Total"
    ]
    student_summaries: list[StudentSummary] = []
    for _, row in student_summary_sheet.iterrows():
        totals = {
            str(col)[: -len(" Total")]: float(row[col]) for col in subject_total_columns
        }
        student_summaries.append(
            StudentSummary(
                student_id=str(row["Student ID"]).strip(),
                subject_totals=totals,
                average_total=float(row["Average Total"]),
                performance_band=str(row["Performance Band"]).strip(),
            )
        )

    return LjaDataset(
        silos=silos,
        assessments=assessments,
        results=results,
        student_summaries=student_summaries,
    )
