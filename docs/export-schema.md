# Export schema (tender requirement 7)

`python -m lja.export` writes a structured extract for the department's
**longitudinal and A/B evaluation** — comparing cohorts that used the assistant
against cohorts that did not, and one semester against the next. It is a
faithful CSV projection of an already-computed pipeline run (`compute_gaps()`
plus the `gap_evidence` trend and the per-student subject totals the loader
carries); it never calls the LLM and never re-decides anything.

```bash
# once, to cache the clustering the export reads (same --source):
python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx
# then:
python -m lja.export ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --out output/export
python -m lja.export --source moodle --out output/export --anonymise
```

The command writes four files into `--out`: **`students.csv`**,
**`competencies.csv`**, **`cohort.csv`** and **`manifest.json`**. Two runs are
meant to be diffed, so every column is documented below and `manifest.json`
records exactly what produced the files.

`--anonymise` replaces every `student_id` with an HMAC-SHA256 pseudonym keyed on
`LJA_EXPORT_SALT` (see `python/.env.example`). The same student maps to the same
pseudonym across every export taken with the same salt — which is what lets the
two cohorts be lined up without either file carrying a real id — while the
mapping cannot be reversed without the key. An empty salt is refused (exit 2)
rather than keying on `""`, which would be stable but guessable.

---

## `students.csv`

One row per student. After the three fixed columns there is **one column per
subject code** seen in the run (sorted), so the header is stable for a given
dataset and two runs of the same cohort line up column-for-column.

| Column | Type | Meaning | Source |
| --- | --- | --- | --- |
| `student_id` | string | Student identifier — the raw id, or an HMAC pseudonym under `--anonymise` | `StudentSummary.student_id` (Excel: `Student ID`; Moodle: `idnumber`) |
| `performance_band` | string | The workbook's overall performance band (e.g. `Credit`, `At risk`) | `StudentSummary.performance_band` |
| `average_total` | float | The student's overall average across subjects, as supplied | `StudentSummary.average_total` |
| `<SUBJECT>` (e.g. `CSE1OOF`) | float \| blank | The student's total for that subject; **blank** if the student did not sit it (not `0`) | `StudentSummary.subject_totals[subject]` |

## `competencies.csv`

One row per `(student, competency)` verdict — the same grain as
`output/gap_report.csv`, enriched with the longitudinal `trend` and the
`in_plan` flag.

| Column | Type | Meaning | Source |
| --- | --- | --- | --- |
| `student_id` | string | As in `students.csv` (pseudonymised identically under `--anonymise`) | `CompetencyGap.student_id` |
| `competency_label` | string | The cross-subject competency label | `CompetencyCluster.competency_label` (clustering cache) |
| `attainment_pct` | float | Weighted attainment for this competency, 0–100, 1 dp | `CompetencyGap.attainment_pct` |
| `classification` | enum | `persistent gap` \| `isolated gap` \| `developing` \| `proficient` | `CompetencyGap.classification` |
| `classification_basis` | enum | How the verdict was reached: `relative position` \| `absolute floor` \| `absolute ceiling` \| `insufficient data` | `CompetencyGap.classification_basis` |
| `relative_position` | float \| blank | Position vs the student's own median, in MAD units; **blank** whenever the relative path was not the one taken | `CompetencyGap.relative_position` |
| `subjects_evidencing` | int | How many subjects contributed evidence (≥2 ⇒ a gap here is *persistent*) | `CompetencyGap.subjects_evidencing` |
| `n_observations` | int | Number of assessment observations behind the figure | `CompetencyGap.n_observations` |
| `trend` | enum | Direction across year-level-ordered subjects: `improving` \| `stable` \| `declining` \| `insufficient evidence` | `describe_trend(subject_breakdown(...))` (`gap_evidence`) |
| `in_plan` | bool | Whether this competency is a **priority** in the student's generated learning plan (not merely mentioned in its prose) | `output/plans/learning_plan_<id>.json` → `priorities[].competency_label` |

`classification_basis`, `relative_position`, `subjects_evidencing` and
`n_observations` travel with every row for the reason `gap_report.csv` carries
them: tender requirement 5 asks that a displayed figure be traceable to how it
was reached, and a verdict with no visible basis is not traceable.

## `cohort.csv`

One row per competency, aggregated across every student in the run. **No
student ids**, so this file is safe to share even from a non-anonymised run —
it is the primary A/B-comparison grain.

| Column | Type | Meaning | Source |
| --- | --- | --- | --- |
| `competency_label` | string | The cross-subject competency label | as above |
| `n_students` | int | Number of students with a row for this competency | count of `competencies.csv` rows for the label |
| `mean_attainment` | float | Mean `attainment_pct` across those students, 2 dp | derived |
| `gap_rate` | float | Fraction whose verdict is a gap (isolated **or** persistent), 3 dp | derived |
| `proficient_rate` | float | Fraction classified `proficient`, 3 dp | derived |

## `manifest.json`

Records exactly what produced the CSVs, so a reader knows two exports came from
the same code, thresholds and clustering before trusting a difference is about
the students and not the pipeline.

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | This document's version — see the policy below |
| `generated_at` | string | UTC timestamp (ISO 8601, seconds) the export was written |
| `source` | string | `excel` or `moodle` |
| `git_commit` | string | `HEAD` at export time, or `unknown` if run outside a checkout |
| `clustering_cache` | string | Path to the SILO clustering the export read |
| `thresholds` | object | The seven `GapThresholds` in force (`absolute_floor`, `absolute_ceiling`, `relative_gap_cutoff`, `relative_strong_cutoff`, `min_competencies`, `min_spread`, `fallback_proficient`) |
| `anonymised` | bool | Whether `--anonymise` was used |
| `files` | array | The CSVs this manifest describes |

---

## Schema version policy

`schema_version` is `MAJOR.MINOR`:

- **First digit (MAJOR)** bumps on any **removed or renamed column**, or any
  change to the meaning of an existing column — anything that can break a
  consumer reading by column name.
- **Second digit (MINOR)** bumps on **additive** changes only — a new column
  appended, a new manifest field — which an existing consumer can ignore.

Current version: **`1.0`**.

## Open question for Scott

The columns above are what the pipeline can produce faithfully today. Two
field-set questions are open and were raised with Scott (Allan's message covers
them); absent a reply this shipped as `1.0` with the columns above:

1. **A time / semester dimension.** There is no term or intake column: nothing
   in the current dataset carries one. Longitudinal comparison therefore works
   by diffing two separately-produced exports (identified by
   `manifest.generated_at` / `git_commit`), not by a within-file time column. If
   the department wants a single file spanning semesters, we need a
   semester/term identifier as a first-class column — and a source that carries
   it.
2. **An explicit cohort label** (used-the-assistant vs did-not). That grouping
   is not in the students' records; it would have to be supplied to the export,
   not derived. If the A/B split is to live in the file rather than in how the
   two exports are separated, confirm where that label comes from.
