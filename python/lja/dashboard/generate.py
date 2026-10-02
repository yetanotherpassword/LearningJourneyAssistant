"""Generate a learning plan or practice quiz from the student page (IOLG-137).

The dashboard's rule (app.py docstring, SMD decision D9) is that a page load
never calls the LLM. This module keeps that rule while adding a button: a
generation is an explicit POST, it runs the *same* command a person would
type -- `python -m lja.plan` or `python -m lja.quiz` with the workbook,
clustering cache and review file this dashboard was started from -- as a
subprocess, and the page re-reads the file the command wrote. There is no
second code path that talks to a model.

Off by default. The dashboard has no login, so the operator must start it
with --allow-generate (or LJA_DASHBOARD_GENERATE=1) before a Generator is
created; without one, create_app() renders no button and the POST route
answers 403.

One job per (student, artefact) at a time. A job records the command, its
output lines (the CLI prints each grounding attempt, which is the only real
progress signal an LLM call offers), the exit code and timings; the page
polls it. The CLI already writes its file only after grounding passes, so a
failed run leaves any previous file untouched.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# What can be generated, and how each maps onto the CLI.
ARTEFACTS: dict[str, dict[str, str]] = {
    "plan": {"module": "lja.plan", "file": "learning_plan_{student_id}.json", "label": "learning plan"},
    "quiz": {"module": "lja.quiz", "file": "quiz_{student_id}.json", "label": "practice quiz"},
}

RUNNING = "running"
DONE = "done"
FAILED = "failed"

# runner(command, on_line) -> exit code. Tests inject one; the default runs
# the command and streams its combined output line by line.
Runner = Callable[[list[str], Callable[[str], None]], int]


def subprocess_runner(command: list[str], on_line: Callable[[str], None]) -> int:
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        on_line(line.rstrip("\n"))
    return proc.wait()


@dataclass
class GenerateConfig:
    """The inputs this dashboard was started from: the same ones the
    Provenance page shows, so a generated artefact is drawn from exactly the
    run being displayed."""

    excel_path: str
    clustering_cache: str
    review_file: str | None
    plans_dir: Path
    quizzes_dir: Path
    python: str = sys.executable


@dataclass
class Job:
    kind: str
    student_id: str
    command: list[str]
    state: str = RUNNING
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    returncode: int | None = None
    lines: list[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "student_id": self.student_id,
            "state": self.state,
            "elapsed": round(self.elapsed, 1),
            "returncode": self.returncode,
            "command": " ".join(self.command),
            "lines": self.lines[-40:],
        }


class Generator:
    def __init__(self, config: GenerateConfig, runner: Runner = subprocess_runner) -> None:
        self.config = config
        self.runner = runner
        self._jobs: dict[tuple[str, str], Job] = {}
        self._lock = threading.Lock()

    def command(self, kind: str, student_id: str) -> list[str]:
        spec = ARTEFACTS[kind]
        out_dir = self.config.plans_dir if kind == "plan" else self.config.quizzes_dir
        # -u: the child's stdout is a pipe, so without it Python block-buffers
        # and the attempt lines arrive only at exit, which defeats the progress view.
        cmd = [
            self.config.python, "-u", "-m", spec["module"],
            self.config.excel_path, student_id,
            "--clustering-cache", self.config.clustering_cache,
            "--out-dir", str(out_dir),
        ]
        if self.config.review_file:
            cmd += ["--review-file", self.config.review_file]
        return cmd

    def output_path(self, kind: str, student_id: str) -> Path:
        out_dir = self.config.plans_dir if kind == "plan" else self.config.quizzes_dir
        return out_dir / ARTEFACTS[kind]["file"].format(student_id=student_id)

    def status(self, kind: str, student_id: str) -> Job | None:
        return self._jobs.get((kind, student_id))

    def start(self, kind: str, student_id: str) -> Job:
        """Begin a job, or raise RuntimeError if one is already running for
        this student and artefact."""
        if kind not in ARTEFACTS:
            raise KeyError(kind)
        with self._lock:
            current = self._jobs.get((kind, student_id))
            if current is not None and current.state == RUNNING:
                raise RuntimeError("already running")
            job = Job(kind=kind, student_id=student_id, command=self.command(kind, student_id))
            self._jobs[(kind, student_id)] = job

        def run() -> None:
            try:
                code = self.runner(job.command, job.lines.append)
            except Exception as exc:  # noqa: BLE001 -- the page shows the failure; nothing else can
                job.lines.append(f"error: {exc}")
                code = -1
            job.returncode = code
            job.finished = time.monotonic()
            job.state = DONE if code == 0 and self.output_path(kind, student_id).exists() else FAILED

        threading.Thread(target=run, name=f"generate-{kind}-{student_id}", daemon=True).start()
        return job
