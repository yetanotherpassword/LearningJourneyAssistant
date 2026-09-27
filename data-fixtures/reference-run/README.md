# Reference run

A fixture so the pipeline and dashboard run offline, from a fresh clone, with no
LLM. It is **not a claim about clustering quality**: the clusters here are
confirmed in bulk so the pipeline will run, not because staff reviewed them. Staff
review of the clustering is in `docs/cluster-review-sprint5.md` (Sui Lung, Sprint 5).

| | |
|---|---|
| Dataset | `data-fixtures/CSE_results_150_students_3_Subjects.xlsx` (150 students, 3 subjects, 13 SILOs) |
| Model | `qwen3-vl:30b` via Ollama (`openai_compatible`), temperature 0.2 |
| Date | 25 Sep 2026 |
| Commit | `ac75a8e` (main, after PR #20) |

## Contents

| File | What it is |
|---|---|
| `silo_clustering.json` | The LLM's SILO-to-competency clustering (5 competencies) |
| `silo_clustering.review.json` | Review decisions: every cluster `confirmed` |
| `clusters.csv` | The clustering as one row per SILO |
| `gap_report.csv` | 750 rows (150 students x 5 competencies); 24 persistent gaps |
| `plans/learning_plan_STU0003.*` | Learning plan, persistent gap on the relative basis |
| `plans/learning_plan_STU0004.*` | Learning plan, persistent gap below the absolute floor |
| `plans/learning_plan_STU0022.*` | Learning plan, persistent gap on the relative basis at 71.5% |

## Using it

From `python/`:

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --clustering-cache ../data-fixtures/reference-run/silo_clustering.json
LJA_DASHBOARD_CLUSTERING_CACHE=../data-fixtures/reference-run/silo_clustering.json python -m lja.dashboard
```

The CLI finds `silo_clustering.review.json` beside the cache, so no
`--allow-unconfirmed` is needed, and it reproduces `gap_report.csv` exactly.

**Keep the review file all-confirmed.** A rejected cluster makes `lja.cli` exit 2,
which breaks every offline run built on this fixture. To try a rejection, copy the
two JSON files somewhere else first.

## How it was produced

Clustering run three times with `--refresh-clustering`. The first run gave 3
competencies, which is below `min_competencies` (4), so every student would have
fallen back to absolute classification and the relative basis would never appear.
Runs 2 and 3 were identical, with 5 competencies. That result is kept here; 217 of
the 750 gap rows are classified on the relative basis.

```bash
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --refresh-clustering
python -m lja.review --cluster <id> --state confirmed   # for each of the 5 cluster ids
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx
python -m lja.plan ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx STU0003   # also STU0004, STU0022
```
