# Learning Journey Assistant (LJA)

An AI-powered system that helps La Trobe University students understand their own
learning. LJA builds a dynamic model of each student's academic profile from
Moodle data — assessment results, rubrics, and marker feedback — then identifies
knowledge gaps against subject intended learning outcomes (SILOs), visualises
mastery, and recommends what to study next.

Capstone project for CSE5IDP. Project owner: Scott. No real student data is used
anywhere in this project; all student records are synthetic or supplied as an
anonymised, modelled dataset.

## What it is today

This repository is the first draft: the groundwork layers, spike code, and the
architectural decisions that de-risk the build. Nothing user-facing exists yet.

| Bundle | Contents | Status |
| --- | --- | --- |
| [devenv/](devenv/) | One-shot Dockerised Moodle 5.2 dev environment (`bootstrap.sh`), shared config, synthetic-data seeding via `tool_generator` | Working |
| [python/](python/) | `moodle_probe.py` — minimal Moodle Web Services client (token check, course listing, per-student grade items), least-privilege API setup notes | Working spike |
| [sql/](sql/) | Read-only extraction queries: rubric definitions, per-criterion fills, outcomes/competency attainment, cross-subject gap detection; schema for `lja_criterion_silo_map` | Working, thresholds TBC with project owner |
| [data-fixtures/](data-fixtures/) | Moodle competency-framework import CSV using CSE5IDP's own SILOs as a worked example | Working, scale config needs verification |
| [docs/TradeShow/](docs/TradeShow/) | Trade show slide deck | Draft |

Key findings baked into the draft (see each bundle's README for detail):

- Moodle already models outcome attainment twice — legacy **Outcomes** and the
  modern **Competency** subsystem. Whether we build on top of or alongside these
  is a Sprint 1 spike.
- Rubric **fills** (which level a marker selected per criterion, plus their
  remark) are **not** exposed over Moodle Web Services. Since per-criterion
  feedback is the signal gap detection depends on, we read them directly from
  the database for now (read-only role), with a custom web-service plugin as a
  stretch goal.
- DevSecOps is deliberate: least-privilege API tokens, a read-only `lja_reader`
  DB role, never writing to Moodle tables directly, no admin credentials.

## What it is going to become

The MVP is a thin vertical slice, working end-to-end before anything is polished:

```
Moodle (synthetic data)
   │  Web Services API + read-only SQL (rubric fills)
   ▼
Extraction layer (Python)
   ▼
Competency model  ──  criterion → SILO mapping (lja_criterion_silo_map)
   ▼
Gap detection engine  ──  weighted attainment per outcome, isolated vs persistent gaps
   ▼
LLM layer (provider-agnostic — see below)
   ▼
Student dashboard  ──  current understanding, strengths, gaps, progress trends
```

Planned in order (must-haves from the project proposal, sequenced by dependency):

1. **Walking skeleton** — one student, one subject, extraction → mapping → gap
   query → crude dashboard page. End-to-end is mandatory; ugly is fine.
2. **Competency model + dashboard proper** — multiple subjects, the four
   dashboard views, real (supplied) dataset swapped in when it lands.
3. **Personalised learning plans & study-strategy recommendations** — LLM
   features grounded in the gap data, never free-associating (a hard constraint
   from the proposal: outputs must be grounded in structured subject data).
4. **Adaptive quiz generation** aligned to identified gaps — last must-have,
   first descope candidate if the schedule slips.
5. Stretch: custom Moodle plugin exposing rubric fills as a web service;
   longitudinal cross-subject tracking.

Guardrails, from the proposal: AI recommendations never override academic
grading; mastery estimates are formative indicators, not official evaluations;
everything stays local-first (Dockerised, under our control) with cloud
migration explicitly deferred.

## LLM layer: provider-agnostic by design

All AI features (feedback parsing, learning-plan generation, quiz generation,
synthetic rubric-remark generation for the seeder) go through a single internal
interface, not direct SDK calls scattered through the code. Two backends are
supported from day one, switchable by configuration:

| Backend | How | Use case |
| --- | --- | --- |
| **Claude (Anthropic API)** | Official `anthropic` Python SDK | Best quality for generation-heavy features (learning plans, quizzes) |
| **Local / OpenAI-compatible** | Any server speaking the OpenAI chat-completions API — LM Studio, Ollama, llama.cpp | Zero-cost development, offline demos, privacy-conservative deployment |

Configuration lives in `.env` (never committed — see `python/.gitignore`):

```bash
# Provider selection
LJA_LLM_PROVIDER=anthropic          # or: openai_compatible

# Anthropic backend
ANTHROPIC_API_KEY=sk-ant-...
LJA_ANTHROPIC_MODEL=claude-sonnet-5   # claude-opus-4-8 for highest quality,
                                      # claude-haiku-4-5 for cheap bulk tasks

# OpenAI-compatible backend (e.g. LM Studio's local server)
LJA_OPENAI_BASE_URL=http://localhost:1234/v1
LJA_OPENAI_MODEL=your-loaded-model-name
LJA_OPENAI_API_KEY=lm-studio        # LM Studio accepts any non-empty string
```

Design rules for the abstraction:

- One `LLMClient` interface (`complete()`, structured-output helper), two
  implementations. Feature code never imports a vendor SDK directly.
- The Anthropic implementation uses the official `anthropic` SDK; the local
  implementation uses the OpenAI-compatible REST shape. We do **not** route
  Claude through an OpenAI-compatibility shim — each backend gets its native
  client.
- Prompts are grounded: every generation call receives structured gap/rubric
  data and the prompt forbids inventing marks or feedback (anti-hallucination
  constraint from the proposal).
- Model choice is per-task, not global: bulk synthetic-data generation can run
  on a cheap/local model while student-facing plan generation uses a stronger
  one.

## Quick start

```bash
# 1. Local Moodle (~10 min first run) — see devenv/README.md
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"      # log out and back in
./devenv/bootstrap.sh
./devenv/seed.sh                     # synthetic courses and students

# 2. Python environment — see python/README.md
cd python
conda env create -f environment.yml
conda activate lja
cp .env.example .env                 # fill in Moodle URL/token + LLM settings
python moodle_probe.py
```

Moodle answers on `http://localhost:8000` (dev credentials in
[devenv/README.md](devenv/README.md) — never reuse them anywhere).

## Repository layout

```
devenv/          Dockerised Moodle dev environment
python/          Extraction layer + (future) competency model, gap engine, LLM layer
sql/             Read-only Moodle extraction queries + LJA schema
data-fixtures/   Competency framework import fixtures
docs/            Slides and project documents
```

## Team & process

Six-person team, 2-week Scrum sprints, sprint reviews demoed to the project
owner from the running system. MVP target: end of semester (late October 2026).
Descope order if the schedule slips, pre-agreed: quizzes → learning plans →
study strategies. The dashboard + gap detection slice is non-negotiable.
