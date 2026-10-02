"""Tests for lja.dashboard -- exercised via FastAPI's TestClient against
small in-memory fixtures. No real Excel file, no clustering cache, no LLM;
create_app() takes data directly for exactly this reason -- see
lja/dashboard/app.py's module docstring.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lja.dashboard.app import create_app
from lja.data.excel_loader import LjaDataset, ResultRow, Silo, StudentSummary
from lja.model.gap_detection import BASIS_CEILING, BASIS_FLOOR, BASIS_RELATIVE, CompetencyGap
from lja.model.silo_clustering import CompetencyCluster, FlaggedSilo, SiloClusteringResult, SiloRef


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
    # Scoped to the gap cards: the Strengths section above them (IOLG-112)
    # lists the proficient row first by design.
    gap_cards = body.split("<h2>Competency gaps</h2>")[1]
    assert gap_cards.index("Persistent Thing") < gap_cards.index("Proficient Thing")


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


def _progress_section(body: str) -> str:
    return body.split("<h2>Progress across subjects</h2>")[1].split("<h2>Competency gaps</h2>")[0]


def test_student_page_shows_progress_across_subjects_in_year_order() -> None:
    clustering = _clustering(("Data Structures", [("CSE1OOF", "SILO2"), ("CSE2ALG", "SILO2")]))
    dataset = _dataset(
        summaries=[StudentSummary("STU0001", {"CSE1OOF": 40.0, "CSE2ALG": 70.0}, 55.0, "Credit")],
        results=[
            # Listed second-year first to prove the columns follow year level, not row order.
            ResultRow("STU0001", "CSE2ALG", "Test", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO2",)),
            ResultRow("STU0001", "CSE1OOF", "Test", score=40.0, feedback_comment="", weight=1.0, weighted_score=40.0, silo_ids=("SILO2",)),
        ],
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=55.0,
            subjects_evidencing=2, n_observations=2, classification="developing",
            classification_basis=BASIS_RELATIVE, relative_position=-0.4,
        ),
    ]
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    progress = _progress_section(body)
    assert progress.index('<th data-sort-type="number">CSE1OOF</th>') < progress.index('<th data-sort-type="number">CSE2ALG</th>')
    assert "40.0%" in progress and "70.0%" in progress
    assert "improving" in progress
    # The chart gets the same rows as JSON, in the same order.
    assert '"labels": ["CSE1OOF", "CSE2ALG"]' in body
    assert '"values": [40.0, 70.0]' in body


def test_student_page_progress_marks_single_subject_competency_as_insufficient() -> None:
    clustering = _clustering(("Testing", [("CSE1OOF", "SILO1")]))
    dataset = _dataset(
        summaries=[StudentSummary("STU0001", {"CSE1OOF": 40.0}, 40.0, "Fail")],
        results=[
            ResultRow("STU0001", "CSE1OOF", "Test", score=40.0, feedback_comment="", weight=1.0, weighted_score=40.0, silo_ids=("SILO1",)),
        ],
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Testing", attainment_pct=40.0,
            subjects_evidencing=1, n_observations=1, classification="isolated gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
    ]
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    progress = _progress_section(body)
    assert '<th data-sort-type="number">CSE1OOF</th>' in progress
    assert "insufficient evidence" in progress
    # One point is not a progression: nothing is sent to the chart.
    assert '"rows": []' in body


def test_student_page_progress_empty_state_without_evidence() -> None:
    body = _client(_dataset([StudentSummary("STU0001", {}, 0.0, "Fail")]), []).get("/student/STU0001").text
    assert "No subject evidence for this student." in _progress_section(body)


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
            classification_basis=BASIS_FLOOR, relative_position=None,
        ),
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=90.0,
            subjects_evidencing=2, n_observations=4, classification="proficient",
            classification_basis=BASIS_CEILING, relative_position=None,
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
    # Count the full table only: the priority-group previews above it
    # repeat the most severe rows on purpose.
    full_table = cohort_body[cohort_body.index('<h2 id="everyone">'):]
    assert int(match.group(1)) == full_table.count('href="/student/')


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


# --- unreviewed-AI warning banner (IOLG-116) ---


def test_dashboard_shows_pending_ai_review_warning() -> None:
    app = create_app(
        _dataset(),
        [],
        SiloClusteringResult(clusters=[]),
        review_warning="2 AI-generated SILO cluster(s) are still awaiting staff review.",
    )

    body = TestClient(app).get("/").text

    assert "AI review warning:" in body
    assert "still awaiting staff review" in body
    assert 'href="/clusters"' in body.split("AI review warning:")[0][-200:], (
        "the banner itself must link to the clusters page, where each cluster's review state is shown"
    )


def test_dashboard_shows_rejected_ai_review_warning() -> None:
    app = create_app(
        _dataset(),
        [],
        SiloClusteringResult(clusters=[]),
        review_warning="1 AI-generated SILO cluster(s) have been rejected by staff.",
    )

    body = TestClient(app).get("/").text

    assert "AI review warning:" in body
    assert "have been rejected by staff" in body
    assert "ai-review-warning-link" in body


def test_dashboard_hides_ai_review_warning_when_confirmed() -> None:
    app = create_app(
        _dataset(),
        [],
        SiloClusteringResult(clusters=[]),
        review_warning=None,
    )

    body = TestClient(app).get("/").text

    assert "AI review warning:" not in body
    assert "ai-review-warning-link" not in body


def _clusters_client(review_states: dict[str, str] | None = None) -> TestClient:
    silos = {
        "CSE1OOF:SILO1": Silo(subject_code="CSE1OOF", silo_local_id="SILO1", text="design object-oriented programs"),
        "CSE2ALG:SILO1": Silo(subject_code="CSE2ALG", silo_local_id="SILO1", text="overall objectives of algorithms"),
        "CSE2ALG:SILO2": Silo(subject_code="CSE2ALG", silo_local_id="SILO2", text="implement sorting algorithms"),
        "CSE3CAP:SILO9": Silo(subject_code="CSE3CAP", silo_local_id="SILO9", text="an outcome nobody clustered"),
    }
    dataset = LjaDataset(silos=silos, assessments=[], results=[], student_summaries=[])
    clustering = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Algorithms",
                rationale="both subjects cover algorithms",
                members=[SiloRef(subject_code="CSE2ALG", silo_local_id="SILO1"),
                         SiloRef(subject_code="CSE2ALG", silo_local_id="SILO2")],
            ),
            CompetencyCluster(
                competency_label="OO Design",
                rationale="only CSE1OOF",
                members=[SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1")],
            ),
        ],
        flagged_silos=[FlaggedSilo(subject_code="CSE2ALG", silo_local_id="SILO1", reason="vague, no specific skill")],
    )
    gaps = [
        CompetencyGap(student_id=sid, competency_label="Algorithms", attainment_pct=pct, subjects_evidencing=1,
                      n_observations=2, classification=cls, classification_basis=BASIS_FLOOR, relative_position=None)
        for sid, pct, cls in [("STU0001", 30.0, "isolated gap"), ("STU0002", 70.0, "developing")]
    ]
    return TestClient(create_app(dataset, gaps, clustering, review_states=review_states))


def test_clusters_page_groups_silo_wording_under_competency_and_subject() -> None:
    body = _clusters_client().get("/clusters").text
    algorithms = body.split('id="competency-1"')[1].split('id="competency-2"')[0]
    assert "CSE2ALG" in algorithms and "implement sorting algorithms" in algorithms
    assert "both subjects cover algorithms" in algorithms
    assert "design object-oriented programs" not in algorithms


def test_clusters_page_lists_flagged_silos_with_their_reason() -> None:
    body = _clusters_client().get("/clusters").text
    flagged = body.split("<h2>Flagged SILOs</h2>")[1].split("<h2>SILO definitions</h2>")[0]
    assert "CSE2ALG:SILO1" in flagged and "vague, no specific skill" in flagged


def test_clusters_page_gap_rate_is_share_of_measured_students_with_a_gap() -> None:
    body = _clusters_client().get("/clusters").text
    assert "1 of 2 students measured on this competency have a gap in it" in body
    assert "50% gap rate" in body


def test_clusters_page_reports_silos_in_no_cluster() -> None:
    body = _clusters_client().get("/clusters").text
    assert "1 SILO in no cluster" in body and "CSE3CAP:SILO9" in body


def test_clusters_page_shows_review_state_only_when_known() -> None:
    assert "review-pending" not in _clusters_client().get("/clusters").text
    body = _clusters_client(review_states={}).get("/clusters").text
    assert body.count('class="badge review-pending"') == 2
    assert "0 / 2" in body


def test_header_links_to_the_clusters_page() -> None:
    assert 'href="/clusters"' in _client(_dataset(), []).get("/").text


def _strength(student_id: str, label: str, attainment: float, position: float | None) -> CompetencyGap:
    return CompetencyGap(
        student_id=student_id,
        competency_label=label,
        attainment_pct=attainment,
        subjects_evidencing=1,
        n_observations=2,
        classification="proficient",
        classification_basis=BASIS_RELATIVE if position is not None else BASIS_CEILING,
        relative_position=position,
    )


def _summary(student_id: str) -> StudentSummary:
    return StudentSummary(student_id=student_id, subject_totals={"CSE1OOF": 70.0}, average_total=70.0, performance_band="Credit")


def _strengths_section(body: str) -> str:
    return body.split("<h2>Strengths</h2>")[1].split("<h2>Progress across subjects</h2>")[0]


def test_student_page_lists_proficient_competencies_under_strengths() -> None:
    gaps = [
        _strength("STU0001", "Testing", 72.0, 1.5),
        _strength("STU0001", "Data Structures", 80.0, None),
        CompetencyGap(
            student_id="STU0001",
            competency_label="Algorithms",
            attainment_pct=42.0,
            subjects_evidencing=1,
            n_observations=2,
            classification="isolated gap",
            classification_basis=BASIS_FLOOR,
            relative_position=None,
        ),
    ]
    strengths = _strengths_section(_client(_dataset([_summary("STU0001")]), gaps).get("/student/STU0001").text)
    assert "Testing" in strengths and "Data Structures" in strengths
    assert "Algorithms" not in strengths
    # Every strength states how it was reached, as the gap cards do.
    assert BASIS_RELATIVE in strengths and BASIS_CEILING in strengths
    assert '+1.50 <a class="term" href="/glossary#mad">MAD</a> above' in strengths


def test_strengths_are_ordered_strongest_relative_position_first() -> None:
    gaps = [
        _strength("STU0001", "Testing", 90.0, 1.2),
        _strength("STU0001", "Networking", 75.0, 2.4),
    ]
    strengths = _strengths_section(_client(_dataset([_summary("STU0001")]), gaps).get("/student/STU0001").text)
    assert strengths.index("Networking") < strengths.index("Testing")


def test_student_page_shows_empty_state_when_nothing_is_proficient() -> None:
    body = _client(_dataset([_summary("STU0001")]), []).get("/student/STU0001").text
    assert "No competency is classified proficient" in body


def test_header_picker_lists_every_student_on_every_page() -> None:
    client = _client(_dataset([_summary("STU0001"), _summary("STU0002")]), [])
    for path in ("/", "/cohort/all", "/student/STU0001"):
        body = client.get(path).text
        assert '<option value="STU0001">' in body and '<option value="STU0002">' in body, path


def test_index_strength_count_matches_proficient_competencies() -> None:
    gaps = [_strength("STU0001", "Testing", 72.0, 1.5), _strength("STU0001", "Data Structures", 80.0, None)]
    body = _client(_dataset([_summary("STU0001")]), gaps).get("/").text
    assert 'data-sort-value="2">2</td>' in body


# --- outcome quality and competency progression ------------------------------

from lja.data.excel_loader import Assessment  # noqa: E402
from lja.model.learning_plan import LearningPlan, PlanPriority  # noqa: E402


def _quality_fixture() -> tuple[LjaDataset, list[CompetencyGap], SiloClusteringResult]:
    dataset = LjaDataset(
        silos={
            "CSE1OOF:SILO1": Silo("CSE1OOF", "SILO1", "Implement basic data structures"),
            "CSE2ALG:SILO1": Silo("CSE2ALG", "SILO1", "Understand the general objectives of algorithms"),
            "CSE2ALG:SILO2": Silo("CSE2ALG", "SILO2", "Design and evaluate data structures"),
        },
        assessments=[
            Assessment("CSE1OOF", "Test", 40.0, "Individual", False, False, ("SILO1",)),
            Assessment("CSE2ALG", "Assignment", 60.0, "Individual", False, False, ("SILO2",)),
        ],
        results=[
            ResultRow("STU0001", "CSE1OOF", "Test", 80.0, "", 40.0, 32.0, ("SILO1",)),
            ResultRow("STU0002", "CSE1OOF", "Test", 40.0, "", 40.0, 16.0, ("SILO1",)),
            ResultRow("STU0001", "CSE2ALG", "Assignment", 60.0, "", 60.0, 36.0, ("SILO2",)),
            ResultRow("STU0002", "CSE2ALG", "Assignment", 30.0, "", 60.0, 18.0, ("SILO2",)),
        ],
        student_summaries=[
            StudentSummary("STU0001", {"CSE1OOF": 80.0, "CSE2ALG": 60.0}, 70.0, "Credit"),
            StudentSummary("STU0002", {"CSE1OOF": 40.0, "CSE2ALG": 30.0}, 35.0, "Fail"),
        ],
    )
    clustering = _clustering(
        ("Data Structures", [("CSE1OOF", "SILO1"), ("CSE2ALG", "SILO2")]),
        ("Vague outcome", [("CSE2ALG", "SILO1")]),
    )
    clustering.flagged_silos.append(FlaggedSilo(subject_code="CSE2ALG", silo_local_id="SILO1", reason="Vague wording; not assessable."))
    gaps = [
        CompetencyGap("STU0001", "Data Structures", 68.0, 2, 2, "proficient", BASIS_RELATIVE, 1.2),
        CompetencyGap("STU0002", "Data Structures", 34.0, 2, 2, "persistent gap", BASIS_FLOOR, None),
    ]
    return dataset, gaps, clustering


def test_outcome_quality_page_shows_flags_and_progressions() -> None:
    dataset, gaps, clustering = _quality_fixture()
    response = _client(dataset, gaps, clustering).get("/silos")
    assert response.status_code == 200
    assert "Vague wording; not assessable." in response.text
    assert "no cross-subject link" in response.text
    assert "not assessed" in response.text
    assert 'href="/competency/data-structures"' in response.text
    assert "declining" in response.text  # 60 -> 45 across the two subjects
    # The word cloud gets its data as JSON with the vocabulary classes.
    assert '"term": "understand", "kind": "vague"' in response.text
    assert '"term": "implement", "kind": "measurable"' in response.text


def test_every_page_links_to_outcome_quality() -> None:
    dataset, gaps, clustering = _quality_fixture()
    client = _client(dataset, gaps, clustering)
    for path in ("/", "/student/STU0001", "/silos"):
        assert 'href="/silos"' in client.get(path).text


def test_competency_page_renders_points_in_year_order_and_404s_unknown() -> None:
    dataset, gaps, clustering = _quality_fixture()
    client = _client(dataset, gaps, clustering)
    response = client.get("/competency/data-structures")
    assert response.status_code == 200
    assert response.text.index("CSE1OOF") < response.text.index("CSE2ALG")
    assert '"attainment": [60.0, 45.0]' in response.text
    assert "Design and evaluate data structures" in response.text
    # A single-subject competency has a page too (its trace), just no progression chart.
    single = client.get("/competency/vague-outcome")
    assert single.status_code == 200
    assert "Taught in one subject only" in single.text
    assert "progression-chart" not in single.text
    assert client.get("/competency/nope").status_code == 404

# --- recommended next actions on student page (IOLG-122) ---------------------


def test_student_detail_renders_generated_learning_plan(tmp_path) -> None:
    dataset = _dataset(
        [
            StudentSummary(
                student_id="STU0001",
                subject_totals={"CSE1OOF": 70.0},
                average_total=70.0,
                performance_band="Credit",
            )
        ]
    )

    plan = LearningPlan(
        student_id="STU0001",
        summary="Focus next on strengthening your data-structure skills.",
        priorities=[
            PlanPriority(
                competency_label="Data Structures",
                silo_keys=[],
                subject_codes=["CSE1OOF"],
                assessment_keys=["CSE1OOF:Test"],
                evidence="Your test result shows this is the next area to strengthen.",
                actions="Practise linked lists",
            )
        ],
        strengths_to_build_on=["Testing"],
    )
    (tmp_path / "learning_plan_STU0001.json").write_text(
        plan.model_dump_json(),
        encoding="utf-8",
    )

    app = create_app(
        dataset,
        [],
        SiloClusteringResult(clusters=[]),
        plans_dir=tmp_path,
    )
    body = TestClient(app).get("/student/STU0001").text

    assert "Recommended next actions" in body
    next_actions = body.split("<h2>Recommended next actions</h2>", 1)[1].split(
        "<h2>Strengths</h2>", 1
    )[0]
    assert "Practise linked lists" in next_actions
    assert "Data Structures" in next_actions
    assert "CSE1OOF:Test" in next_actions


def test_student_detail_shows_plan_empty_state_when_file_is_missing(tmp_path) -> None:
    dataset = _dataset(
        [
            StudentSummary(
                student_id="STU0001",
                subject_totals={},
                average_total=70.0,
                performance_band="Credit",
            )
        ]
    )

    app = create_app(
        dataset,
        [],
        SiloClusteringResult(clusters=[]),
        plans_dir=tmp_path,
    )
    body = TestClient(app).get("/student/STU0001").text

    assert "No learning plan has been generated for this student yet" in body
    assert "python -m lja.plan" in body


def test_student_detail_without_plans_directory_is_safe() -> None:
    dataset = _dataset(
        [
            StudentSummary(
                student_id="STU0001",
                subject_totals={},
                average_total=70.0,
                performance_band="Credit",
            )
        ]
    )

    app = create_app(
        dataset,
        [],
        SiloClusteringResult(clusters=[]),
        plans_dir=None,
    )
    response = TestClient(app).get("/student/STU0001")

    assert response.status_code == 200
    assert "No learning plan has been generated for this student yet" in response.text



# --- priority groups list every member (IOLG-134 follow-up) ---


def test_cohort_title_prints_the_floor_in_force_not_a_placeholder() -> None:
    dataset, gaps = _two_students_one_with_a_persistent_gap()
    body = _client(dataset, gaps).get("/cohort/priority-1").text
    assert "{floor}" not in body
    assert "below the 50% floor" in body



# ---------------------------------------------------------------- trajectory (IOLG-106)

def _trajectory_fixture() -> tuple[LjaDataset, list[CompetencyGap], SiloClusteringResult]:
    """One student who sat CSE1OOF and CSE2ALG; CSE3CAP is ahead."""
    clustering = _clustering(("Data Structures", [("CSE3CAP", "SILO1"), ("CSE1OOF", "SILO2"), ("CSE2ALG", "SILO2")]))
    dataset = _dataset(
        summaries=[
            StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 60.0, "CSE2ALG": 50.0}, average_total=55.0, performance_band="P")
        ],
        results=[
            ResultRow(student_id="STU0001", subject_code="CSE1OOF", assessment_name="Exam", score=60.0,
                      feedback_comment="", weight=1.0, weighted_score=60.0, silo_ids=("SILO2",)),
            ResultRow(student_id="STU0001", subject_code="CSE2ALG", assessment_name="Exam", score=50.0,
                      feedback_comment="", weight=1.0, weighted_score=50.0, silo_ids=("SILO2",)),
        ],
    )
    gaps = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=55.0,
            subjects_evidencing=2, n_observations=2, classification="persistent gap",
            classification_basis=BASIS_RELATIVE, relative_position=-1.4,
        ),
    ]
    return dataset, gaps, clustering


def test_gap_card_shows_the_subject_chain_in_sequence_order_with_the_ahead_subject_marked() -> None:
    dataset, gaps, clustering = _trajectory_fixture()
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    chain = re.search(r'<ol class="subject-chain">(.*?)</ol>', body, re.S)
    assert chain is not None
    steps = re.findall(r'<li class="chain-step (\w+)[^"]*"[^>]*>\s*<a href="/subject/(\w+)">', chain.group(1))
    assert steps == [("taken", "CSE1OOF"), ("taken", "CSE2ALG"), ("ahead", "CSE3CAP")]
    assert "prepare" in chain.group(1)
    assert "order: declared sequence" in body
    assert "declining" in body  # 60 -> 50 across the sequence


def test_gap_card_states_the_order_came_from_the_year_digit_when_nothing_is_declared(monkeypatch) -> None:
    from lja import config

    monkeypatch.setattr(config, "SUBJECT_SEQUENCE", "")
    dataset, gaps, clustering = _trajectory_fixture()
    body = _client(dataset, gaps, clustering).get("/student/STU0001").text
    assert "order: year digit" in body


def test_future_subjects_are_only_offered_for_a_gap_not_a_strength() -> None:
    dataset, gaps, clustering = _trajectory_fixture()
    strong = [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=80.0,
            subjects_evidencing=2, n_observations=2, classification="proficient",
            classification_basis=BASIS_CEILING, relative_position=None,
        ),
    ]
    body = _client(dataset, strong, clustering).get("/student/STU0001").text
    assert "Flag for intervention" not in body
    assert "prepare" not in re.search(r'<ol class="subject-chain">(.*?)</ol>', body, re.S).group(1)


def test_run_page_shows_the_declared_sequence_and_the_stable_band() -> None:
    dataset, gaps, clustering = _trajectory_fixture()
    body = _client(dataset, gaps, clustering).get("/run").text
    assert "LJA_SUBJECT_SEQUENCE" in body
    assert "CSE1OOF &rarr; CSE2ALG &rarr; CSE3CAP" in body
    assert "LJA_TREND_STABLE_BAND" in body


def test_glossary_defines_trajectory() -> None:
    dataset, gaps, clustering = _trajectory_fixture()
    body = _client(dataset, gaps, clustering).get("/glossary").text
    assert 'id="trajectory"' in body
    assert "Order, not time" in body
# --- practice quiz (tender R8) ----------------------------------------------

from lja.model.quiz import QuizDocument, QuizItem, QuizSubject  # noqa: E402


def _one_student() -> LjaDataset:
    return _dataset([StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit")])


def _quiz_document() -> QuizDocument:
    return QuizDocument(
        student_id="STU0001",
        introduction="Two practice questions on data structures; this is practice, not assessment.",
        items=[
            QuizItem(
                competency_label="Data Structures",
                gap_kind="persistent gap",
                subject_code="CSE2ALG",
                silo_key="CSE2ALG:SILO1",
                assessment_key="CSE2ALG:Assignment 1",
                kind="multiple_choice",
                stem="Which linked-list operation is constant time from the head?",
                options=["Insert at the head", "Find the last node", "Delete by value"],
                correct_index=0,
                explanation="Only the head is reachable without traversal. Revisit CSE2ALG:SILO1.",
            )
        ],
        subjects=[
            QuizSubject(code="CSE2ALG", title="Algorithms and Data Structures", year_level=2, synopsis="Linear structures, trees and graphs."),
            QuizSubject(code="CSE3CAP"),
        ],
    )


def test_student_detail_renders_the_quiz_with_subjects_answer_and_caveat(tmp_path) -> None:
    (tmp_path / "quiz_STU0001.json").write_text(_quiz_document().model_dump_json(), encoding="utf-8")
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=tmp_path)
    body = TestClient(app).get("/student/STU0001").text

    section = body.split("<h2>Practice quiz</h2>", 1)[1].split("<h2>Strengths</h2>", 1)[0]
    assert "this is practice, not assessment" in section
    assert "Which linked-list operation is constant time from the head?" in section
    assert "<li>Insert at the head</li>" in section
    assert "Show answer" in section
    assert "<strong>A.</strong> Insert at the head" in section
    assert "Revisit CSE2ALG:SILO1." in section
    assert "CSE2ALG:SILO1 &middot; CSE2ALG:Assignment 1" in section
    # Subject info: synopsis where the catalogue had one, an honest note where it did not.
    assert "Algorithms and Data Structures" in section
    assert "Linear structures, trees and graphs." in section
    assert "No handbook synopsis in the catalogue for this subject." in section
    # The page says what the checks do not cover.
    assert "do <strong>not</strong> confirm the marked answer is correct" in section


def test_student_detail_shows_quiz_empty_state_when_file_is_missing(tmp_path) -> None:
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=tmp_path)
    body = TestClient(app).get("/student/STU0001").text
    assert "No practice quiz has been generated for this student yet" in body
    assert "python -m lja.quiz" in body


def test_student_detail_without_quizzes_directory_is_safe() -> None:
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=None)
    response = TestClient(app).get("/student/STU0001")
    assert response.status_code == 200
    assert "No practice quiz has been generated" in response.text


def test_student_detail_shows_educator_block_and_flags_disagreement(tmp_path) -> None:
    from lja.model.quiz import EducatorNote, EducatorReview

    document = _quiz_document()
    document.items.append(document.items[0].model_copy(update={"stem": "Second question?", "correct_index": 1}))
    document = document.model_copy(
        update={
            "educator_review": EducatorReview(
                reviewer="fake",
                notes=[
                    EducatorNote(question_index=0, chosen_index=0, marking_verdict=None, confidence="high", teaching_explanation="Head insert needs no traversal."),
                    EducatorNote(question_index=1, chosen_index=2, marking_verdict=None, confidence="low", teaching_explanation="Delete by value is also linear.", concerns="Two options are defensible."),
                ],
            )
        }
    )
    (tmp_path / "quiz_STU0001.json").write_text(document.model_dump_json(), encoding="utf-8")
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=tmp_path)
    body = TestClient(app).get("/student/STU0001").text
    section = body.split("<h2>Practice quiz</h2>", 1)[1].split("<h2>Strengths</h2>", 1)[0]

    assert section.count("For educator view only") == 2
    assert "blind check agrees" in section
    assert "blind check disagrees: chose C" in section
    assert "Head insert needs no traversal." in section
    assert "<strong>Concern:</strong> Two options are defensible." in section
    assert "disagreed on question 2</strong>; check those first." in " ".join(section.split())
    assert "a label, not an access control" in section


def test_student_detail_quiz_without_review_has_no_educator_block(tmp_path) -> None:
    (tmp_path / "quiz_STU0001.json").write_text(_quiz_document().model_dump_json(), encoding="utf-8")
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=tmp_path)
    body = TestClient(app).get("/student/STU0001").text
    assert "For educator view only" not in body
    assert "blind pass" not in body


def test_student_detail_renders_a_written_task_with_model_answer_and_second_marker(tmp_path) -> None:
    from lja.model.quiz import EducatorNote, EducatorReview, QuizItem

    document = _quiz_document()
    document.items.append(
        QuizItem(
            competency_label="Data Structures", gap_kind="persistent gap", subject_code="CSE2ALG",
            silo_key="CSE2ALG:SILO1", assessment_key="CSE2ALG:Assignment 1", kind="written",
            stem="Implement insert-at-head for a singly linked list and state its cost.",
            model_answer="Create a node pointing at the current head and make it the head: O(1).",
            marking_points=["New node points at old head", "States O(1)"],
            explanation="A weak answer traverses first. Revisit CSE2ALG:SILO1.",
        )
    )
    document = document.model_copy(
        update={
            "educator_review": EducatorReview(
                reviewer="fake",
                notes=[
                    EducatorNote(question_index=0, chosen_index=0, marking_verdict=None, confidence="high", teaching_explanation="Head insert needs no traversal."),
                    EducatorNote(question_index=1, chosen_index=None, marking_verdict="partly", confidence="medium", teaching_explanation="Mention the empty-list case.", concerns="No marking point covers the empty list."),
                ],
            )
        }
    )
    (tmp_path / "quiz_STU0001.json").write_text(document.model_dump_json(), encoding="utf-8")
    app = create_app(_one_student(), [], SiloClusteringResult(clusters=[]), quizzes_dir=tmp_path)
    section = TestClient(app).get("/student/STU0001").text.split("<h2>Practice quiz</h2>", 1)[1].split("<h2>Strengths</h2>", 1)[0]

    assert "Written task.</span> Implement insert-at-head" in section
    assert "Show model answer" in section
    assert "Create a node pointing at the current head" in section
    assert "<li>States O(1)</li>" in section
    assert "second marker: model answer partly the marking points" in section
    assert "disagreed on question 2</strong>; check those first." in " ".join(section.split())
    assert "No marking point covers the empty list." in section
