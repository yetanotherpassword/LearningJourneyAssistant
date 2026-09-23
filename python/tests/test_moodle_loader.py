"""Unit tests for lja.data.moodle_loader (IOLG-104).

The loader is exercised against a fake DB-API cursor holding canned Query 2
rows -- the same column names Query 2 selects -- plus a temp mapping CSV, so
these run with no database present. One integration test at the end runs the
real Query 2 against a live Moodle DB, but only when one is reachable.
"""

from __future__ import annotations

import os

import pytest

from lja.data.moodle_loader import (
    _strip_html,
    load_criterion_silo_map,
    load_dataset_from_moodle,
)

# Column names in Query 2's SELECT order (sql/moodle_attainment_extraction.sql).
# The loader reads by name via cursor.description, so only the columns it
# actually uses need realistic values; the rest are present for fidelity.
_COLUMNS = [
    "subject_code", "subject_name", "assignment_id", "assessment_name",
    "user_id", "student_id_number", "rubric_name", "criterion_order",
    "criterion", "level_awarded", "level_score", "criterion_max_score",
    "criterion_pct", "marker_remark", "rubric_total_normalised",
    "gradebook_grade", "assessment_max_grade", "graded_at", "grader_user_id",
]


def _row(**overrides):
    """A full Query 2 row with sensible defaults, overridden per test."""
    base = {name: None for name in _COLUMNS}
    base.update(
        subject_code="CSE1IOI",
        assessment_name="Assignment 1",
        user_id=42,
        student_id_number="S12345",
        criterion="Problem decomposition and algorithm design",
        criterion_pct=75.0,
        marker_remark="<p>Solid work.</p>",
    )
    base.update(overrides)
    return base


class FakeCursor:
    """Minimal DB-API cursor: ignores the SQL, returns canned rows."""

    def __init__(self, rows):
        self._rows = rows
        self.description = [(name,) for name in _COLUMNS]
        self.executed = None

    def execute(self, sql, params=None):
        self.executed = sql

    def fetchall(self):
        return [tuple(row[name] for name in _COLUMNS) for row in self._rows]

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.cursor_obj = None

    def cursor(self):
        self.cursor_obj = FakeCursor(self._rows)
        return self.cursor_obj


@pytest.fixture
def mapping_csv(tmp_path):
    """The three-criterion CSE1IOI bridge, matching data-fixtures."""
    path = tmp_path / "map.csv"
    path.write_text(
        "subject_code,assessment_name,criterion_text,silo_key,weight\n"
        "CSE1IOI,Assignment 1,Problem decomposition and algorithm design,CSE1IOI:SILO1,1.0\n"
        "CSE1IOI,Assignment 1,Correct implementation and testing,CSE1IOI:SILO2,0.5\n"
        "CSE1IOI,Assignment 1,Code quality and documentation,CSE1IOI:SILO3,1.0\n",
        encoding="utf-8",
    )
    return path


def test_strip_html_removes_tags_and_unescapes() -> None:
    assert _strip_html("<p>Good &amp; clear.</p>") == "Good & clear."
    assert _strip_html("<ul><li>one</li><li>two</li></ul>") == "onetwo"
    assert _strip_html("") == ""
    assert _strip_html(None) == ""


def test_load_criterion_silo_map_keys_and_weight(mapping_csv) -> None:
    mapping = load_criterion_silo_map(mapping_csv)
    entry = mapping[("CSE1IOI", "Assignment 1", "Correct implementation and testing")]
    assert entry.silo_key == "CSE1IOI:SILO2"
    assert entry.subject_code == "CSE1IOI"
    assert entry.silo_local_id == "SILO2"
    assert entry.weight == 0.5


def test_builds_dataset_with_one_result_per_row(mapping_csv) -> None:
    rows = [
        _row(criterion="Problem decomposition and algorithm design", criterion_pct=80.0),
        _row(criterion="Correct implementation and testing", criterion_pct=60.0),
        _row(criterion="Code quality and documentation", criterion_pct=40.0),
    ]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)

    assert len(dataset.results) == 3
    assert {s for s in dataset.silos} == {"CSE1IOI:SILO1", "CSE1IOI:SILO2", "CSE1IOI:SILO3"}
    # SILO text stands in from the criterion wording (no separate SILO statement).
    assert dataset.silos["CSE1IOI:SILO1"].text == "Problem decomposition and algorithm design"

    by_silo = {r.silo_ids[0]: r for r in dataset.results}
    assert by_silo["SILO1"].score == 80.0
    assert by_silo["SILO2"].weight == 0.5
    assert by_silo["SILO2"].weighted_score == 30.0  # 60 * 0.5
    # Each result carries exactly one SILO.
    assert all(len(r.silo_ids) == 1 for r in dataset.results)


def test_one_assessment_gathers_all_three_silos(mapping_csv) -> None:
    rows = [
        _row(criterion="Problem decomposition and algorithm design"),
        _row(criterion="Correct implementation and testing"),
        _row(criterion="Code quality and documentation"),
    ]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)
    assert len(dataset.assessments) == 1
    assessment = dataset.assessments[0]
    assert assessment.assessment_name == "Assignment 1"
    assert set(assessment.silo_ids) == {"SILO1", "SILO2", "SILO3"}


def test_remark_html_is_stripped_into_feedback(mapping_csv) -> None:
    rows = [_row(marker_remark="<p>Great <b>decomposition</b>.</p>")]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)
    assert dataset.results[0].feedback_comment == "Great decomposition."


def test_idnumber_falls_back_to_user_id(mapping_csv) -> None:
    rows = [_row(student_id_number=None, user_id=99)]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)
    assert dataset.results[0].student_id == "user99"


def test_unmapped_criterion_raises_with_details(mapping_csv) -> None:
    rows = [_row(criterion="A criterion nobody mapped")]
    with pytest.raises(ValueError, match="no row in the mapping"):
        load_dataset_from_moodle(FakeConn(rows), mapping_csv)


def test_null_criterion_pct_becomes_zero(mapping_csv) -> None:
    rows = [_row(criterion_pct=None)]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)
    assert dataset.results[0].score == 0.0


def test_student_summary_built_per_student(mapping_csv) -> None:
    rows = [
        _row(student_id_number="S1", criterion="Problem decomposition and algorithm design", criterion_pct=90.0),
        _row(student_id_number="S1", criterion="Correct implementation and testing", criterion_pct=70.0),
        _row(student_id_number="S2", criterion="Code quality and documentation", criterion_pct=50.0),
    ]
    dataset = load_dataset_from_moodle(FakeConn(rows), mapping_csv)
    summaries = {s.student_id: s for s in dataset.student_summaries}
    assert set(summaries) == {"S1", "S2"}
    # S1 averages 90 and 70 -> subject total 80.
    assert summaries["S1"].subject_totals["CSE1IOI"] == 80.0


# ---------------------------------------------------------------------------
# Integration: only runs when a real Moodle DB is reachable.
# ---------------------------------------------------------------------------

def _moodle_conn_or_skip():
    """Connect using config.MOODLE_DB, or skip if unreachable / no driver."""
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")
    from lja import config

    if os.environ.get("LJA_RUN_MOODLE_INTEGRATION") != "1":
        pytest.skip("set LJA_RUN_MOODLE_INTEGRATION=1 to run against a live Moodle DB")
    try:
        return psycopg2.connect(connect_timeout=3, **config.MOODLE_DB.connect_kwargs)
    except psycopg2.Error as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Moodle DB not reachable: {exc}")


def test_integration_loads_seeded_subject() -> None:
    from pathlib import Path

    conn = _moodle_conn_or_skip()
    try:
        mapping = Path(__file__).resolve().parents[2] / "data-fixtures" / "criterion_silo_map_CSE1IOI.csv"
        dataset = load_dataset_from_moodle(conn, mapping)
    finally:
        conn.close()

    # The IOLG-56 fixture seeds 5 students x 3 criteria = 15 rubric fills.
    assert len(dataset.results) == 15
    assert dataset.silos, "expected at least one SILO from the seeded subject"
