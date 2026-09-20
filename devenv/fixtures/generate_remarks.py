"""Regenerate the marker remarks baked into mark_rubric_fixture.php (IOLG-56).

The rubric fixture needs one free-text remark per (student, criterion) filling.
Hand-written remarks satisfy the ticket, but generating plausible criterion-level
feedback with an LLM is an explicitly legitimate use here (see devenv/README.md's
"Synthetic data" note) and gives the parsing engine more realistic, varied text.

This is a ONE-TIME dev tool, not part of the replay path: it prints a ready-to-
paste PHP `$REMARKS = [...]` block, which is committed into mark_rubric_fixture.php
so reload_fixture.sh stays deterministic and offline (no LLM call at reload time).

It goes through the project's own provider-agnostic LLM layer (lja.llm) with a
validated Pydantic schema -- the same discipline as lja/data/synth_generator.py --
so it honours whatever backend .env selects (defaults to the local qwen3-vl:30b
over Ollama). Every generated remark is grounded in the criterion text and the
awarded level; if the model omits a cell we fall back to the current wording so a
flaky call can never leave a filling without a remark.

Run from the python/ directory so .env and the lja package resolve:

    cd python && python ../devenv/fixtures/generate_remarks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

# Make the lja package importable when run from anywhere.
_PYTHON_DIR = Path(__file__).resolve().parents[2] / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from lja.llm.factory import get_llm_client  # noqa: E402

# -----------------------------------------------------------------------------
# The fixture definition. These MUST stay identical to $CRITERIA / $LEVELS /
# $SCORES in mark_rubric_fixture.php -- the remarks are generated to match the
# level each student was awarded on each criterion, so a drift here would print
# feedback that contradicts the marks.
# -----------------------------------------------------------------------------

CRITERIA = [
    "Problem decomposition and algorithm design",
    "Correct implementation and testing",
    "Code quality and documentation",
]

# score => descriptor. Max score is the top key.
LEVELS = {
    0: "Not demonstrated",
    1: "Developing",
    2: "Proficient",
    3: "Exemplary",
}
MAX_SCORE = max(LEVELS)

# [student_index][criterion_index] -> score. Five students, three criteria.
SCORES = [
    [3, 3, 2],
    [2, 1, 2],
    [1, 0, 1],
    [2, 2, 3],
    [0, 1, 1],
]

# Used verbatim if the model omits a cell -- a remark is a Query 2 output column,
# so no filling may ever be left without one.
FALLBACK_REMARKS = [
    [
        "Clear breakdown of the problem into well-chosen sub-steps.",
        "All test cases pass and edge cases are handled thoughtfully.",
        "Readable, but a few functions would benefit from doc comments.",
    ],
    [
        "Decomposition is sound; some steps could be split further.",
        "Core logic works but two boundary cases fail — revisit input validation.",
        "Naming is consistent and the layout is easy to follow.",
    ],
    [
        "The overall approach is unclear; plan the algorithm before coding.",
        "Implementation does not yet produce correct output on the samples.",
        "Formatting is inconsistent; run the formatter and add comments.",
    ],
    [
        "Good decomposition, though one sub-problem is solved twice.",
        "Correct on all provided cases; add a couple of your own tests.",
        "Excellent documentation — clear docstrings and inline rationale.",
    ],
    [
        "Little evidence of decomposition; the solution is one long block.",
        "Partially working — the main loop terminates early on empty input.",
        "Some comments present but variable names are hard to follow.",
    ],
]


class Remark(BaseModel):
    student_index: int
    criterion_index: int
    remark: str


class RemarkSet(BaseModel):
    remarks: list[Remark]


_SYSTEM_PROMPT = """You are writing marker remarks for a first-year university programming \
assignment. This is SYNTHETIC test data for a learning-analytics fixture -- not feedback for a \
real student -- but each remark must read like a genuine marker comment a tutor would leave against \
one rubric criterion.

You will be given a list of cells. Each cell names a rubric CRITERION and the LEVEL the student was \
awarded on it (e.g. "Not demonstrated", "Developing", "Proficient", "Exemplary", with a score out \
of a maximum). For every cell, write ONE remark that:

- clearly matches the awarded level -- an "Exemplary" remark is warmly positive, a "Not \
  demonstrated" remark is honest about the work being absent or incorrect, and the middle levels \
  are proportionate and constructive;
- speaks only to that one criterion (decomposition/algorithm design, implementation/testing, or \
  code quality/documentation) -- do not comment on the other criteria;
- is 1-2 sentences, professional and specific, in Australian university marking tone;
- differs in structure and vocabulary from the other remarks -- they must NOT read like \
  synonym-swapped copies of one another.

Return one remark per cell, echoing back its student_index and criterion_index so each remark maps \
to the right filling. Do not invent a student's name or reference material outside the criterion.
"""


def _build_user_prompt() -> str:
    lines = [
        "Write one remark for each of the following cells. Match the awarded level exactly.",
        "",
    ]
    for si, row in enumerate(SCORES):
        for ci, score in enumerate(row):
            lines.append(
                f"- student_index={si}, criterion_index={ci}: "
                f'criterion="{CRITERIA[ci]}", '
                f'awarded level="{LEVELS[score]}" (score {score} of {MAX_SCORE})'
            )
    return "\n".join(lines)


def _php_escape(text: str) -> str:
    # Single-quoted PHP strings only need ' and \ escaped.
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _emit_php(grid: list[list[str]]) -> str:
    out = [
        "$REMARKS = [",
    ]
    for si, row in enumerate(grid):
        out.append("    [")
        for ci, remark in enumerate(row):
            out.append(
                f"        '{_php_escape(remark)}',"
                f"  // {LEVELS[SCORES[si][ci]]}: {CRITERIA[ci]}"
            )
        out.append("    ],")
    out.append("];")
    return "\n".join(out)


def main() -> int:
    client = get_llm_client()
    print(f"LLM: {client.describe()}", file=sys.stderr)

    grid = [list(row) for row in FALLBACK_REMARKS]  # start from the safe default
    used_fallback: list[tuple[int, int]] = []

    try:
        result = client.complete_structured(
            system=_SYSTEM_PROMPT, user=_build_user_prompt(), schema=RemarkSet
        )
        for r in result.remarks:
            if 0 <= r.student_index < len(SCORES) and 0 <= r.criterion_index < len(CRITERIA):
                text = r.remark.strip()
                if text:
                    grid[r.student_index][r.criterion_index] = text
        print(f"Model returned {len(result.remarks)} remarks.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 -- a bad call must not silently corrupt output
        print(f"LLM call failed ({exc}); using fallback remarks for all cells.", file=sys.stderr)

    # Report any cell that ended up on the fallback so the operator can re-run.
    for si, row in enumerate(SCORES):
        for ci in range(len(row)):
            if grid[si][ci] == FALLBACK_REMARKS[si][ci]:
                used_fallback.append((si, ci))
    if used_fallback:
        print(
            f"Note: {len(used_fallback)} cell(s) used the fallback remark: {used_fallback}",
            file=sys.stderr,
        )

    print(f"Usage: {client.usage_summary()}", file=sys.stderr)
    print(_emit_php(grid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
