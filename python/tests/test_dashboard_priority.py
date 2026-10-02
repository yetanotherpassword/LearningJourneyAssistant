"""Priority groups, the /run provenance page and the /glossary page.

Same approach as test_dashboard.py: FastAPI's TestClient over in-memory
fixtures, no Excel, no clustering cache, no LLM.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from lja.dashboard.app import create_app
from lja.dashboard.run_info import RunInfo, collect_run_info
from lja.data.excel_loader import LjaDataset, StudentSummary
from lja.model.gap_detection import BASIS_CEILING, BASIS_FLOOR, BASIS_RELATIVE, CompetencyGap, GapThresholds
from lja.model.silo_clustering import SiloClusteringResult

ALL_IDS = ("STU0001", "STU0002", "STU0003", "STU0004")


def _dataset(summaries: list[StudentSummary]) -> LjaDataset:
    return LjaDataset(silos={}, assessments=[], results=[], student_summaries=summaries)


def _client(dataset: LjaDataset, gaps: list[CompetencyGap], **kwargs) -> TestClient:
    return TestClient(create_app(dataset, gaps, SiloClusteringResult(clusters=[]), **kwargs))


def _four_students_one_per_priority() -> tuple[LjaDataset, list[CompetencyGap]]:
    """STU0003 breaches the floor (1st priority), STU0002 is flagged only
    relative to their own median (2nd), STU0004 has one isolated gap (3rd),
    STU0001 has no gap. Numbered against the severity order so a test cannot
    pass on student-id order by accident.
    """
    dataset = _dataset(
        [
            StudentSummary(student_id="STU0001", subject_totals={}, average_total=70.0, performance_band="Credit"),
            StudentSummary(student_id="STU0002", subject_totals={}, average_total=68.0, performance_band="Credit"),
            StudentSummary(student_id="STU0003", subject_totals={}, average_total=45.0, performance_band="Fail"),
            StudentSummary(student_id="STU0004", subject_totals={}, average_total=66.0, performance_band="Credit"),
        ]
    )
    gaps = [
        CompetencyGap("STU0002", "Data Structures", 60.0, 2, 4, "persistent gap", BASIS_RELATIVE, -1.5),
        CompetencyGap("STU0003", "Data Structures", 35.0, 2, 4, "persistent gap", BASIS_FLOOR, None),
        CompetencyGap("STU0004", "Data Structures", 58.0, 1, 2, "isolated gap", BASIS_RELATIVE, -1.2),
        CompetencyGap("STU0001", "Data Structures", 90.0, 2, 4, "proficient", BASIS_CEILING, None),
    ]
    return dataset, gaps


def _full_table(body: str) -> str:
    return body[body.index('<h2 id="everyone">'):]


def _members(body: str) -> list[str]:
    table = _full_table(body)
    return [sid for sid in ALL_IDS if f'href="/student/{sid}"' in table]


def test_priority_groups_partition_flagged_students() -> None:
    dataset, gaps = _four_students_one_per_priority()
    client = _client(dataset, gaps)
    body = client.get("/").text

    for key in ("priority-1", "priority-2", "priority-3"):
        assert f'href="/cohort/{key}"' in body
    flat = " ".join(body.split()).replace("&mdash;", "—")
    assert "1st priority — below the 50% floor: 1 student<" in flat
    assert "3 of 4 students have at least one flagged competency; 1 have none" in flat

    assert "below the absolute floor of 50%" in client.get("/cohort/priority-1").text
    assert _members(client.get("/cohort/priority-1").text) == ["STU0003"]
    assert _members(client.get("/cohort/priority-2").text) == ["STU0002"]
    assert _members(client.get("/cohort/priority-3").text) == ["STU0004"]


def test_students_render_in_priority_order() -> None:
    dataset, gaps = _four_students_one_per_priority()
    table = _full_table(_client(dataset, gaps).get("/").text)

    positions = [table.index(f'href="/student/{sid}"') for sid in ("STU0003", "STU0002", "STU0004", "STU0001")]
    assert positions == sorted(positions)
    for rank in (1, 2, 3):
        assert table.count(f'class="priority-{rank}"') == 1


def test_priority_group_lists_every_member_in_its_own_filter_box() -> None:
    """No preview cut: thirteen floor-breach students all appear in the
    1st-priority section, inside a filter box with a sortable table, and
    again in the full table underneath."""
    n = 13
    dataset = _dataset(
        [StudentSummary(f"STU{i:04d}", {}, 40.0, "Fail") for i in range(1, n + 1)]
    )
    gaps = [
        CompetencyGap(f"STU{i:04d}", "Data Structures", 30.0 + i, 2, 4, "persistent gap", BASIS_FLOOR, None)
        for i in range(1, n + 1)
    ]
    body = _client(dataset, gaps).get("/").text
    group = body[
        body.index('<section class="priority-group priority-group-1">'):
        body.index('<section class="priority-group priority-group-2">')
    ]

    assert group.count('href="/student/') == n
    assert 'class="scroll-search"' in group
    assert '<table class="sortable">' in group
    assert "in this group" not in group
    assert _full_table(body).count('href="/student/') == n


def test_run_page_prints_the_thresholds_the_classifier_was_given() -> None:
    """The page must describe the run on the page, not config defaults: a
    dashboard started with --absolute-floor 45 has to say 45, and say that
    it differs from the default.
    """
    dataset, gaps = _four_students_one_per_priority()
    client = _client(
        dataset, gaps,
        thresholds=GapThresholds(absolute_floor=45.0, absolute_ceiling=80.0, relative_gap_cutoff=-1.5),
    )
    flat = " ".join(client.get("/run").text.split())

    assert "Below <strong>45%</strong>" in flat
    assert "At or above <strong>80%</strong>" in flat
    assert "At or below <strong>-1.5</strong>" in flat
    assert "2+ subjects" in flat
    assert '<td class="val">45 %' in flat and 'class="issue">changed' in flat
    assert "LJA_GAP_ABSOLUTE_FLOOR" in flat and "--absolute-floor" in flat
    assert "No command recorded" in flat  # no RunInfo in tests
    # The same values reach the tiles and the glossary.
    assert "below the 45% floor" in client.get("/").text
    assert "45% in this run" in client.get("/glossary").text


def test_run_page_shows_command_inputs_and_generator_record() -> None:
    dataset, gaps = _four_students_one_per_priority()
    info = RunInfo(
        command="python -m lja.dashboard --excel-path x.xlsx --port 8765",
        started_at="2026-09-28 16:00 AEST",
        excel_path="x.xlsx",
        clustering_cache="x.clustering.json",
        review_file=None,
        code_version="abc1234",
        generator={"truth_file": "x.truth.json", "catalogue": "cat.yaml", "seed": 11, "params": {"n_students": 4, "noise_sd": 3.0}},
        environment={"LJA_GAP_ABSOLUTE_FLOOR": "50.0"},
    )
    body = _client(dataset, gaps, run_info=info).get("/run").text

    assert "python -m lja.dashboard --excel-path x.xlsx --port 8765" in body
    assert "abc1234" in body
    assert "every cluster counts as pending" in body
    assert "<code>noise_sd</code>" in body and "Seed" in body and ">11<" in body
    assert "= 50.0" in body  # env var value shown beside its name


def test_collect_run_info_reads_only_provenance_from_the_truth_file(tmp_path) -> None:
    xlsx = tmp_path / "cohort.xlsx"
    xlsx.write_bytes(b"")
    (tmp_path / "cohort.truth.json").write_text(
        json.dumps({"seed": 7, "params": {"n_students": 3}, "catalogue": "c.yaml", "planted": {"STU0001": {"competency": "x"}}})
    )
    info = collect_run_info(
        excel_path=str(xlsx),
        clustering_cache="c.json",
        review_file=None,
        environ={"LJA_GAP_MIN_SPREAD": "2"},
        argv=["ignored", "--excel-path", str(xlsx), "--port", "1"],
    )

    assert info.command.startswith("python -m lja.dashboard --excel-path ")
    assert info.generator == {
        "truth_file": str(tmp_path / "cohort.truth.json"), "catalogue": "c.yaml", "seed": 7, "params": {"n_students": 3},
    }
    assert "planted" not in info.generator
    assert info.environment["LJA_GAP_MIN_SPREAD"] == "2"
    assert info.environment["LJA_GAP_ABSOLUTE_FLOOR"] is None


def test_collect_run_info_without_a_truth_file(tmp_path) -> None:
    xlsx = tmp_path / "real.xlsx"
    xlsx.write_bytes(b"")
    info = collect_run_info(excel_path=str(xlsx), clustering_cache="c.json", review_file="r.json", environ={}, argv=["x"])
    assert info.generator is None
    assert info.review_file == "r.json"


def test_glossary_defines_mad_and_is_linked_from_the_tables() -> None:
    dataset, gaps = _four_students_one_per_priority()
    client = _client(dataset, gaps)

    glossary = client.get("/glossary").text
    assert 'id="mad"' in glossary and "median absolute deviation" in glossary
    for anchor in ("silo", "competency", "persistent-gap", "isolated-gap", "priority", "absolute-floor"):
        assert f'id="{anchor}"' in glossary

    assert 'href="/glossary#mad"' in client.get("/").text
    assert 'href="/glossary#mad"' in client.get("/student/STU0002").text


def test_every_page_links_to_run_and_glossary() -> None:
    dataset, gaps = _four_students_one_per_priority()
    client = _client(dataset, gaps)
    for path in ("/", "/cohort/priority-1", "/student/STU0002", "/run", "/glossary"):
        body = client.get(path).text
        assert 'href="/run"' in body and 'href="/glossary"' in body, path


def test_severity_chart_includes_unflagged_students_as_grey_points() -> None:
    dataset, gaps = _four_students_one_per_priority()
    body = _client(dataset, gaps).get("/").text
    # STU0001 has no gap; its only competency row is 90% proficient, so it is
    # plotted at y = 90 with priority 0 (the grey "no flag" series).
    assert '{"id": "STU0001", "x": 70.0, "y": 90.0, "p": 0}' in body
    assert '{"id": "STU0003", "x": 45.0, "y": 35.0, "p": 1}' in body
    assert "The 1 students with no flag" in " ".join(body.split())


def test_severity_chart_draws_the_floor_and_ceiling_in_force() -> None:
    dataset, gaps = _four_students_one_per_priority()
    body = _client(dataset, gaps, thresholds=GapThresholds(absolute_floor=45.0, absolute_ceiling=80.0)).get("/").text
    assert 'const severityLines = {"floor": 45.0, "ceiling": 80.0};' in body


def test_provenance_page_gives_the_pipeline_command_that_reproduces_the_numbers() -> None:
    """The dashboard classifies at start-up and never reads the CLI's gap
    report, so the page reconstructs the equivalent lja.cli command from the
    inputs it does know, with a flag for every threshold that differs from
    the default and an env prefix for the one that has no flag."""
    dataset, gaps = _four_students_one_per_priority()
    info = RunInfo(
        command="python -m lja.dashboard --excel-path x.xlsx --absolute-floor 45",
        started_at="2026-10-02 18:20 AEST",
        excel_path="../data/cohort.xlsx",
        clustering_cache="x.clustering.json",
        review_file="x.clustering.review.json",
        code_version="abc1234",
        generator=None,
        environment={},
    )
    thresholds = GapThresholds(absolute_floor=45.0, fallback_proficient=60.0)
    body = _client(dataset, gaps, thresholds=thresholds, run_info=info).get("/run").text
    assert "Provenance" in body
    assert "LJA_GAP_FALLBACK_PROFICIENT=60 python -m lja.cli ../data/cohort.xlsx --clustering-cache x.clustering.json --absolute-floor 45" in body
    assert "--review-file" not in body  # the default review path beside the cache is not repeated


def test_provenance_page_without_run_info_does_not_invent_paths() -> None:
    dataset, gaps = _four_students_one_per_priority()
    body = _client(dataset, gaps).get("/run").text
    assert "paths unknown" in body
