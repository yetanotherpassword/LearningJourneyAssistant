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

# Dashboard (lja/dashboard/) -- read-only against an already-computed
# pipeline run; it never calls the LLM itself (see the module docstring), so
# these just need to point at whatever `python -m lja.cli` was last run
# against.
DASHBOARD_EXCEL_PATH = os.environ.get(
    "LJA_DASHBOARD_EXCEL_PATH", "../data-fixtures/CSE_results_150_students_3_Subjects.xlsx"
)
DASHBOARD_CLUSTERING_CACHE = os.environ.get("LJA_DASHBOARD_CLUSTERING_CACHE", "output/silo_clustering.json")
