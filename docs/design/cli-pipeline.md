# Learning Journey Assistant — CLI Pipeline

| | |
|---|---|
| **Version** | 2.0, 3 October 2026. Supersedes the 12 August 2026 page. |
| **Describes** | `main` at `b4ccebd` (3 Oct 2026) |
| **Source** | `docs/design/cli-pipeline.md`; diagram from `docs/handover/diagrams/04-seq-pipeline.mmd`. Rebuild with `docs/design/build.sh` |

## What `python -m lja.cli` does

One command turns a workbook, or a Moodle database, into competency clusters and a per-student gap report. It has exactly one step that touches a model, and that step is cached so a normal re-run never re-spends the call.

![Running the pipeline](../handover/diagrams/04-seq-pipeline.png)

*Figure 1: Load, cluster (cached), gate, classify. Source: `docs/handover/diagrams/04-seq-pipeline.mmd`.*

| Step | Where | What happens | Exit |
|---|---|---|---|
| Load | `lja.data.loading` | `--source excel` reads the three workbook sheets; `--source moodle` runs SQL Query 2 as `lja_reader` and joins the criterion-to-SILO CSV. Both return one `LjaDataset`. | 2 on a malformed workbook or an unmapped criterion |
| Cluster, or read the cache | `lja.model.silo_clustering` | If `output/silo_clustering.json` (or `--clustering-cache`) exists and covers every SILO, no model call. Otherwise one structured call; the result must place every SILO in exactly one cluster, and a miss is quoted back into a retry, up to three attempts. | 1 if no attempt passes coverage |
| Gate | `lja.review` | The review file beside the cache holds pending / confirmed / rejected per cluster. Any rejected cluster stops the run and prints the reviewer's note as rework instructions. Pending clusters stop it too unless `--allow-unconfirmed`. | 2 when blocked |
| Classify | `lja.model.gap_detection` | For every student and competency: weighted attainment, then floor, ceiling, flat-profile fallback, relative position against the student's own median and MAD. Persistent when two or more subjects evidence the gap. | |
| Write | | `output/clusters.csv` (one row per SILO, then the SILO definitions) and `output/gap_report.csv` (student, competency, attainment, subjects evidencing, observations, classification, basis, relative position). | 0 |

Every threshold is an environment variable with a CLI flag (`--absolute-floor`, `--relative-gap-cutoff`, `--min-spread`, …) so a sensitivity sweep is a loop in a shell, not a code change. The values are proposals, not ratified (action A-01); the dashboard's Provenance page shows the ones in force.

## The commands that read what it wrote

None of these re-clusters. Each reads the cache and the review file the pipeline left, and each is run deliberately, because the generating ones cost model calls.

| Command | Produces | Model calls |
|---|---|---|
| `python -m lja.review` | Confirm or reject clusters; a rejection needs a note | none |
| `python -m lja.plan <xlsx> STUxxxx` | A learning plan: what to work on, with evidence and actions, grounded name by name | 1 per attempt, up to 3 |
| `python -m lja.strategy <xlsx> STUxxxx` | A study strategy: how to study each gap, techniques from a closed evidence-based list, grounded per competency | 1 per attempt |
| `python -m lja.quiz <xlsx> STUxxxx` | A practice quiz per gap, multiple choice or written task, plus a blind educator review; the answer key is unverifiable and the page says so | 1 per attempt + 1 review |
| `python -m lja.export <xlsx> --out DIR` | `students.csv`, `competencies.csv`, `cohort.csv`, `manifest.json`; `--anonymise` pseudonymises ids with a keyed HMAC | none |
| `python -m lja.dashboard` | Serves the run; classifies at start-up from the workbook and cache | none on a page load; the opt-in Generate button runs `lja.plan` / `lja.quiz` as a subprocess |

## Reading the diagram

**Cache hit or miss.** Checked before anything else runs. If the cache exists, covers every SILO in the dataset and `--refresh-clustering` was not passed, the model branch is skipped and the run is free. Adding a subject with new SILOs makes the cache stale and triggers a re-cluster; existing review decisions survive for any cluster whose membership is unchanged, because a cluster's id is a hash of its members.

**The retry loop.** The grounding validator checks the response against the input, not just its shape. A live run in August produced schema-valid JSON that silently dropped three of thirteen SILOs; Pydantic cannot see a completeness problem, only a comparison with the dataset can. The same validator, with different reference lists, is what every generated artefact passes through.

**Scale.** The single call holds for the three-subject workbook (13 SILOs) and fails on a 52-SILO catalogue on the 30B local model. The handbook tagger (`lja.data.competency_tagger`, embeddings plus k-means with the model labelling clusters in batches) grouped 1,436 real SILOs in 64 seconds and is the staged answer; wiring it into `cluster_silos()` is the next clustering work package.

## Timings on the supplied workbook

| | |
|---|---|
| Load, classify, write (cache hit) | under 2 s |
| First clustering call, `qwen3-vl:30b` via Ollama | minutes; run-to-run variance is why the cache and the review file exist |
| One learning plan, `qwen/qwen3-vl-30b` via LM Studio | 17 to 35 s |
| Test suite, offline | 365 tests, about 3.5 s |
