"""Every count tile links to the list it counts; the list pages exist and
hold exactly what the tile said.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from lja.dashboard.app import create_app
from lja.data.excel_loader import Assessment, LjaDataset, ResultRow, Silo, StudentSummary
from lja.model.gap_detection import BASIS_FLOOR, BASIS_RELATIVE, CompetencyGap
from lja.model.silo_clustering import CompetencyCluster, FlaggedSilo, SiloClusteringResult, SiloRef


def _fixture() -> tuple[LjaDataset, list[CompetencyGap], SiloClusteringResult]:
    """Two subjects, four SILOs. CSE2ALG:SILO1 is flagged, vague, unassessed
    and links to no other subject; CSE2ALG:SILO3 is unassessed and unlinked.
    Data Structures spans both subjects, so it has a progression page.
    """
    dataset = LjaDataset(
        silos={
            "CSE1OOF:SILO1": Silo("CSE1OOF", "SILO1", "Implement basic data structures"),
            "CSE2ALG:SILO1": Silo("CSE2ALG", "SILO1", "Understand the general objectives of algorithms"),
            "CSE2ALG:SILO2": Silo("CSE2ALG", "SILO2", "Design and evaluate data structures"),
            "CSE2ALG:SILO3": Silo("CSE2ALG", "SILO3", "Analyse algorithm complexity"),
        },
        assessments=[
            Assessment("CSE1OOF", "Test", 40.0, "Individual", False, False, ("SILO1",)),
            Assessment("CSE2ALG", "Assignment", 60.0, "Individual", False, True, ("SILO2",)),  # hurdle
        ],
        results=[
            ResultRow("STU0001", "CSE1OOF", "Test", 80.0, "", 40.0, 32.0, ("SILO1",)),
            ResultRow("STU0002", "CSE1OOF", "Test", 40.0, "", 40.0, 16.0, ("SILO1",)),
            ResultRow("STU0001", "CSE2ALG", "Assignment", 60.0, "", 60.0, 36.0, ("SILO2",)),
        ],
        student_summaries=[
            StudentSummary("STU0001", {"CSE1OOF": 80.0, "CSE2ALG": 60.0}, 70.0, "Credit"),
            StudentSummary("STU0002", {"CSE1OOF": 40.0}, 40.0, "Fail"),
        ],
    )
    clustering = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Data Structures", rationale="Both build and assess structures.",
                members=[SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1"), SiloRef(subject_code="CSE2ALG", silo_local_id="SILO2")],
            ),
            CompetencyCluster(
                competency_label="Vague outcome", rationale="Placed alone.",
                members=[SiloRef(subject_code="CSE2ALG", silo_local_id="SILO1")],
            ),
            CompetencyCluster(
                competency_label="Complexity", rationale="Single subject.",
                members=[SiloRef(subject_code="CSE2ALG", silo_local_id="SILO3")],
            ),
        ],
        flagged_silos=[FlaggedSilo(subject_code="CSE2ALG", silo_local_id="SILO1", reason="Vague wording; not assessable.")],
    )
    gaps = [
        CompetencyGap("STU0001", "Data Structures", 68.0, 2, 2, "proficient", BASIS_RELATIVE, 1.2),
        CompetencyGap("STU0002", "Data Structures", 34.0, 1, 1, "isolated gap", BASIS_FLOOR, None),
    ]
    return dataset, gaps, clustering


def _client() -> TestClient:
    dataset, gaps, clustering = _fixture()
    return TestClient(create_app(dataset, gaps, clustering))


def _tile_links(body: str) -> dict[str, str]:
    """label -> href for every stat tile on the page."""
    found = {}
    for href, label in re.findall(r'<a class="stat stat-link" href="([^"]+)"[^>]*>\s*<div class="num[^"]*">.*?</div>\s*<div class="label">(.*?)</div>', body, flags=re.S):
        found[" ".join(label.split())] = href
    return found


def test_outcome_quality_tiles_link_to_their_lists() -> None:
    links = _tile_links(_client().get("/silos").text)
    assert links["subjects"] == "/subjects"
    assert links["SILOs"] == "/silos/list/all"
    assert links["flagged by the clustering"] == "/silos/list/flagged"
    assert links["link to no other subject"] == "/silos/list/orphan"
    assert links["never assessed"] == "/silos/list/unassessed"
    assert links["vaguely worded"] == "/silos/list/vague"


def test_run_page_tiles_link_to_their_lists() -> None:
    links = _tile_links(_client().get("/run").text)
    assert links["students"] == "/cohort/all"
    assert links["subjects"] == "/subjects"
    assert links["SILOs"] == "/silos/list/all"
    assert links["assessments"] == "/assessments"
    assert links["result rows"] == "/assessments"
    assert links["competencies (clusters)"] == "/competencies"
    assert links["student × competency rows"] == "/competencies"


def test_index_statistic_tiles_link_to_cohort_or_glossary() -> None:
    client = _client()
    links = _tile_links(client.get("/").text)
    assert links["students"] == "/cohort/all#everyone"
    assert links["mean"] == "/glossary#mean"
    assert links["std deviation"] == "/glossary#standard-deviation"
    assert links["interquartile range"] == "/glossary#quartiles"
    glossary = client.get("/glossary").text
    for anchor in ("mean", "median", "standard-deviation", "variance", "range", "quartiles", "subject", "assessment", "result-row", "gap-rate"):
        assert f'id="{anchor}"' in glossary, anchor


def test_silo_lists_hold_exactly_what_the_tile_counted() -> None:
    client = _client()
    silos_page = client.get("/silos").text
    tile_counts = {
        label: int(num)
        for num, label in re.findall(r'<div class="num[^"]*">(\d+)</div>\s*<div class="label">([^<]+)</div>', silos_page)
    }
    expected = {
        "all": tile_counts["SILOs"],
        "flagged": tile_counts["flagged by the clustering"],
        "orphan": tile_counts["link to no other subject"],
        "unassessed": tile_counts["never assessed"],
        "vague": tile_counts["vaguely worded"],
    }
    # SILO1 of CSE2ALG is flagged, vague AND unassessed; SILO3 is unassessed only.
    assert expected == {"all": 4, "flagged": 1, "orphan": 2, "unassessed": 2, "vague": 1}

    for key, count in expected.items():
        body = client.get(f"/silos/list/{key}").text
        assert body.count('<tr class="') == count, key
        assert f"<strong>{count}</strong> of 4 outcomes" in body

    flagged = client.get("/silos/list/flagged").text
    assert "Vague wording; not assessable." in flagged
    assert "SILO2" not in flagged.split('<tbody>')[1]
    assert client.get("/silos/list/nope").status_code == 404


def test_subjects_page_and_subject_page() -> None:
    client = _client()
    subjects = client.get("/subjects").text
    assert 'href="/subject/CSE1OOF"' in subjects and 'href="/subject/CSE2ALG"' in subjects
    assert subjects.count("<tr>") == 2 + 1  # two subjects plus the header row

    page = client.get("/subject/CSE2ALG").text
    assert "<h1>CSE2ALG</h1>" in page
    assert "Design and evaluate data structures" in page
    assert "Implement basic data structures" not in page       # other subject's outcome
    assert "Assignment" in page and "hurdle" in page
    assert 'data-sort-value="1">1</td>' in page                  # one result row for the assignment
    assert client.get("/subject/NOPE").status_code == 404


def test_competencies_page_totals_the_gap_rows() -> None:
    body = _client().get("/competencies").text
    assert "2 rows in all" in body
    assert 'href="/competency/data-structures"' in body          # spans two subjects
    assert "Complexity</strong> <span class=\"muted\">(one subject)</span>" in body
    assert "Both build and assess structures." in body
    assert 'href="/subject/CSE1OOF"' in body


def test_assessments_page_totals_the_result_rows() -> None:
    body = _client().get("/assessments").text
    assert "3 result rows in all" in body
    assert "Test" in body and "Assignment" in body
    assert 'data-sort-value="2">2</td>' in body                  # two result rows for the test
    assert "name an assessment that is not in the map" not in body


def test_subject_codes_link_to_subject_pages_everywhere() -> None:
    client = _client()
    for path in ("/silos", "/silos/list/all", "/competency/data-structures", "/competencies", "/assessments"):
        assert 'href="/subject/CSE1OOF"' in client.get(path).text, path


def test_scroll_boxed_tables_have_filter_and_expand_controls() -> None:
    """The toolbar ships hidden and scrollbox.js reveals it, so a page with
    JavaScript off never shows controls that do nothing."""
    client = _client()
    for path in ("/", "/subjects", "/silos/list/all", "/competencies", "/assessments"):
        body = client.get(path).text
        assert '<div class="scroll-panel" data-what="' in body, path
        assert '<div class="scroll-tools" hidden>' in body, path
        assert 'class="scroll-search"' in body and 'class="scroll-expand"' in body, path
        assert '/static/scrollbox.js' in body, path
    assert client.get("/static/scrollbox.js").status_code == 200
