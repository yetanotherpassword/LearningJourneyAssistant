# LJA — Python bundle

The extraction, semantic-mapping, gap-detection, and LLM layers for the
Learning Journey Assistant.

## Two data paths, same downstream pipeline

The proposal's architecture assumed Moodle would be the data source from day
one. In practice the project owner (Scott Mann) handed over a ready-extracted
Excel workbook on the 2026-08-11 call — `data-fixtures/CSE_results_150_students_3_Subjects.xlsx`,
three subjects, 150 synthetic students, SILOs, assessments, scores and
feedback already structured. That's the **fast path to a working
pipeline**; the direct-SQL Moodle path is the **production path** for when the
system reads a live Moodle instance instead of a supplied export. Both feed the
same clustering → gap-detection → LLM stages; only the extraction step differs,
and both produce the identical `LjaDataset` type the downstream code consumes.

As of IOLG-104 the Moodle path is wired end to end for a seeded subject:
`lja/data/moodle_loader.py` runs Query 2 from `sql/moodle_attainment_extraction.sql`
(prefix-substituted via `lja/data/sql.py`, IOLG-105) against a read-only
connection, joins each rubric criterion to a SILO through the staff-editable
`data-fixtures/criterion_silo_map_*.csv` (IOLG-56), and returns the same
`LjaDataset` the Excel loader does. Select the source on the CLI:

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx   # --source excel (default)
python -m lja.cli --source moodle                                            # reads config.MOODLE_DB
```

```
data-fixtures/CSE_results_*.xlsx  ──▶ excel_loader   ──┐
                                                        ├──▶ LjaDataset ──▶ lja.model (clustering [via lja.llm], gaps) ──▶ lja.dashboard
Moodle DB (sql/ Query 2 + mapping CSV) ──▶ moodle_loader ──┘
```

The `--source moodle` run above produced clusters and a gap report for the
seeded CSE1IOI subject with **no change** to `silo_clustering.py` or
`gap_detection.py` — the `LjaDataset` abstraction held, which was the point of
the vertical slice. See "Running against Moodle" below for the connection
setup.

## Contents

| Path | Purpose |
| --- | --- |
| `lja/config.py` | Reads `.env`; the one place that knows environment variable names |
| `lja/llm/` | Provider-agnostic LLM client — `AnthropicClient`, `OpenAICompatibleClient`, a factory keyed off `LJA_LLM_PROVIDER` |
| `lja/llm/grounding.py` | Reusable grounding validator — checks any generated artefact names only things present in its input. See "Grounding validation" below |
| `lja/data/excel_loader.py` | Parses the 3-sheet workbook into typed `Silo` / `Assessment` / `ResultRow` / `StudentSummary` records |
| `lja/data/moodle_loader.py` | Builds the same records from a live Moodle DB — runs Query 2, joins the criterion→SILO mapping CSV. The production counterpart to `excel_loader.py` |
| `lja/data/sql.py` | Loads `sql/moodle_attainment_extraction.sql`, substitutes the table prefix, slices out a single query |
| `lja/data/loading.py` | Source-aware dataset loader shared by `cli.py` and `plan.py` — turns `--source`/`--mapping`/`--clustering-cache` into a dataset + cache path so the two commands can't drift |
| `lja/data/synth_generator.py` | Generates additional synthetic students — planted, known cross-subject gaps + LLM-varied feedback. `python -m lja.data.synth_generator --help` |
| `lja/model/silo_clustering.py` | LLM-driven cross-subject SILO clustering — the semantic-matching step Scott asked for, with automatic retry on a validation failure |
| `lja/model/gap_detection.py` | Weighted per-student, per-competency attainment + **relative** gap classification — see "Gap detection" below |
| `lja/cli.py` | `python -m lja.cli <xlsx path>` or `--source moodle` — runs the whole pipeline, writes a gap report |
| `lja/model/learning_plan.py` | LLM-generated learning plan for one student, grounded in the gap output and validated by `lja/llm/grounding.py` — see "Learning plans" below |
| `lja/plan.py` | `python -m lja.plan <xlsx path> <student id>` or `--source moodle <student id>` — generates and writes one student's plan; needs `lja.cli`'s clustering cache from the same source |
| `lja/dashboard/` | `python -m lja.dashboard` — read-only web view over an already-computed pipeline run. Never calls the LLM. See "Dashboard" below |
| `tests/` | pytest — all offline (no live LLM call needed). The count is whatever CI reports; it is no longer quoted here because it went stale four times in a fortnight. |
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

## Running against Moodle (`--source moodle`)

The Moodle path connects to Postgres directly, read-only. Connection settings
come entirely from `config.MOODLE_DB` (env vars, loaded from `.env`); the loader
never opens a connection itself as the application user.

1. **Create the read-only role** on the Moodle database (once). The DDL is in
   `sql/README.md` under "Before you run anything" — a `lja_reader` role with
   `SELECT` only. Never connect as the Moodle application user.
2. **Point `.env` at the instance** (gitignored — never commit it):

   ```
   PGHOST=localhost
   PGPORT=5432            # devenv: the db container's port, published to the host
   PGDATABASE=moodle
   PGUSER=lja_reader
   PGPASSWORD=…           # the lja_reader password, not the app user's
   LJA_MOODLE_TABLE_PREFIX=m_   # devenv uses m_, a hosted instance usually mdl_
   ```

   The devenv `db` container does not publish its port by default; set
   `MOODLE_DOCKER_DB_PORT` (see `devenv/README.md`) or forward it, and use `m_`
   for the prefix — confirm with `SELECT current_setting` / `$CFG->prefix` if
   unsure.
3. **Run the pipeline:**

   ```bash
   python -m lja.cli --source moodle
   ```

   That's the whole command — it produces `output/clusters.csv` and
   `output/gap_report.csv` for the seeded subject. The clustering cache is
   source-aware (Moodle defaults to `output/silo_clustering_moodle.json`, Excel
   to `output/silo_clustering.json`) so the two paths don't clobber each other,
   and a cache that doesn't cover the current dataset's SILOs is recomputed
   automatically rather than failing gap detection. Override with
   `--clustering-cache`, `--clusters-out`, `--gaps-out` as needed.

   `--mapping` defaults to `../data-fixtures/criterion_silo_map_CSE1IOI.csv`;
   point it elsewhere for another subject. Any Moodle criterion with no row in
   the mapping CSV is a hard error listing the unmapped criteria — the mapping
   is required, not best-effort.

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

### Outcome quality and progression pages

`/silos` ("Outcome quality" in the header) is the first place the dashboard
shows anything about the *outcomes themselves* rather than the students. It
is computed by `lja/model/silo_quality.py`, pure functions over the same
three inputs as every other page (dataset, clustering, gap rows), so it
adds no pipeline stage and never calls the LLM. It shows:

- **Tiles**: subjects, SILOs, and how many SILOs are flagged by the
  clustering model, link to no other subject (a one-member cluster), are
  never assessed, or are vaguely worded.
- **The vocabulary of the outcomes** as a word cloud (d3-cloud): every
  content word across all SILO texts, sized by how many outcomes use it,
  green where it names an observable act (analyse, implement, evaluate) and
  red where it names a mental state that cannot be marked (understand,
  appreciate, be aware of). That is Bloom's old test of an assessable
  outcome, applied to the whole catalogue at once. The stem lists are
  `MEASURABLE_STEMS` and `VAGUE_STEMS` in `silo_quality.py`; qualifiers
  like "basic" are deliberately not vague.
- **Subjects**: health (share of SILOs with no issue), the four issue
  counts, students, mean attainment and gap rate. Sortable.
- **Progression by competency**: every competency taught in two or more
  subjects, the subjects in year order, the change in mean attainment from
  first to last and a trend using the same five-point band as the student
  page. Each row links to `/competency/{slug}`: a line chart of mean
  attainment and gap rate subject by subject, hollow points where the
  subject's outcome was flagged, and the outcome texts underneath.
- **Which subjects share competencies**: a chord diagram (d3), one arc per
  subject coloured by year level, ribbons weighted by shared competencies.
  Above 40 subjects it keeps the most connected and says so.
- **Attainment by subject and competency**: a heat-mapped table, empty
  where a subject has no outcome in that competency.
- **Every outcome**, worst first, with the flag reason in the model's own
  words and the vague terms found.

Run it on a large cohort the same way as any other run; only the paths change:

```bash
D=../data-fixtures/CSE_results_catalogue_handbook_3000
python -m lja.data.catalogue_generator ../data-fixtures/handbook/catalogue_tagged.yaml \
    --students 3000 --enrolment-fraction 0.05 --no-llm-feedback --seed 7 --out $D.xlsx
python -m lja.cli $D.xlsx --clustering-cache $D.clustering.json --review-file $D.clustering.review.json
python -m lja.dashboard --excel-path $D.xlsx --clustering-cache $D.clustering.json
```

Measured on that run (314 handbook subjects, 1,436 SILOs, 3,000 students,
181k result rows): generation 17 s, pipeline 13 s, dashboard start 14 s,
`/silos` renders in about 0.1 s and is about 3 MB because the outcome
table and the 314 x 48 heat map are complete rather than paged.

Two honest limits of that run. The catalogue's own competency tags stand in
for the LLM clustering (single-call clustering fails its coverage check at
52 SILOs, let alone 1,436), so **flagged is zero** there: flags only come
from a real clustering run, as on the supplied workbook where CSE2ALG SILO1
is flagged. And every progression is **stable**, because the generator's
ability model has no year-level drift to find; the page is doing its job
by not inventing a trend. What the run does show is the vocabulary: 366 of
the 1,436 real handbook outcomes lean on an unobservable verb.

d3 and d3-cloud load from the same CDN as Chart.js and carry the same
offline caveat; if they fail, the cloud and chord stay empty and the
tables still carry every number.

### Staff confirmation gate

LLM-generated competency clusters now require staff review before they are
trusted for gap generation. Each cluster has one of three states:
`pending`, `confirmed`, or `rejected`.

Review decisions are stored separately from the regenerable clustering cache
in `output/silo_clustering.review.json`. Review clusters with:

```bash
python -m lja.review
```

`python -m lja.cli` blocks gap generation when clusters are pending unless
`--allow-unconfirmed` is explicitly supplied. Rejected clusters always block
gap generation and must be returned through the documented rework path.

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

## Learning plans — the first generated artefact, and it fails closed

`python -m lja.plan <xlsx> <student id>` (S4-6) is the first LLM feature
built on top of the gap output. It is one LLM call per student, kept out of
`lja.cli` so that re-running the pipeline never silently re-spends plan
calls, and it never regenerates the clustering — it requires the cache
`lja.cli` wrote.

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx    # once: caches the clustering
python -m lja.plan ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx STU0003
# writes output/plans/learning_plan_STU0003.json and .md
```

`lja.plan` takes the same `--source {excel,moodle}` and `--mapping` options as
`lja.cli`, and its default `--clustering-cache` is source-aware in the same way
(`output/silo_clustering.json` for Excel, `output/silo_clustering_moodle.json`
for Moodle) — both commands share `lja/data/loading.py`, so a plan is always
drawn from the same source as the clustering it reads. Against Moodle the
student id is the Moodle `idnumber`:

```bash
python -m lja.cli --source moodle              # once: caches the Moodle clustering
python -m lja.plan --source moodle <idnumber>  # writes output/plans/learning_plan_<idnumber>.json and .md
```

**What the model is shown** (`build_plan_context()`): this one student's
competency classifications from `compute_gaps()`, the per-subject evidence
and trend behind each from `gap_evidence`, the wording of the SILOs each
competency is built from, and the student's own assessment scores and
marker feedback. No cohort figures, no other students. The plan can only
be as good as the gap output — see `docs/adr/0001` and the flat-profile
finding before reading much into one.

**What the model returns** is a `LearningPlan` schema, not prose: each
priority carries explicit `competency_label`, `silo_keys`, `subject_codes`
and `assessment_keys` fields alongside its `evidence` and `actions` text.
That is deliberate — it gives the grounding validator something concrete
to check.

**Tender requirement 6, enforced not requested.** Every name in the plan is
validated against the exact vocabulary of the context it was generated
from (`validate_plan()`, built on `lja/llm/grounding.py`): competencies
(each at most once), SILO keys, subject codes, assessment keys, the
student id, and any subject code or SILO key mentioned inline in the prose
fields. A failing plan is retried with the full error list quoted back to
the model (default 3 attempts, `--max-attempts`); if no attempt grounds,
`generate_learning_plan()` raises and the command exits 1 without writing
anything. `tests/test_learning_plan.py` is the grounding test suite the
sprint plan's M3 row asked for: one test per kind of invention, plus the
retry-and-recover and fail-the-build paths.

**First live run** (2026-09-07, `qwen3-vl:30b` via Ollama, STU0003 — a
student with one persistent gap on a profile spanning 63–66%): grounded on
the first attempt, one call, 35 s, 3.8k tokens in / 0.4k out. The evidence
text quoted the right per-subject figures and marker comments verbatim.
Two quality issues the validator is not meant to catch, noted for the
prompt rather than fixed blind: it listed every one of the student's seven
assessments under "revisit" instead of the two it actually cited, and it
wrote bare `SILO1`/`SILO4` in prose where the prompt asks for full keys
(the prose scan only checks `SUBJECT:SILOn` forms, so a bare id passes as
ambiguous rather than ungrounded).

Not yet done: the plan does not consult the staff-confirmation states from
IOLG-82 (PR #8) — once that merges, a plan built on a `rejected` cluster
should be refused the same way the gap report is. And there is no
dashboard rendering; the Markdown file is the deliverable for now.

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

### Grounding validation — the check every generated artefact goes through

`lja/llm/grounding.py` (S4-3, IOLG-85) is `silo_clustering.py`'s
`_validate_coverage()` generalised. That check earned its place by catching
`qwen3-vl:30b` silently dropping 3 of 13 SILOs on two separate live runs;
the S4-6 learning-plan generator needs the same guarantee for SILOs,
subjects, assessments and competency names, and tender requirement 6 says
the build must fail if it is not met. So the check now lives in one module
and clustering is just its first caller.

A validation is a list of `ReferenceCheck`s — one per kind of name —
compared against what the input actually contained:

```python
from lja.llm.grounding import InputVocabulary, ReferenceCheck, validate_grounding

vocab = InputVocabulary.from_dataset(dataset)          # SILO keys, subject codes, "SUBJECT:Assessment"
validate_grounding("learning plan", [
    ReferenceCheck("SILO", plan.silo_keys, vocab.silos),
    ReferenceCheck("subject", plan.subject_codes, vocab.subjects),
    ReferenceCheck("competency", plan.competency_labels, [c.competency_label for c in clustering.clusters]),
])                                                       # raises GroundingError (a ValueError) listing every problem
```

Three failure categories, two of them opt-in so an artefact only asserts
what it needs:

| Category | Meaning | When checked |
| --- | --- | --- |
| `unknown` | the artefact names something not in the input — the hallucination case | always |
| `missing` | something in the input never appears in the artefact | `require_complete=True` (clustering: every SILO must land in a cluster) |
| `duplicated` | something referenced more than once | `require_unique=True` (clustering: a SILO in two clusters double-counts evidence) |

`check_grounding()` returns a `GroundingReport` instead of raising, for
callers that want to retry or warn rather than fail. Names are compared
exactly after `strip()` — no case folding, no aliasing — because a near-miss
is exactly the kind of thing this check exists to catch. Structured output
is the intended input: put the names in explicit Pydantic fields and check
those. `extract_codes()` exists for free-text fields that mention subject
codes or `SUBJECT:SILOn` keys inline; it cannot recover an invented
assessment title from prose, which is the argument for structured fields.

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
and have not been tested against SILO clustering specifically. Adaptive
thinking also remains unvalidated against the full clustering task.

**Live Anthropic validation (IOLG-88, 31 August 2026).** The Anthropic
structured-output path was validated end to end against `claude-opus-4-8`.
A live structured-output request successfully returned
`status="success"` and `message="Anthropic API is working."`. The call took
2.2 seconds, used 282 input tokens and 21 output tokens, with an estimated
cost of $0.0019.

Live testing uncovered two integration issues. First, an identity-linked API
key required an `anthropic-workspace-id`; using a key scoped to the Default
Workspace resolved the authentication issue. Second, Anthropic rejected the
raw Pydantic JSON Schema because object schemas require
`additionalProperties: false`. The client was updated to use
`anthropic.transform_schema(...)`, which produces an Anthropic-compatible
schema. The Anthropic client unit tests passed after the fix. The API key is
stored only in the gitignored `.env` file and is not committed to the
repository.

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

## Generating a whole cohort from the subject catalogue (IOLG-113)

`synth_generator.py` above can only add students: it copies the supplied
workbook's three subjects and 13 SILOs verbatim. Scott was explicit that the
product's value arrives "across all of our, what, 30-plus subjects", and the
relative gap detector cannot be exercised properly on data where every
student is one baseline plus noise (see the `GAP_MIN_SPREAD` note in
`config.py` and `docs/adr/0001`). The catalogue path addresses both.

`data-fixtures/subject_catalogue.yaml` is the single source: subjects, their
SILOs, their assessments, and -- the thing the workbook cannot carry -- a
`competency` tag on every SILO saying which cross-subject competency it
evidences. The three supplied subjects are in it verbatim (a test checks
that against the workbook); nine more are synthetic, using the shortnames
`devenv/seed.sh` already generates. 12 subjects, 52 SILOs, 16 competencies,
every competency spanning two or more subjects.

```bash
python -m lja.data.catalogue_generator ../data-fixtures/subject_catalogue.yaml \
    --students 500 --seed 42 \
    --out ../data-fixtures/CSE_results_catalogue_500_synthetic.xlsx \
    --moodle-out ../data-fixtures/moodle-generated
```

What it writes, all regenerable and gitignored:

| File | Purpose |
| --- | --- |
| `<out>.xlsx` | Same three sheets and columns as the supplied workbook; loads through `load_dataset()` unchanged. |
| `<out>.truth.json` | Ground truth: which students were given a planted gap and in which competency, plus every student's hidden ability vector. |
| `<out>.clustering.json` | The catalogue's competency tags in the LLM clustering cache's own JSON shape. |
| `<out>.clustering.review.json` | A staff-review file with every ground-truth cluster confirmed, so the pipeline passes the confirmation gate without `--allow-unconfirmed`. |
| `moodle-generated/` (with `--moodle-out`) | Competency-framework CSV per subject, `criterion_silo_map.csv`, `rubric_fixture.json` and `seed_subjects.txt` for the devenv Moodle -- see `devenv/README.md`. |

How the cohort differs from the supplied data: each student has a baseline
**and** a per-competency ability (`--competency-sd`, default 7 points), so a
student weak at abstraction is weak at it in every subject that assesses
it. A fraction (`--planted-gap-fraction`, default 8%) additionally gets a
deep planted gap (18-30 points) in one cross-subject competency. Feedback
text uses the same LLM template-bank mechanism as `synth_generator.py`;
`--no-llm-feedback` uses the built-in templates. `--competency-sd 0`
reproduces the supplied data's flat profiles, which is useful for showing
why they are flat.

Then run the pipeline against the **ground-truth** clustering and score it:

```bash
python -m lja.cli ../data-fixtures/CSE_results_catalogue_500_synthetic.xlsx \
    --clustering-cache ../data-fixtures/CSE_results_catalogue_500_synthetic.clustering.json
python -m lja.data.catalogue_verify ../data-fixtures/CSE_results_catalogue_500_synthetic.truth.json \
    --gaps output/gap_report.csv
```

This isolates gap detection from clustering quality. To score the LLM's
clustering too, refresh it and pass it to the verifier:

```bash
python -m lja.cli ../data-fixtures/CSE_results_catalogue_500_synthetic.xlsx --refresh-clustering --allow-unconfirmed
python -m lja.data.catalogue_verify ../data-fixtures/CSE_results_catalogue_500_synthetic.truth.json \
    --gaps output/gap_report.csv --clustering output/silo_clustering.json
```

The verifier reports planted-gap recall, how many unplanted students were
flagged and whether the flagged competency really is in that student's
weakest third by true ability, and (with `--clustering`) pairwise
precision/recall of the LLM's clusters against the catalogue's tags.
`--min-recall 0.9` makes it exit non-zero, for CI.

Measured on the 500-student, seed-42 run through the ground-truth
clustering, default thresholds:

| Measure | Result |
| --- | --- |
| Planted gaps recovered as a persistent gap | 32 of 33 |
| Students with any persistent gap | 448 of 500 |
| Unplanted flags where the competency is in the student's weakest third | 411 of 416 |

The second line is a finding, not a bug: once students have genuine
per-competency variance, the relative detector at the default `-1.0` MAD
cutoff flags almost everyone's weakest competency. The flags are
*accurate* (third line) but there are a lot of them, which is exactly the
threshold-calibration question action A-01 leaves open. Sensitivity-test
with the `--relative-gap-cutoff` and `--competency-sd` knobs together.

**Scale finding (2026-09-20).** The first thing the 52-SILO workbook exposed
was not in the gap detector. `cluster_silos()` with the default local model
(`qwen3-vl:30b`) failed its own coverage validation on all three attempts
-- each attempt dropped three SILOs and listed three others twice -- and
`lja.cli --refresh-clustering` aborted after 7m43s. The same call succeeds
on the supplied 13 SILOs. So the single-call "cluster everything at once"
design does not hold at the scale Scott described, at least on this model;
options are a stronger model (the Anthropic provider), chunking the SILOs
per year level or per subject pair with a merge pass, or a repair step that
asks only about the missed/duplicated SILOs. That is a clustering work
package, not this one. Until it lands, score gap detection through the
ground-truth clustering, which is what the sidecar is for.

**Hundreds of real subjects: the La Trobe handbook.** For a cohort that
looks like a university -- engineering, biology, chemistry, computing
students sharing first-year maths and chemistry and then diverging -- the
subjects come from the handbook, not from the LLM's imagination.
handbook.latrobe.edu.au allows crawling, lists every subject page in its
sitemap, and embeds each subject as JSON with its SILOs; CSE1OOF's SILOs
there are the originals Scott abbreviated. Three commands:

```bash
# 1. crawl (one request/second, cached on disk; 314 pages took ~5 min)
python -m lja.data.handbook --year 2026 --prefix CSE PHY CHE MAT STA BIO BCH MIC GEN ENG ELE CIV EEE ENV AGR SCI \
    --out ../data-fixtures/handbook/catalogue_raw.yaml
# 2. group the SILOs into competencies with embeddings, label them with the LLM
python -m lja.data.competency_tagger ../data-fixtures/handbook/catalogue_raw.yaml \
    --out ../data-fixtures/handbook/catalogue_tagged.yaml --k 48 --traits 5
# 3. add programs (see below), then generate as usual
python -m lja.data.catalogue_generator ../data-fixtures/handbook/catalogue.yaml --students 3000 \
    --out ../data-fixtures/handbook/CSE_results_catalogue_handbook_3000_synthetic.xlsx \
    --moodle-out ../data-fixtures/handbook/moodle-generated
```

What each step does and does not do:

- `handbook.py` gets real SILOs, titles, year levels and credit points. The
  handbook loads assessment maps per teaching period with client-side
  JavaScript and that endpoint is not in the page bundles, so assessments
  are **synthetic**, drawn from a small library of realistic patterns per
  discipline and seeded by subject code (`assessments_synthetic: true` on
  every subject). Swap them for real ones if Scott can export them.
- `competency_tagger.py` embeds every SILO (`nomic-embed-text` through the
  OpenAI-compatible endpoint; `LJA_EMBED_MODEL`), runs spherical k-means,
  and asks the chat model only to *label* each cluster, in batches of 20.
  1,436 SILOs took 64 seconds end to end. This is the scaling answer to the
  finding above: `cluster_silos()` cannot partition 52 SILOs in one call,
  but grouping sentences by meaning is what embeddings are for. It also
  writes `traits` on each competency: loadings onto a few latent aptitude
  axes from a PCA of the cluster centroids, so competencies that mean
  similar things co-vary across students.
- **Programs** live in the catalogue's `programs:` list. Each has an intake
  share and ordered rules: "take N subjects matching these globs in this
  year", core (first N in catalogue order) or elective (sampled). The
  science set in `data-fixtures/handbook/catalogue.yaml` defines seven, from
  Computer Science to Agricultural Science and a Master of IT, and every
  student is assigned to one. The generator then draws each student's
  traits around their program's mean (`--program-selection`: engineering
  students lean towards what engineering rewards), derives competency
  abilities from traits plus independent noise (`--latent-share`), and
  enrols by the rules. Planted gaps land only in a competency the student's
  own subjects evidence at least twice.

Measured on the 3,000-student, seed-7 handbook cohort (314 subjects, 1,436
SILOs, 48 competencies, 7 programs, 193,988 result rows; generation 20 s,
workbook 24 MB, pipeline 13 s) through the ground-truth clustering:

| Relative gap cutoff (MAD) | Planted gaps found as persistent (of 245) | Unplanted students with a persistent gap | ...of which genuinely in the student's weakest third |
| --- | --- | --- | --- |
| -1.0 (default) | 227 (93%) | 2,240 of 3,000 | 2,066 |
| -1.5 | 220 (90%) | 1,833 | 1,700 |
| -2.0 | 207 (84%) | 1,420 | 1,329 |

Same shape as the 500-student finding above, now with a sensitivity curve:
the detector is accurate about *which* competency is weak, and the cutoff
trades a little planted-gap recall for a lot fewer flagged students. That
table is the input action A-01 has been missing.

The handbook directory is gitignored: the content is La Trobe's, and the
whole thing regenerates from the sitemap in minutes. Ask Scott before
committing any of it.

**Drafting more subjects with the LLM.** Hand-writing 30 subjects of
plausible SILOs is the tedious part; the model drafts them in the
catalogue's structure, shown the existing competencies and the real
subjects as style examples, and the draft is validated by the same Pydantic
model before it lands:

```bash
python -m lja.data.catalogue_draft ../data-fixtures/subject_catalogue.yaml \
    --subject CSE2OSA "Operating Systems and Architecture" 2 \
    --subject CSE3MLA "Machine Learning Applications" 3 \
    --out ../data-fixtures/subject_catalogue.yaml
```

New competencies the model proposes are appended and printed loudly --
each one changes the ground truth, so look at them. Drafted subjects are
`source: synthetic`; the supplied three are never rewritten.

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
per-criterion remark — are not. This is why the Moodle path reads the database
directly (Query 2) rather than over web services; `moodle_loader.py` and
`sql/README.md` are the answer to this gap.

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
- Multi-subject Moodle extraction. `moodle_loader.py` is proven against one
  seeded subject (CSE1IOI); the mapping CSV and Query 2 generalise, but a real
  multi-subject instance hasn't been exercised. Note `lja_criterion_score` is
  **not** materialised — the in-memory `LjaDataset` the loader returns is its
  equivalent for the slice, so there is no staging-table loader to write.
- Learning-plan / quiz / study-strategy generation — `cluster_silos()` is the
  first LLM feature built; those are next.
