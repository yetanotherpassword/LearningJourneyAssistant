# LJA — Python bundle

The extraction, semantic-mapping, gap-detection, and LLM layers for the
Learning Journey Assistant.

## Two data paths, same downstream pipeline

The proposal's architecture assumed Moodle would be the data source from day
one. In practice the project owner (Scott Mann) handed over a ready-extracted
Excel workbook on the 2026-08-11 call — `data-fixtures/CSE_results_150_students_3_Subjects.xlsx`,
three subjects, 150 synthetic students, SILOs, assessments, scores and
feedback already structured. That's now the **fast path to a working
pipeline**; the Moodle Web Services / direct-SQL path (`moodle_probe.py`,
`sql/`) remains the **production path** for when the system reads a live
Moodle instance instead of a supplied export. Both feed the same
clustering → gap-detection → LLM stages; only the extraction step differs.

```
data-fixtures/CSE_results_*.xlsx  ──┐
                                     ├──▶ lja.model (clustering [via lja.llm], gaps) ──▶ lja.dashboard
Moodle (moodle_probe.py + sql/)  ──┘
```

## Contents

| Path | Purpose |
| --- | --- |
| `lja/config.py` | Reads `.env`; the one place that knows environment variable names |
| `lja/llm/` | Provider-agnostic LLM client — `AnthropicClient`, `OpenAICompatibleClient`, a factory keyed off `LJA_LLM_PROVIDER` |
| `lja/data/excel_loader.py` | Parses the 3-sheet workbook into typed `Silo` / `Assessment` / `ResultRow` / `StudentSummary` records |
| `lja/data/synth_generator.py` | Generates additional synthetic students — planted, known cross-subject gaps + LLM-varied feedback. `python -m lja.data.synth_generator --help` |
| `lja/model/silo_clustering.py` | LLM-driven cross-subject SILO clustering — the semantic-matching step Scott asked for, with automatic retry on a validation failure |
| `lja/model/gap_detection.py` | Weighted per-student, per-competency attainment + **relative** gap classification — see "Gap detection" below |
| `lja/cli.py` | `python -m lja.cli <xlsx path>` — runs the whole pipeline, writes a gap report |
| `lja/dashboard/` | `python -m lja.dashboard` — read-only web view over an already-computed pipeline run. Never calls the LLM. See "Dashboard" below |
| `tests/` | pytest — 87 tests, all offline (no live LLM call needed) |
| `moodle_probe.py` | Web Services spike — kept for the production Moodle path |
| `environment.yml` | Conda environment: `pandas`, `openpyxl`, `psycopg2`, `anthropic`, `openai`, `pydantic`, `pytest`, `fastapi`, `uvicorn`, `jinja2` |
| `.env.example` | Template for credentials and LLM config. Copy to `.env` and fill in |

## Setup

```bash
conda env create -f environment.yml
conda activate lja
cp .env.example .env             # fill in what you're using — see below
```

Run the Moodle probe (production path spike):

```bash
python moodle_probe.py
```

Run the gap-detection pipeline against Scott's dataset (fast path):

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx
```

Run the tests:

```bash
python -m pytest tests/
```

## Dashboard

Read-only view over an already-computed pipeline run — FastAPI + Jinja2 +
Chart.js, per `docs/sprint-plan.md`'s Sprint 1 recommendation. It never
calls the LLM and never writes anything; it only reads the dataset plus
whatever clustering `python -m lja.cli` already cached.

```bash
cd python
conda activate lja
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --refresh-clustering   # once, if you haven't already
python -m lja.dashboard
```

Then open http://127.0.0.1:8000/ — a student list (with persistent- and
isolated-gap counts per row) linking to a per-student page: an attainment
chart plus a classification-badged gap table, both colored from the same
semantic palette (`lja/dashboard/static/style.css`) so the chart and the
badges never disagree about what a color means. `--port` and `--host` are
both flags on `python -m lja.dashboard`; neither has an `LJA_*` environment
variable yet.

**Cohorts.** Each figure in the stat strip links to `/cohort/<key>` — the
same student table and statistics over just that subset, with a sentence
stating what put those students in it. Cohorts are registered in
`_COHORTS` in `app.py`, so adding one is a registry entry rather than a new
route and a new template. Two exist today: `all` and `persistent-gap`.

> **No "At Risk" cohort yet, and that is a decision.** The Sprint 3 runbook
> (§9) lists the at-risk threshold as a stop-and-ask: the project owner
> confirmed there is no institutional "at risk" number to match, so the
> definition is the team's to choose and defend, and it is due at WP2
> planning alongside the relative-gap thresholds it will most likely be
> expressed in terms of. `/cohort/at-risk` returns 404 until then, and
> `test_at_risk_cohort_is_not_registered_yet` asserts that absence so the
> decision cannot be made silently by whoever adds the tile.

**Statistics.** Mean, median, population variance and standard deviation,
min/max and quartiles over each student's average total, plus a
distribution histogram and a competency-classification breakdown. The
arithmetic lives in `lja/dashboard/stats.py` as pure functions over lists of
floats, tested independently in `tests/test_dashboard_stats.py` with the
working shown in each test's docstring. These are *population* statistics,
not sample statistics — a cohort is every student it describes, not a
sample drawn from a larger body.

**Sorting.** Every column heading on those tables sorts, ascending then
descending. That is client-side progressive enhancement
(`lja/dashboard/static/sort.js`): the server always renders rows in student-id
order, so the table is still correct with JavaScript disabled. Cells carry a
`data-sort-value` with the raw figure, because sorting the *rendered* text
would order "100.0%" before "20.0%".

If `output/silo_clustering.json` doesn't exist yet, `python -m lja.dashboard`
fails fast with the exact `lja.cli` command to run first, rather than
silently trying to call the LLM itself — the dashboard should never be the
thing that triggers a billed API call.

`create_app(dataset, gaps, clustering)` in `lja/dashboard/app.py` is a factory that
takes data as arguments instead of loading it itself; `lja/dashboard/__main__.py`
is the only place that touches disk (the Excel file and the clustering
cache). `tests/test_dashboard.py` builds tiny in-memory `LjaDataset` /
`CompetencyGap` fixtures and drives the app via FastAPI's `TestClient` — no
real Excel file, no LLM, no dependency on whatever happens to be in
`output/` when the tests run.

**Known caveat, flagged rather than silently accepted:** the chart loads
Chart.js from a CDN (`lja/dashboard/templates/base.html`), which needs
internet access. Everything else on the page — tables, badges, the student
list — still works if that request fails; only the chart itself won't
render. Vendor `chart.js` into `lja/dashboard/static/` if this needs to run
fully offline, matching the rest of the project's local-first stance (the
whole point of the Ollama path).

**Not yet built:** a `confirmed_by_staff` review action on this page — see
"Not yet written" below. For now this dashboard is read-only, matching
Sprint 2's scope in `docs/sprint-plan.md`; the natural place for that
action is a "confirm" control on each competency once it exists.

## Gap detection — relative, not absolute

A competency is judged against **the variability within that student's own profile**, not against
a fixed pass mark. That is what the lodged tender's requirement 4 promises, explicitly "rather
than raw pass or fail thresholds". The previous absolute 50/65 classification was the mechanism
the tender excludes.

For each student, their competency attainments form a profile. Position is measured as
`(attainment − profile median) / profile MAD`, in median-absolute-deviation units. Median and MAD
rather than mean and standard deviation because students carry roughly 4–8 competencies, and at
that n one catastrophic result drags the mean far enough to hide everything else.

Two absolute guards remain, because pure relative logic has two degenerate cases that are each
*worse* than what it replaces — a uniformly weak student would be told they have no gaps, and a
uniformly strong student would have their merely-very-good competency flagged. The **floor**
catches the first, the **ceiling** the second, and both are checked before anything relative.

Where a profile is too short or too flat to reason about, classification falls back to absolute
**and records that it did**. Every gap carries `classification_basis` — one of `relative position`,
`absolute floor`, `absolute ceiling`, `insufficient data` — plus `relative_position` when the
relative path was taken. Both appear in the gap report CSV and on the student page, because tender
requirement 5 asks that a displayed figure be traceable, and a verdict with no visible basis is not.

`subjects_evidencing >= 2` still separates a persistent gap from an isolated one. That distinction
is orthogonal to how the gap was detected and Sprint 5's study-strategy generation depends on it.

### Tuning

Seven `LJA_GAP_*` environment variables in `lja/config.py` — the single source of truth, with no
numeric literals anywhere in `gap_detection.py`. `python -m lja.cli` exposes all six of the
classification tunables as flags (`--absolute-floor`, `--relative-gap-cutoff`, `--min-spread`, …)
so Sprint 5 can sweep them without editing a `.env` between runs. See `.env.example`.

> **The defaults are proposals, not settled numbers.** Scott confirmed there is no institutional
> "at risk" figure to match, so they are the team's to ratify and defend — action **A-01** in
> `docs/meetings/actions.md`. Read
> [`docs/adr/0001-relative-gap-detection.md`](../docs/adr/0001-relative-gap-detection.md) before
> changing any of them: it records a measurement showing the supplied dataset's profiles are
> nearly flat (median MAD 0.90 percentage points), that a quarter of relative gaps sit under two
> points below the student's own median, and why tuning `MIN_SPREAD` down to make more gaps appear
> would be fitting to an artefact of how the data was generated.

**`sql/moodle_attainment_extraction.sql` Query 6 still carries the legacy 50/65** and is annotated
as divergent. Running it and running `lja.cli` on the same data will disagree. That is expected
until Sprint 4 reconciles them — the Moodle path is not wired to code yet, and porting an
unratified algorithm would mean maintaining two copies of a moving target.

## The LLM layer — provider-agnostic, actually built now

One interface, `lja.llm.LLMClient`, with a single method:
`complete_structured(system, user, schema) -> schema instance`. Feature code
(`silo_clustering.py`) never imports `anthropic` or `openai` directly — it
imports `LLMClient` and calls `get_llm_client()`. Two implementations:

| Backend | Client | How structured output is enforced |
| --- | --- | --- |
| `AnthropicClient` | Official `anthropic` SDK, `messages.create(output_config={"format": ..., "effort": ...})` | Server-side — the API guarantees the schema |
| `OpenAICompatibleClient` | `openai` SDK pointed at a custom `base_url` — LM Studio, Ollama, llama.cpp | Prompt-embedded JSON Schema, tried as `response_format: json_schema` → `json_object` → plain text (servers disagree on what they support — confirmed live, see below), then a validated `RuntimeError` |

Switch with `.env`:

```bash
LJA_LLM_PROVIDER=openai_compatible        # or: anthropic

ANTHROPIC_API_KEY=sk-ant-...
LJA_ANTHROPIC_MODEL=claude-opus-4-8       # current highest-quality model
LJA_ANTHROPIC_EFFORT=                     # low|medium|high|xhigh|max, empty = API default ("high")
LJA_ANTHROPIC_THINKING=false              # true enables adaptive thinking

LJA_OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama; LM Studio default is :1234/v1
LJA_OPENAI_MODEL=qwen3-vl:30b                    # see the finding below before changing this
LJA_OPENAI_API_KEY=not-needed
LJA_OPENAI_MAX_TOKENS=16000                      # raise if a reasoning model returns empty content
LJA_OPENAI_TEMPERATURE=0.2                       # low on purpose -- see "Tuning the LLM" below
```

Default is `openai_compatible` so a fresh checkout with no API key still
works against a local model.

## Tuning the LLM

Three separate things people usually mean by "tweak the LLM," and this
codebase handles them differently:

**1. The prompt.** There is one, already in the repo, already iterated on
against real failures this session (see the finding below) —
`_SYSTEM_PROMPT` in [`lja/model/silo_clustering.py`](lja/model/silo_clustering.py).
Edit it directly for a permanent change. For a one-off experiment without
touching the file, `cluster_silos()` takes an `extra_instructions` string
appended to the end of the prompt, exposed on the CLI:

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx \
    --refresh-clustering \
    --extra-instructions "Prefer fewer, broader competency groups over many narrow ones."
```

(`synth_generator.py` has its own `_FEEDBACK_SYSTEM_PROMPT` for the feedback
template bank — same idea, different file, no CLI flag yet since it's used
far less often.)

**2. Temperature / creativity — provider-dependent, not a single knob.**
This is the one with a real gotcha: the two backends don't support the same
controls, because Anthropic actually **removed** `temperature`/`top_p`/`top_k`
from this model family — sending any of them to `claude-opus-4-8` is a 400
error, not a no-op. So:

| Backend | Temperature knob | What actually controls depth/quality |
| --- | --- | --- |
| `OpenAICompatibleClient` (Ollama, LM Studio) | `LJA_OPENAI_TEMPERATURE`, real standard OpenAI-API sampling temperature, honoured by the local server | — |
| `AnthropicClient` (`claude-opus-4-8`) | **Not supported — the API rejects it.** | `LJA_ANTHROPIC_EFFORT` (`low`/`medium`/`high`/`xhigh`/`max`) + `LJA_ANTHROPIC_THINKING` (adaptive thinking on/off) |

`LJA_OPENAI_TEMPERATURE` defaults to `0.2`, deliberately low. SILO
clustering is a classification/judgement task where we want the model's
single best answer, not creative variety across runs — a high temperature
here would make the already-observed run-to-run coverage variance (see the
finding below, point 5) worse, not better. There's been no live A/B test of
different temperature values against this task yet; `0.2` is a reasoned
starting point, not a measured optimum — worth revisiting if clustering
quality on the local-model path is still inconsistent after a temperature
sweep.

For the Anthropic path, `effort` is the closest equivalent lever: `high`
(the API's own default, same as leaving `LJA_ANTHROPIC_EFFORT` empty) is
probably the right starting point for this task; `xhigh` or `max` cost more
and haven't been tested against SILO clustering specifically. Neither the
effort nor the thinking wiring has been exercised against a live Anthropic
call in this repo yet — there's no `ANTHROPIC_API_KEY` configured in this
dev environment, only the local Ollama path has actually been run — so
treat both as implemented-and-unit-tested, not validated end to end.

**3. Other request options.** `LJA_OPENAI_MAX_TOKENS` / the Anthropic
client's fixed `max_tokens=16000` already exist and are covered above (see
the reasoning-model empty-content finding). `LJA_ANTHROPIC_THINKING=true`
turns on adaptive thinking, which lets the model reason before answering —
worth trying if clustering quality on the Anthropic path needs a boost, at
the cost of extra latency and tokens.

## Local LLM setup — Ollama (recommended path for the team)

The only model that has actually produced correct cross-subject SILO
clustering in testing so far (see the finding below) is `qwen3-vl:30b` run
through Ollama. Setup, Linux:

```bash
# 1. Install (official installer; sets up a systemd service on Linux)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Confirm it's running
systemctl is-active ollama        # should print "active"
# or, if you'd rather not use the systemd service:
ollama serve &

# 3. Pull the model that's confirmed to work -- ~19 GB download
ollama pull qwen3-vl:30b

# 4. Verify it's there and reachable
ollama list
curl -s http://localhost:11434/v1/models | grep qwen3-vl
```

Point `python/.env` at it (this is already the code default, so an empty
`.env` works too):

```bash
LJA_OPENAI_BASE_URL=http://localhost:11434/v1
LJA_OPENAI_MODEL=qwen3-vl:30b
```

Then run the pipeline as normal:

```bash
cd python
conda activate lja
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --refresh-clustering
```

`--refresh-clustering` forces a fresh LLM call; omit it on later runs to
reuse the cached result in `output/silo_clustering.json` at zero cost.

**Hardware:** 19 GB on disk for the model weights alone; budget enough
RAM (CPU inference) or VRAM (GPU) on top of that to actually load it, or
expect it to be slow. If your machine can't run a 30B model, `LM Studio`
pointed at a teammate's machine on the LAN works identically — just change
`LJA_OPENAI_BASE_URL` to `http://<their-ip>:1234/v1`, as done for the
qwen3.5-35b-a3b test below. Nothing else in the code needs to change either
way; that's the point of the provider abstraction.

### A real finding, not a hypothetical one: local-model quality varies a lot on this task

Three live runs against Ollama, same dataset, same code, different models
and prompt versions:

1. **`gemma4:latest` (8B)** — grouped SILOs **by subject**, i.e. did nothing
   semantic at all, even after the prompt was strengthened with an explicit
   worked example and an instruction that single-subject clusters are a sign
   of failure. Exactly the failure mode Scott warned against on the call.
2. **`qwen3-vl:30b`, first attempt** — genuinely attempted cross-subject
   grouping, but silently dropped 3 of the 13 SILOs. Caught by
   `silo_clustering.py`'s `_validate_coverage()` before it could reach
   `gap_detection.py` and corrupt an average — this is exactly why that
   check exists rather than trusting the schema validation alone.
3. **`qwen3-vl:30b`, after fixing a real prompt ambiguity** (flagging a SILO
   as poorly-worded had been read as "instead of" clustering it, not "as well
   as" — the model was leaving `CSE2ALG:SILO1` out of every cluster because
   it had flagged that one) — **full coverage, 7 competency groups from 13
   SILOs, genuine cross-subject reasoning**: e.g. it linked `CSE1OOF:SILO2`
   ("abstract data types and encapsulation") with `CSE2ALG:SILO2`/`SILO3`
   ("identifying/implementing data structures") into one "Data Structures
   Knowledge and Application" competency — the same shape of link Scott gave
   as his own worked example on the call. Running gap detection on top of it
   found **6 students with a genuine persistent gap in that competency**,
   evidenced across both subjects, 40–50% attainment. `CSE2ALG:SILO1`
   ("overall objectives...") was correctly flagged as vague wording *and*
   still given its own cluster, once the prompt no longer treated those as
   mutually exclusive.

4. **`qwen/qwen3.5-35b-a3b`** (a 35B MoE model, ~3B active params, run
   locally on remote LM Studio hardware) — surfaced two real infrastructure
   bugs first: this server rejects `response_format: json_object` outright
   (LM Studio here only accepts `json_schema` or `text`), and as a
   hybrid-reasoning model it silently burned its entire token budget on
   chain-of-thought and returned empty content (`finish_reason: length`)
   until `max_tokens` was set explicitly. Both are now handled generally
   (`openai_compatible_client.py` tries three `response_format` strategies
   in order; `max_tokens` defaults to 16000 and is configurable via
   `LJA_OPENAI_MAX_TOKENS`) with regression tests, not just patched for this
   one model. Once those were fixed, the actual clustering **collapsed back
   to one cluster per subject** — the same failure mode as `gemma4`, despite
   comparable headline size to the successful `qwen3-vl:30b` run. Worth
   noting: its SILO-flagging was good (4 flagged, reasonable critiques,
   better coverage than `qwen3-vl`'s single flag) — the weakness is
   specifically the cross-subject grouping instruction, not the model
   overall. Bigger parameter count did not predict quality here; the MoE
   architecture (fewer active parameters per token than a dense model) may
   be part of why.

5. **`qwen3-vl:30b`, a later re-run, same prompt** — dropped 3 SILOs again,
   but a **different 3** than run #2's failure. Same model, same code, same
   prompt, different sample. That rules out "bad prompt" or "bad model" as
   the sole explanation — it's run-to-run sampling variance on a task this
   nuanced, and it means even a model confirmed good (run #3, point 4 above)
   can still fail occasionally. `cluster_silos()` now retries automatically
   on a coverage-validation failure (default 3 attempts, `max_attempts=`
   overridable), feeding the specific validation error back into the next
   attempt's prompt rather than blindly resending the same request — see
   `silo_clustering.py` and its retry tests in
   `tests/test_silo_clustering.py`.

Takeaway for the team: **treat the clustering output as `mapped_by='llm'`,
`confirmed_by_staff=False`**, exactly like an unconfirmed row in
`lja_criterion_silo_map` — the CLI prints this warning after every run and
writes the result to a cache file precisely so it's reviewable, not because
LLM output is being trusted blindly, even when (as above) a specific run
turns out to be good. This also validates the multi-backend design: cheap
local models are fine for iterating on the pipeline's plumbing, but the
model and the prompt both matter for this specific semantic task, and even
a good model needs the retry-on-validation-failure loop, because single-shot
LLM sampling is not reliable enough on its own here to skip it.

## Generating more synthetic data

`lja/data/synth_generator.py` extends the supplied workbook with more
students, in the same shape, ready to run through `lja.cli` unchanged.
Two things it does deliberately, not just "add noise":

1. **A configurable fraction of new students get a planted, known gap.**
   Their scores are genuinely suppressed on a chosen set of SILOs spanning
   two subjects; everything else about them is normal. This gives ground
   truth — after generating, running the real pipeline and checking whether
   `compute_gaps()` flags exactly those students as a persistent gap in the
   competency those SILOs cluster into is a real correctness check on the
   whole system, not just "did it run without crashing."
2. **Feedback text comes from an LLM-generated template bank** (one call
   for ~24 varied templates, not one call per row), sampled per row and
   filled in with that row's actual SILO text. Directly answers what Scott
   called out as a real limitation of the supplied data on the
   2026-08-11 call — only 45 unique feedback strings across 1650 rows.

```bash
python -m lja.data.synth_generator \
    ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx \
    --add 150 \
    --out ../data-fixtures/CSE_results_300_students_3_Subjects_synthetic.xlsx \
    --seed 42
```

Prints the planted-gap student IDs at the end — that's the ground truth to
check the pipeline against:

```bash
python -m lja.cli ../data-fixtures/CSE_results_300_students_3_Subjects_synthetic.xlsx --refresh-clustering
grep "persistent gap" output/gap_report.csv | cut -d, -f1 | sort -u
# compare against the planted IDs the generator printed
```

Default planted-gap SILOs are `CSE1OOF:SILO2`, `CSE2ALG:SILO2`,
`CSE2ALG:SILO3` — the one cross-subject link the clustering has found
correctly and repeatably (see the finding above, points 3 and 5).
Override with `--planted-gap-silos` / `--planted-gap-fraction` for a
different ground truth, or `--no-llm-feedback` to skip the LLM call
entirely (uses a small built-in template per band instead — useful for a
fast, fully offline test run).

## Enabling the Web Services API on the Moodle instance (production path)

1. Site administration → Advanced features → tick **Enable web services**.
2. Site administration → Server → Web services → **Manage protocols** → enable
   **REST**.
3. Server → Web services → **External services** → add a service containing only
   the functions we need, with "Authorised users only" ticked.
4. Create a service account and a role carrying just the required capabilities
   (`moodle/grade:viewall`, `gradereport/user:view`,
   `moodle/user:viewalldetails`), assigned at system level.
5. **Manage tokens** → generate a token scoped to that user and service.

Least privilege is deliberate. We do not use the admin token, and we should be
able to say so at the final presentation — Scott has been explicit about
DevSecOps being a differentiator.

## Functions the extraction layer relies on

| Purpose | Function |
| --- | --- |
| Verify token, enumerate available functions | `core_webservice_get_site_info` |
| Subjects and their structure | `core_course_get_courses`, `core_course_get_contents` |
| Enrolled students in a subject | `core_enrol_get_enrolled_users` |
| Per-student grade items plus feedback | `gradereport_user_get_grade_items` |
| Assignment metadata and marks | `mod_assign_get_assignments`, `mod_assign_get_grades` |
| Quiz attempts | `mod_quiz_get_user_attempts` |
| Rubric definitions (criteria and levels) | `core_grading_get_definitions` |
| Activity completion | `core_completion_get_activities_completion_status` |
| Competencies and user proficiency | the `core_competency_*` family |

Do not treat that table as final. The instance publishes its own version-exact
reference with full parameter and return schemas at **Site administration →
Server → Web services → API Documentation**. Read it there; the function set
changes between releases.

## The known coverage gap (production path only)

Rubric **definitions** are exposed over web services. Rubric **fills** — which
level was selected on which criterion for which student, plus the marker's
per-criterion remark — are not. See `sql/README.md` for the direct-SQL path
that exists because of this gap.

This doesn't affect the Excel path above — Scott's workbook already carries
scored, feedback-attached results per student per assessment, so there's no
rubric-fill extraction step to perform there.

## Design decision flagged for the project owner

`gap_detection.py` treats one assessment's overall score as full evidence
for **every** SILO it addresses, weighted only by the assessment's own
`Weight` — it does not split the score across SILOs when an assessment maps
to several at once. Reasonable default, but worth confirming with Scott
before it drives a real intervention: see the module's docstring.

## Not yet written

- Staff confirmation workflow for the LLM's SILO clustering (the
  `confirmed_by_staff` gate that exists conceptually in `sql/`'s
  `lja_criterion_silo_map` has no equivalent here yet — right now nothing
  stops an unreviewed clustering from being used). Per `docs/sprint-plan.md`
  (M2, Sprint 3), MVP scope is a CLI/admin script, not a full UI — and the
  gate should be advisory (three states: pending/confirmed/rejected), not a
  hard block on the pipeline; a `rejected` cluster still needs a real
  rework path (`--extra-instructions` + `--refresh-clustering`, or a manual
  override), not a silent dead end.
- Confirmation UI on the dashboard (see "Dashboard" above) — deferred until
  the CLI/admin version above exists.
- Reload-on-change for `python -m lja.dashboard` — restart the process to
  pick up template/CSS edits; wiring `uvicorn`'s `--reload` through the
  `create_app()` factory pattern is more machinery than this slice needed.
- Loader that populates `lja_criterion_score` for the **Moodle** path (the
  Excel path has its own loader — `lja/data/excel_loader.py` — already done).
- Synthetic data seeder for the Moodle path — see the devenv bundle.
- Learning-plan / quiz / study-strategy generation — `cluster_silos()` is the
  first LLM feature built; those are next.
