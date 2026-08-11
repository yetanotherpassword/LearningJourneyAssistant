# Learning Journey Assistant (LJA)

An AI-powered system that helps La Trobe University students understand their own
learning. LJA builds a dynamic model of each student's academic profile from
assessment results, rubrics, and marker feedback, then identifies knowledge
gaps against subject intended learning outcomes (SILOs), visualises mastery,
and recommends what to study next.

Capstone project for CSE5IDP. Project owner: Scott Mann. No real student data
is used anywhere in this project; all student records are synthetic or
supplied as an anonymised, modelled dataset.

## What it is today

Extraction through gap-detection now runs end-to-end against a real supplied
dataset. The dashboard and the generation features built on top of gap data
(learning plans, quizzes, study strategies) don't exist yet.

| Bundle | Contents | Status |
| --- | --- | --- |
| [devenv/](devenv/) | One-shot Dockerised Moodle 5.2 dev environment (`bootstrap.sh`), shared config, synthetic-data seeding via `tool_generator`, `.mbz` restore path | Working |
| [python/](python/) | `lja/` package: Excel loader, provider-agnostic LLM layer, LLM-driven SILO clustering, gap detection, CLI — plus `moodle_probe.py`, the Web Services spike for the production Moodle path | **Working — 18 passing tests, runs end-to-end against real data** |
| [sql/](sql/) | Read-only extraction queries for the production Moodle path: rubric definitions, per-criterion fills, outcomes/competency attainment, cross-subject gap detection | Written, not yet wired to code — superseded for now by the Excel path below |
| [data-fixtures/](data-fixtures/) | **The real dataset** — 150 students × 3 subjects × 11 assessments, supplied by the project owner. Plus a competency-framework import CSV and a Moodle backup used only to prove the restore mechanics | Real data in hand |
| [docs/](docs/) | Sprint plan, trade show deck | Active |

Key findings from the codebase and from the 2026-08-11 call with the project
owner (see each bundle's README for detail):

- The project owner supplied a ready-extracted Excel workbook instead of raw
  Moodle backups for this phase — three real subjects (`CSE1OOF`, `CSE2ALG`,
  `CSE3CAP`), 150 synthetic students, SILOs, scores, and feedback already
  structured. That's the fast path now; the Moodle Web Services/SQL path
  (`sql/`, `moodle_probe.py`) remains the plan for a live production instance.
- SILO numbering is **local to each subject** — `SILO1` in `CSE1OOF` and
  `SILO1` in `CSE2ALG` describe unrelated things. Finding which SILOs across
  subjects describe the *same* underlying competency, semantically rather
  than by keyword, is the core problem the project owner asked us to solve —
  and it's now implemented and running (`python/lja/model/silo_clustering.py`).
- Local LLM quality on that clustering task varies a lot: an 8B model
  (`gemma4`) collapsed to grouping-by-subject (semantically useless) even
  with a strengthened prompt; a 30B model (`qwen3-vl`) attempted genuine
  cross-subject grouping with real, correct rationale. Neither is
  staff-confirmed — see `python/README.md` for the full finding.
- Rubric **fills** (which level a marker selected per criterion, plus their
  remark) are **not** exposed over Moodle Web Services — only relevant to the
  production Moodle path, since the Excel dataset already carries scored
  results directly.
- DevSecOps is deliberate: least-privilege API tokens, a read-only `lja_reader`
  DB role, never writing to Moodle tables directly, no admin credentials.

## What it is going to become

The MVP is a thin vertical slice, working end-to-end before anything is
polished. The extraction → clustering → gap-detection spine now runs on the
Excel path; the dashboard is the next real gap.

```
data-fixtures/CSE_results_*.xlsx  (real data)  ─┐
                                                  ├─▶ SILO clustering (LLM) ─▶ Gap detection ─▶ LLM layer ─▶ [Dashboard — not built]
Moodle (production path — sql/, moodle_probe.py) ─┘
```

Planned in order (must-haves from the project proposal, sequenced by dependency):

1. ~~**Walking skeleton**~~ — **done for the Excel path**: load → cluster SILOs
   → detect gaps → CSV report, running against real data with 18 passing
   tests. Still missing: a rendered view (currently a CLI + CSV).
2. **Dashboard** — render the gap report; multiple subjects, the four
   dashboard views from the proposal.
3. **Staff confirmation workflow** for the LLM's SILO clustering — right now
   nothing gates an unreviewed clustering from driving a gap report, unlike
   the Moodle path's `confirmed_by_staff` design.
4. **Personalised learning plans & study-strategy recommendations** — LLM
   features grounded in the gap data, never free-associating (a hard constraint
   from the proposal: outputs must be grounded in structured subject data).
5. **Adaptive quiz generation** aligned to identified gaps — last must-have,
   first descope candidate if the schedule slips.
6. Stretch: custom Moodle plugin exposing rubric fills as a web service;
   longitudinal cross-subject tracking; the production Moodle-DB path wired
   up as an alternative to the Excel loader.

Guardrails, from the proposal: AI recommendations never override academic
grading; mastery estimates are formative indicators, not official evaluations;
everything stays local-first (Dockerised, under our control) with cloud
migration explicitly deferred.

## LLM layer: provider-agnostic, and actually built

All AI features go through one internal interface
(`python/lja/llm/base.py::LLMClient`), not direct SDK calls scattered through
the code — `complete_structured(system, user, schema) -> schema instance`,
returning a validated Pydantic object, not free text to be regex-parsed
downstream. Two backends, switchable by `.env`:

| Backend | How | Structured output |
| --- | --- | --- |
| **Claude (Anthropic API)** | Official `anthropic` SDK | Server-enforced via `messages.parse(output_format=...)` |
| **Local / OpenAI-compatible** | Any server speaking the OpenAI chat-completions API — LM Studio, Ollama, llama.cpp | Prompt-embedded JSON Schema + one retry, then a clear error |

```bash
# Provider selection — defaults to openai_compatible so a fresh checkout
# works with zero API key against a local model.
LJA_LLM_PROVIDER=openai_compatible   # or: anthropic

# Anthropic backend
ANTHROPIC_API_KEY=sk-ant-...
LJA_ANTHROPIC_MODEL=claude-opus-4-8   # current highest-quality model

# OpenAI-compatible backend
LJA_OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama; LM Studio default is :1234/v1
LJA_OPENAI_MODEL=gemma4:latest
LJA_OPENAI_API_KEY=not-needed
```

Design rules for the abstraction, confirmed by actually building it:

- One `LLMClient` interface, two implementations. Feature code
  (`silo_clustering.py`) never imports `anthropic` or `openai` directly.
- The Anthropic implementation uses the official SDK's structured-output
  support; the local implementation cannot assume that guarantee exists, so it
  validates and retries instead. We do **not** route Claude through an
  OpenAI-compatibility shim — each backend gets its native client.
- Every clustering/generation call is grounded in structured data and the
  prompt forbids inventing SILOs, subjects, or wording that wasn't supplied
  (anti-hallucination constraint from the proposal) — and a coverage
  validator checks the LLM's response against the input, not just its shape,
  because a live run caught a real model dropping data silently.
- Model choice is per-task: this session ran the whole pipeline for free on a
  local Ollama model; student-facing generation later should use a stronger one.

## Quick start

```bash
# 1. Local Moodle (~10 min first run) — needed for the production path only,
#    not for the Excel pipeline below — see devenv/README.md
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"      # log out and back in
./devenv/bootstrap.sh
./devenv/seed.sh                     # synthetic courses and students

# 2. Python environment — see python/README.md
cd python
conda env create -f environment.yml
conda activate lja
cp .env.example .env                 # fill in LLM settings; Moodle settings optional for now

# 3. Run the actual pipeline against the real dataset
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx
python -m pytest tests/
```

Moodle (production-path devenv) answers on `http://localhost:8081` — see
`devenv/env.sh` for the port default and dev credentials (never reuse them
anywhere).

## Repository layout

```
devenv/          Dockerised Moodle dev environment (production path)
python/          lja/ package: Excel loader, LLM layer, SILO clustering, gap detection, CLI, tests
sql/             Read-only Moodle extraction queries + LJA schema (production path)
data-fixtures/   The real Excel dataset, competency-framework CSV, a backup-restore sample
docs/            Sprint plan and trade show deck
```

## Team & process

Five-person team, 2-week Scrum sprints, sprint reviews demoed to the project
owner from the running system — see `docs/sprint-plan.md` for the full
per-sprint breakdown and workload allocation. MVP target: end of semester
(late October 2026). Descope order if the schedule slips, pre-agreed: quizzes
→ study strategies → learning plans. The extraction → clustering →
gap-detection spine is non-negotiable — it's also the part now already
working.

### AI tool usage

Parts of this codebase were built with AI coding assistance (Claude Code).
Commits that had AI assistance carry a `Co-Authored-By: Claude <noreply@anthropic.com>`
trailer alongside the human author, so it's visible in `git log` which
changes had it and which didn't — consistent with the DevSecOps/transparency
standard the rest of this project holds itself to (least-privilege tokens,
read-only DB roles, no admin credentials — see "Key findings" above).
