"""Central config, read once from the environment (.env in local dev).

Every other module reads settings from here rather than calling os.environ
directly, so there is exactly one place that knows the variable names.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# "anthropic" or "openai_compatible". Defaults to the free/local path so a
# fresh checkout works without an API key -- see python/README.md.
LLM_PROVIDER = os.environ.get("LJA_LLM_PROVIDER", "openai_compatible")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# claude-opus-4-8 is the current highest-quality model; override for a
# cheaper/faster one (e.g. claude-haiku-4-5) once the prompts are stable.
ANTHROPIC_MODEL = os.environ.get("LJA_ANTHROPIC_MODEL", "claude-opus-4-8")

# claude-opus-4-8 rejects temperature/top_p/top_k outright (400) -- they were
# removed from this model family. The actual "how hard should it think" dial
# is effort (low/medium/high/xhigh/max); "" omits it, which the API treats
# as high. Thinking is off by default on this model unless explicitly turned
# on -- see python/README.md before enabling it (slower, costs more, and
# hasn't been tested live against this task).
ANTHROPIC_EFFORT = os.environ.get("LJA_ANTHROPIC_EFFORT", "")
ANTHROPIC_THINKING = os.environ.get("LJA_ANTHROPIC_THINKING", "false").lower() == "true"

# Any server implementing OpenAI's /v1/chat/completions shape: LM Studio
# (default port 1234) or Ollama (default port 11434, note the /v1 suffix).
#
# Model default is deliberately a larger one: live testing of
# silo_clustering.py found an 8B model (gemma4) fails the cross-subject
# clustering task outright (it groups by subject, which is semantically
# useless), while a 30B model (qwen3-vl) produces genuinely correct
# cross-subject reasoning. See python/README.md's "real finding" section
# before downgrading this for speed.
OPENAI_BASE_URL = os.environ.get("LJA_OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_MODEL = os.environ.get("LJA_OPENAI_MODEL", "qwen3-vl:30b")
OPENAI_API_KEY = os.environ.get("LJA_OPENAI_API_KEY", "not-needed")

# Reasoning models (Qwen3.5 and similar) can spend thousands of tokens on
# chain-of-thought before emitting any answer -- confirmed live, see
# openai_compatible_client.py's module docstring. Raise this per-model if a
# clustering call comes back empty with finish_reason=length.
OPENAI_MAX_TOKENS = int(os.environ.get("LJA_OPENAI_MAX_TOKENS", "16000"))

# Standard OpenAI-API sampling temperature -- unlike the Anthropic path,
# local/LM Studio servers actually honour this. Kept low on purpose: SILO
# clustering is a classification/judgement task where we want the model's
# best answer, not creative variation, and a lower temperature has produced
# more consistent coverage in testing. Not a "creativity" knob to turn up.
OPENAI_TEMPERATURE = float(os.environ.get("LJA_OPENAI_TEMPERATURE", "0.2"))

# Gap detection (lja/model/gap_detection.py) -- RELATIVE classification.
#
# The lodged tender, requirement 4, promises gap detection based on the
# variability within an individual student's profile, "rather than raw pass or
# fail thresholds". So the primary signal is how a competency sits against
# that student's OWN median, measured in median-absolute-deviations (MAD).
#
# Two absolute guards remain, because pure relative classification has two
# degenerate cases that are each worse than the absolute logic it replaces:
# a uniformly weak student has almost no within-profile variance and would be
# told they have no gaps, and a uniformly strong student would have their
# merely-very-good competency flagged. See docs/adr/0001-relative-gap-detection.md.
#
# EVERY VALUE BELOW IS A PROPOSAL, NOT A SETTLED NUMBER. Scott confirmed there
# is no institutional "at risk" figure to match, so these are the team's to
# ratify and defend -- see docs/meetings/actions.md, action A-01. They are
# environment variables precisely so that sensitivity-testing them in Sprint 5
# needs no code change.

# The Fail/Pass boundary. Below this is a gap regardless of how the rest of
# the student's profile looks -- this is the guard that stops a uniformly
# weak student being told they have nothing to work on.
GAP_ABSOLUTE_FLOOR = float(os.environ.get("LJA_GAP_ABSOLUTE_FLOOR", "50.0"))

# The Distinction boundary. At or above this is never a gap, however far it
# sits below the student's own median -- the guard that stops a student on 90%
# everywhere having their 85% flagged, which teaches them to distrust the tool.
GAP_ABSOLUTE_CEILING = float(os.environ.get("LJA_GAP_ABSOLUTE_CEILING", "75.0"))

# Relative position, in MAD units, at or below which a competency is a gap.
# -1.0 means "a full median-absolute-deviation below this student's median".
GAP_RELATIVE_GAP_CUTOFF = float(os.environ.get("LJA_GAP_RELATIVE_GAP_CUTOFF", "-1.0"))

# Relative position at or above which a competency counts as proficient.
GAP_RELATIVE_STRONG_CUTOFF = float(os.environ.get("LJA_GAP_RELATIVE_STRONG_CUTOFF", "1.0"))

# Below this many competencies there is no meaningful spread to reason about;
# whatever the statistic says at n=2 or 3, it is noise. Students in the
# supplied dataset carry roughly 4-8, so this excludes only the thin cases.
GAP_MIN_COMPETENCIES = int(os.environ.get("LJA_GAP_MIN_COMPETENCIES", "4"))

# A MAD below this (in percentage points) means the profile is effectively
# flat, and dividing by it would turn rounding noise into a large relative
# position. Fall back to absolute classification instead, and say so.
#
# 1.0 is chosen on a principle -- attainment is reported to one decimal
# place, so a profile whose median deviation is under a whole point is flat
# within the resolution of the figures themselves -- and then checked against
# the supplied dataset rather than the other way round. MEASURED on all 150
# students: MAD min 0.00, Q1 0.52, median 0.90, Q3 1.40, max 3.80. So:
#
#     min_spread 0.5 -> 134/150 students (89%) classified relatively
#     min_spread 1.0 ->  72/150 students (48%)
#     min_spread 2.0 ->  15/150 students (10%)
#
# The first draft of this used 2.0, which made the tender's headline feature
# fire for one student in ten. **Read the caution in the ADR before tuning
# this to fit:** these profiles are near-flat by construction, because each
# competency's attainment is an average over several assessments of a single
# per-student baseline plus independent noise. Real students have genuine
# per-competency strengths, so this spread is probably an artefact of how the
# dataset was generated, and fitting the threshold tightly to it would be
# fitting to the generator. See docs/meetings/actions.md action A-01.
GAP_MIN_SPREAD = float(os.environ.get("LJA_GAP_MIN_SPREAD", "1.0"))

# Used ONLY on the absolute fallback path, between floor and ceiling: at or
# above this is proficient, below it is developing. This is the old
# DEFAULT_HIGH_THRESHOLD, kept because the fallback deliberately reproduces
# the previous behaviour rather than inventing a third set of semantics.
GAP_FALLBACK_PROFICIENT = float(os.environ.get("LJA_GAP_FALLBACK_PROFICIENT", "65.0"))

# Dashboard (lja/dashboard/) -- read-only against an already-computed
# pipeline run; it never calls the LLM itself (see the module docstring), so
# these just need to point at whatever `python -m lja.cli` was last run
# against.
DASHBOARD_EXCEL_PATH = os.environ.get(
    "LJA_DASHBOARD_EXCEL_PATH", "../data-fixtures/CSE_results_150_students_3_Subjects.xlsx"
)
DASHBOARD_CLUSTERING_CACHE = os.environ.get("LJA_DASHBOARD_CLUSTERING_CACHE", "output/silo_clustering.json")
