"""Generate-from-the-student-page (IOLG-137), exercised with a fake runner
so no test spawns python or a model. What is checked: the button exists only
when a Generator is configured, the command is the real CLI invocation with
this run's inputs, a job runs and the page shows the result, a failure
leaves the old file alone, and two presses do not start two jobs.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi.testclient import TestClient

from lja.dashboard.app import create_app
from lja.dashboard.generate import DONE, FAILED, GenerateConfig, Generator
from lja.dashboard.run_info import RunInfo
from lja.data.excel_loader import LjaDataset, StudentSummary
from lja.model.gap_detection import BASIS_FLOOR, CompetencyGap
from lja.model.silo_clustering import SiloClusteringResult

PLAN = {
    "student_id": "STU0001",
    "summary": "Work on data structures.",
    "priorities": [
        {
            "competency_label": "Data Structures",
            "silo_keys": ["CSE1OOF:SILO2"],
            "subject_codes": ["CSE1OOF"],
            "assessment_keys": ["CSE1OOF:Exam"],
            "evidence": "40% in CSE1OOF.",
            "actions": "Redo the exam questions.",
        }
    ],
    "strengths_to_build_on": [],
}


def _dataset() -> LjaDataset:
    return LjaDataset(
        silos={}, assessments=[], results=[],
        student_summaries=[StudentSummary(student_id="STU0001", subject_totals={"CSE1OOF": 40.0}, average_total=40.0, performance_band="Fail")],
    )


def _gaps() -> list[CompetencyGap]:
    return [
        CompetencyGap(
            student_id="STU0001", competency_label="Data Structures", attainment_pct=40.0,
            subjects_evidencing=1, n_observations=1, classification="isolated gap",
            classification_basis=BASIS_FLOOR, relative_position=None,
        )
    ]


def _run_info() -> RunInfo:
    return RunInfo(
        command="python -m lja.dashboard", started_at="now", excel_path="../data/cohort.xlsx",
        clustering_cache="cache.json", review_file="cache.review.json", code_version=None, generator=None, environment={},
    )


def _config(tmp_path: Path) -> GenerateConfig:
    return GenerateConfig(
        excel_path="../data/cohort.xlsx", clustering_cache="cache.json", review_file="cache.review.json",
        plans_dir=tmp_path / "plans", quizzes_dir=tmp_path / "quizzes", python="python",
    )


def _wait(client: TestClient, url: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(url).json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_without_a_generator_the_page_shows_the_real_workbook_path_and_no_button() -> None:
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), run_info=_run_info()))
    body = client.get("/student/STU0001").text
    assert "python -m lja.plan ../data/cohort.xlsx STU0001" in body
    assert "&lt;xlsx&gt;" not in body
    assert 'class="generate-box"' not in body
    assert client.post("/student/STU0001/generate/plan").status_code == 403


def test_button_appears_and_says_generate_when_no_file_exists(tmp_path) -> None:
    gen = Generator(_config(tmp_path), runner=lambda cmd, on_line: 0)
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), plans_dir=tmp_path / "plans", quizzes_dir=tmp_path / "quizzes", generator=gen))
    body = client.get("/student/STU0001").text
    assert body.count('class="generate-box"') == 2  # plan and quiz
    assert "Generate learning plan" in body and "Generate practice quiz" in body
    assert "Regenerate" not in body


def test_command_is_the_real_cli_invocation_with_this_runs_inputs(tmp_path) -> None:
    gen = Generator(_config(tmp_path))
    cmd = gen.command("plan", "STU0001")
    assert cmd == [
        "python", "-u", "-m", "lja.plan", "../data/cohort.xlsx", "STU0001",
        "--clustering-cache", "cache.json", "--out-dir", str(tmp_path / "plans"),
        "--review-file", "cache.review.json",
    ]
    assert gen.command("quiz", "STU0001")[3] == "lja.quiz"
    assert gen.output_path("quiz", "STU0001") == tmp_path / "quizzes" / "quiz_STU0001.json"


def test_pressing_generate_runs_the_job_and_the_page_then_shows_the_plan_and_regenerate(tmp_path) -> None:
    def fake_runner(cmd, on_line):
        on_line("attempt 1: grounded")
        out = Path(cmd[cmd.index("--out-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "learning_plan_STU0001.json").write_text(json.dumps(PLAN))
        return 0

    gen = Generator(_config(tmp_path), runner=fake_runner)
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), plans_dir=tmp_path / "plans", quizzes_dir=tmp_path / "quizzes", generator=gen))
    started = client.post("/student/STU0001/generate/plan")
    assert started.status_code == 202
    assert started.json()["state"] in ("running", "done")
    job = _wait(client, "/student/STU0001/generate/plan/status")
    assert job["state"] == DONE and job["returncode"] == 0
    assert "attempt 1: grounded" in job["lines"]
    body = client.get("/student/STU0001").text
    assert "Work on data structures." in body
    assert "Regenerate learning plan" in body


def test_a_failed_generation_reports_the_output_and_keeps_the_old_file(tmp_path) -> None:
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "learning_plan_STU0001.json").write_text(json.dumps(PLAN))

    def failing_runner(cmd, on_line):
        on_line("GroundingError: invented SILO CSE9ZZZ:SILO1")
        return 1

    gen = Generator(_config(tmp_path), runner=failing_runner)
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), plans_dir=plans, quizzes_dir=tmp_path / "quizzes", generator=gen))
    client.post("/student/STU0001/generate/plan")
    job = _wait(client, "/student/STU0001/generate/plan/status")
    assert job["state"] == FAILED and job["returncode"] == 1
    assert "GroundingError" in job["lines"][0]
    assert json.loads((plans / "learning_plan_STU0001.json").read_text()) == PLAN
    assert "Work on data structures." in client.get("/student/STU0001").text


def test_a_second_press_while_running_is_refused(tmp_path) -> None:
    release = time.monotonic() + 0.3

    def slow_runner(cmd, on_line):
        while time.monotonic() < release:
            time.sleep(0.01)
        return 1

    gen = Generator(_config(tmp_path), runner=slow_runner)
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), plans_dir=tmp_path / "plans", quizzes_dir=tmp_path / "quizzes", generator=gen))
    assert client.post("/student/STU0001/generate/quiz").status_code == 202
    assert client.post("/student/STU0001/generate/quiz").status_code == 409
    assert client.get("/student/STU0001").text.count('data-running="true"') == 1
    _wait(client, "/student/STU0001/generate/quiz/status")


def test_unknown_artefact_and_unknown_student_are_404(tmp_path) -> None:
    gen = Generator(_config(tmp_path), runner=lambda cmd, on_line: 0)
    client = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), generator=gen))
    assert client.post("/student/STU0001/generate/essay").status_code == 404
    assert client.post("/student/NOBODY/generate/plan").status_code == 404
    assert client.get("/student/STU0001/generate/plan/status").status_code == 404  # never started


def test_provenance_page_says_whether_generation_is_on(tmp_path) -> None:
    off = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]))).get("/run").text
    assert re.search(r"Generation from the student page.*?off", off, re.S)
    gen = Generator(_config(tmp_path), runner=lambda cmd, on_line: 0)
    on = TestClient(create_app(_dataset(), _gaps(), SiloClusteringResult(clusters=[]), generator=gen)).get("/run").text
    assert re.search(r"Generation from the student page.*?on", on, re.S)
