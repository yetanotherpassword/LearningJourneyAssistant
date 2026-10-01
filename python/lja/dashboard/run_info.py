"""Provenance for the run a dashboard is showing.

Collected once in __main__.py and handed to create_app(), so the /run page
can say exactly which command, which files and which cut-offs produced the
numbers on every other page. Nothing here is computed from the gap rows --
it is the *inputs* to them -- and nothing here calls the LLM or writes.

Tests pass a RunInfo built by hand (or none at all), which is why this is a
plain dataclass and why the collector is a separate function rather than
something create_app() does for itself.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RunInfo:
    # The dashboard process as it was started, reconstructed from argv and
    # quoted so it can be pasted back into a shell.
    command: str
    started_at: str
    excel_path: str
    clustering_cache: str
    review_file: str | None
    # Short git hash of the code serving the page, or None outside a checkout.
    code_version: str | None = None
    # Present only when a <workbook>.truth.json sits beside the workbook,
    # i.e. the cohort is synthetic and its generator recorded how it was made.
    generator: dict | None = None
    # Environment variables that shape classification, as the process saw
    # them. Listed even when unset so the reader can see nothing overrode
    # the defaults.
    environment: dict[str, str | None] = field(default_factory=dict)


# Every LJA_GAP_* variable config.py reads. Kept as a tuple here rather than
# scraped from os.environ so an unset variable still appears on the page.
GAP_ENV_VARS: tuple[str, ...] = (
    "LJA_GAP_ABSOLUTE_FLOOR",
    "LJA_GAP_ABSOLUTE_CEILING",
    "LJA_GAP_RELATIVE_GAP_CUTOFF",
    "LJA_GAP_RELATIVE_STRONG_CUTOFF",
    "LJA_GAP_MIN_COMPETENCIES",
    "LJA_GAP_MIN_SPREAD",
    "LJA_GAP_FALLBACK_PROFICIENT",
)


def _git_short_hash(anchor: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _generator_record(excel_path: Path) -> dict | None:
    """seed + params + catalogue from the generator's truth file, if any.

    Only those three keys: the truth file also holds the answer key (which
    student was given which gap), and the dashboard must not read that --
    a page that knows the answers is not a test of the method.
    """
    truth = excel_path.with_suffix("").with_suffix(".truth.json") if excel_path.suffix else None
    if truth is None or not truth.exists():
        return None
    try:
        data = json.loads(truth.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {
        "truth_file": str(truth),
        "catalogue": data.get("catalogue"),
        "seed": data.get("seed"),
        "params": data.get("params") or {},
    }


def collect_run_info(
    *,
    excel_path: str,
    clustering_cache: str,
    review_file: str | None,
    environ: dict[str, str],
    argv: list[str] | None = None,
) -> RunInfo:
    argv = sys.argv if argv is None else argv
    # sys.argv[0] is the module's __main__.py path when run with -m; say
    # what the person typed instead.
    command = " ".join(["python", "-m", "lja.dashboard", *map(shlex.quote, argv[1:])])
    return RunInfo(
        command=command,
        started_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        excel_path=excel_path,
        clustering_cache=clustering_cache,
        review_file=review_file,
        code_version=_git_short_hash(Path(__file__).resolve().parent),
        generator=_generator_record(Path(excel_path)),
        environment={name: environ.get(name) for name in GAP_ENV_VARS},
    )
