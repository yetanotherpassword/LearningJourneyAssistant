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
from lja.model.gap_detection import CompetencyGap
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
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=90.0,
            subjects_evidencing=2, n_observations=4, classification="proficient",
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
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Persistent Thing", attainment_pct=30.0,
            subjects_evidencing=2, n_observations=3, classification="persistent gap",
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
        ),
    ]
    body = _client(dataset, gaps).get("/student/STU0001").text
    assert "Flag for intervention" not in body
    assert "No other subject in this dataset" not in body


# --- cohort drill-down, statistics and column sorting (S3-7) ---


def _two_students_one_with_a_persistent_gap() -> tuple[LjaDataset, list[CompetencyGap]]:
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
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=90.0,
            subjects_evidencing=2, n_observations=4, classification="proficient",
        ),
    ]
    return dataset, gaps


def test_index_stat_tiles_link_to_their_cohort_page() -> None:
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/").text
    assert 'href="/cohort/all"' in body
    assert 'href="/cohort/persistent-gap"' in body


def test_cohort_page_contains_only_its_members() -> None:
    """STU0002 has the persistent gap; STU0001 is proficient. The cohort page
    must not merely highlight the difference -- STU0001 should not be on it.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    response = _client(dataset, gaps).get("/cohort/persistent-gap")

    assert response.status_code == 200
    assert 'href="/student/STU0002"' in response.text
    assert 'href="/student/STU0001"' not in response.text


def test_cohort_page_states_what_put_students_in_it() -> None:
    """Tender requirement 5: a displayed figure is traceable to a source
    record. A filtered count with no statement of the filter is not.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/cohort/persistent-gap").text
    assert "two or more subjects" in body


def test_index_tile_count_and_cohort_page_row_count_agree() -> None:
    """The tile is a promise about what the link leads to. These are computed
    from one shared view model precisely so they cannot disagree, and this is
    the test that would catch it if that ever stopped being true.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    client = _client(dataset, gaps)

    index_body = client.get("/").text
    match = re.search(r'<div class="num">(\d+)</div>\s*<div class="label">with a persistent gap', index_body)
    assert match is not None

    cohort_body = client.get("/cohort/persistent-gap").text
    assert int(match.group(1)) == cohort_body.count('href="/student/')


def test_unknown_cohort_is_404_and_names_the_ones_that_exist() -> None:
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    response = _client(dataset, gaps).get("/cohort/not-a-cohort")
    assert response.status_code == 404
    assert "persistent-gap" in response.json()["detail"]


def test_at_risk_cohort_is_not_registered_yet() -> None:
    """Deliberately asserting an ABSENCE, which is unusual enough to justify.

    The team asked for an "At Risk" tile. Sprint 3 runbook Sec 9 lists the
    at-risk threshold as a stop-and-ask -- Scott confirmed there is no
    institutional number to match, so the definition is the team's to choose
    and defend, and it is due at WP2 planning. This test fails the moment
    someone adds the cohort, which is the intended prompt to delete the test
    and record the agreed definition rather than to work around it.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    assert _client(dataset, gaps).get("/cohort/at-risk").status_code == 404


def test_index_renders_descriptive_statistics() -> None:
    """Averages 70 and 40.

    mean     = (70+40)/2 = 55
    median   = (40+70)/2 = 55
    variance = population: deviations -15 and +15 -> 225+225 = 450, /2 = 225
    stdev    = sqrt(225) = 15
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/").text

    assert "55.00%" in body       # mean and median
    assert "225.00" in body       # variance
    assert "15.00" in body        # standard deviation
    assert "variance" in body


def test_statistics_are_computed_over_the_cohort_not_the_whole_dataset() -> None:
    """The persistent-gap cohort holds only STU0002 (average 40), so its mean
    is 40, not the 55 the full dataset averages. A statistics panel that
    ignored the filter would be the easiest possible bug to ship here.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/cohort/persistent-gap").text

    assert "40.00%" in body
    assert "55.00%" not in body


def test_table_is_marked_sortable_with_machine_readable_values() -> None:
    """Sorting is client-side, so the server's contract is the markup: a
    sortable table, typed headers, and a raw value per cell. Without
    data-sort-value the client would sort on "70.0%" and order 100 before 20.
    """
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/").text

    assert 'class="sortable"' in body
    assert 'data-sort-type="number"' in body
    assert 'data-sort-type="text"' in body
    assert 'data-sort-value="70.0"' in body      # raw, not the rendered "70.0%"
    assert 'data-sort-value="Credit"' in body


def test_empty_dataset_renders_an_empty_state_not_a_broken_page() -> None:
    response = _client(_dataset([]), []).get("/")
    assert response.status_code == 200
    assert "No students in this cohort." in response.text
