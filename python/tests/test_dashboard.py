"""Tests for lja.dashboard -- exercised via FastAPI's TestClient against
small in-memory fixtures. No real Excel file, no clustering cache, no LLM;
create_app() takes data directly for exactly this reason -- see
lja/dashboard/app.py's module docstring.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lja.dashboard.app import create_app
from lja.data.excel_loader import LjaDataset, ResultRow, StudentSummary
from lja.model.gap_detection import BASIS_CEILING, BASIS_FLOOR, BASIS_RELATIVE, CompetencyGap
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef


def _dataset(summaries: list[StudentSummary] | None = None, results: list[ResultRow] | None = None) -> LjaDataset:
    return LjaDataset(silos={}, assessments=[], results=results or [], student_summaries=summaries or [])


def _clustering(*groups: tuple[str, list[tuple[str, str]]]) -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label=label,
                rationale="test",
                members=[SiloRef(subject_code=s, silo_local_id=i) for s, i in members],
            )
            for label, members in groups
        ]
    )


def _client(dataset: LjaDataset, gaps: list[CompetencyGap], clustering: SiloClusteringResult | None = None) -> TestClient:
    return TestClient(create_app(dataset, gaps, clustering or SiloClusteringResult(clusters=[])))


def test_index_lists_every_student() -> None:
    dataset = _dataset(
        [
            StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 70.0}, average_total=70.0, performance_band="Credit"),
            StudentSummary(student_id="STU0002", subject_totals={"CSE1OOF": 40.0}, average_total=40.0, performance_band="Fail"),
        ]
    )
    response = _client(dataset, []).get("/")
    assert response.status_code == 200
    assert "STU0001" in response.text
    assert "STU0002" in response.text


def test_index_counts_only_students_with_a_persistent_gap() -> None:
    dataset = _dataset(
        [
            StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit"),
            StudentSummary(student_id="STU0002", subject_totals={}, average_total=40.0, performance_band="Fail"),
        ]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0002", competency_label="Data Structures", attainment_pct=35.0,
            subjects_evidencing=2, n_observations=4, classification="persistent gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=90.0,
            subjects_evidencing=2, n_observations=4, classification="proficient",
            classification_basis=BASIS_CEILING, relative_position=None,
        ),
    ]
    response = _client(dataset, gaps).get("/")
    match = re.search(r'<div class="num">(\d+)</div>\s*<div class="label">with a persistent gap', response.text)
    assert match is not None
    assert match.group(1) == "1"


def test_index_marks_at_risk_students_link_with_the_at_risk_class() -> None:
    dataset = _dataset(
        [
            StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit"),
            StudentSummary(student_id="STU0002", subject_totals={}, average_total=40.0, performance_band="Fail"),
        ]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0002", competency_label="Data Structures", attainment_pct=35.0,
            subjects_evidencing=2, n_observations=4, classification="persistent gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps).get("/").text
    assert 'href="/student/STU0002" class="at-risk"' in body.replace("\n", "").replace("  ", "")
    assert 'href="/student/STU0001" class=""' in body.replace("\n", "").replace("  ", "")


def test_student_detail_shows_its_gaps() -> None:
    dataset = _dataset(
        [StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 70.0}, average_total=70.0, performance_band="Credit")]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=42.0,
            subjects_evidencing=2, n_observations=3, classification="persistent gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    response = _client(dataset, gaps).get("/student/STU0001")
    assert response.status_code == 200
    assert "Data Structures" in response.text
    assert "persistent gap" in response.text


def test_student_detail_404_for_unknown_student() -> None:
    dataset = _dataset(
        [StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit")]
    )
    response = _client(dataset, []).get("/student/STU9999")
    assert response.status_code == 404


def test_worst_classification_renders_first() -> None:
    """Guards the sort in app.py: a reviewer should see the persistent gap
    before the proficient row, not in whatever order compute_gaps() happened
    to emit them.
    """
    dataset = _dataset(
        [StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit")]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Proficient Thing", attainment_pct=95.0,
            subjects_evidencing=2, n_observations=3, classification="proficient",
            classification_basis=BASIS_CEILING, relative_position=None,
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Persistent Thing", attainment_pct=30.0,
            subjects_evidencing=2, n_observations=3, classification="persistent gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps).get("/student/STU0001").text
    assert body.index("Persistent Thing") < body.index("Proficient Thing")


def test_student_detail_shows_per_subject_evidence_and_trend() -> None:
    clustering = _clustering(("Data Structures", [("CSE1OOF", "SILO2"), ("CSE2ALG", "SILO2")]))
    dataset = _dataset(
        summaries=[
            StudentSummary(
                student_id="STU0001",
                subject_totals={"CSE1OOF": 70.0, "CSE2ALG": 40.0},
                average_total=55.0,
                performance_band="Credit",
            )
        ],
        results=[
            ResultRow("STU0001", "CSE1OOF", "Test", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO2",)),
            ResultRow("STU0001", "CSE2ALG", "Test", score=30.0, feedback_comment="", weight=1.0, weighted_score=30.0, silo_ids=("SILO2",)),
        ],
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=50.0,
            subjects_evidencing=2, n_observations=2, classification="persistent gap",
            classification_basis=BASIS_RELATIVE, relative_position=-1.5,
        ),
    ]
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    assert "CSE1OOF" in body and "CSE2ALG" in body
    assert "declining" in body


def test_student_detail_flags_future_subjects_for_an_at_risk_gap() -> None:
    clustering = _clustering(("Data Structures", [("CSE1OOF", "SILO2"), ("CSE2ALG", "SILO2")]))
    dataset = _dataset(
        summaries=[
            StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 40.0}, average_total=40.0, performance_band="Fail")
        ]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=40.0,
            subjects_evidencing=1, n_observations=1, classification="isolated gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    assert "Flag for intervention" in body
    assert "CSE2ALG" in body


def test_student_detail_shows_honest_empty_state_when_no_future_subjects() -> None:
    clustering = _clustering(("Data Structures", [("CSE1OOF", "SILO2")]))
    dataset = _dataset(
        summaries=[
            StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 40.0}, average_total=40.0, performance_band="Fail")
        ]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=40.0,
            subjects_evidencing=1, n_observations=1, classification="isolated gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    assert "No other subject in this dataset" in body


def test_student_detail_never_flags_future_subjects_for_a_non_gap() -> None:
    dataset = _dataset(
        [StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 90.0}, average_total=90.0, performance_band="High Distinction")]
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=90.0,
            subjects_evidencing=1, n_observations=1, classification="proficient",
            classification_basis=BASIS_CEILING, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps).get("/student/STU0001").text
    assert "Flag for intervention" not in body
    assert "No other subject in this dataset" not in body
