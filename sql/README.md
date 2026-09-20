# LJA — SQL bundle

Read-only extraction queries for a self-hosted Moodle instance, plus the schema
for the assistant's own criterion-to-outcome mapping table.

**Status: production path, now wired to code (Query 2).** As of IOLG-104,
`python/lja/data/moodle_loader.py` runs Query 2 against a live Moodle
Postgres and builds the same `LjaDataset` the Excel path produces, so
`python -m lja.cli --source moodle` yields clusters and a gap report with no
change to the model code. `lja/data/sql.py` is the single place that reads
this file, substitutes the table prefix (`{prefix}`, see below), and slices
out an individual query. The project owner also supplied a ready-extracted
Excel workbook on 2026-08-11
(`data-fixtures/CSE_results_150_students_3_Subjects.xlsx`); that Excel path
(`--source excel`, the default) is the other way in. The remaining queries
(1, 3–6) are documentation/plan, not yet called from code.

The `lja_criterion_score` table below is **not materialised**: the in-memory
`LjaDataset` the loader returns is its equivalent for the vertical slice, so
nothing writes a staging table.

## Contents

| File | Purpose |
| --- | --- |
| `moodle_attainment_extraction.sql` | Six queries and one table definition. Fully commented. |

## Target environment

- Moodle 5.2.x (current stable, released 20 April 2026)
- PostgreSQL backend
- Default table prefix `mdl_` — check `$CFG->prefix` in `config.php` if unsure.
  **Confirmed discrepancy:** our own `devenv/` Docker install actually uses
  `m_`, not `mdl_` — moodle-docker's `config.docker-template.php` sets it,
  and it was caught by querying the live devenv Postgres directly. These
  queries are written against `mdl_` because that's Moodle's own documented
  default and what a hosted/production instance more commonly runs, but
  **do not assume either prefix** — check the actual instance before running
  anything here. Whoever writes the Moodle-path loader in `python/lja`
  should make the prefix a config value, not a hardcoded string, given we've
  already seen it vary between our own two environments.

## Before you run anything

Create a dedicated read-only role. Do not connect as the Moodle application
user, and never write to Moodle tables directly — grade aggregation, event
triggers and cache invalidation all live in PHP, so a direct `UPDATE` will
silently desynchronise the gradebook.

```sql
CREATE ROLE lja_reader LOGIN PASSWORD '<from .env, not committed>';
GRANT CONNECT ON DATABASE moodle TO lja_reader;
GRANT USAGE ON SCHEMA public TO lja_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO lja_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lja_reader;
```

## The queries

1. **Rubric definitions** — every criterion and level in the instance. Run first;
   this is the vocabulary the mapping table has to cover.
2. **Per-criterion rubric fills, per student** — the core query. Level awarded,
   score, criterion ceiling, normalised percentage, and the marker's remark.
3. **Legacy Outcomes attainment** — returns rows only if
   `$CFG->enableoutcomes = 1` and outcomes are attached to activities.
4. **Competency framework attainment** — per-user proficiency from the modern
   competency subsystem.
5. **Activity-to-competency linkage** — which assessments already declare which
   competencies.
6. **Gap detection across subjects** — weighted attainment per outcome, with
   isolated gaps distinguished from persistent ones.

Plus `CREATE TABLE lja_criterion_silo_map`, which belongs in the assistant's own
database, not inside Moodle.

## Two things that will bite you

**`grading_instances.itemid` is not a user id.** For assignments it is
`mdl_assign_grades.id` — the grade record — which is where `userid` lives. Join
through `assign_grades`. Joining `itemid` directly to `user.id` returns rows and
they are all wrong.

**Filter on `grading_instances.status = 1`.** If a marker edits a rubric after
grading, existing instances flip to a needs-update status while the pushed
gradebook grade stays unchanged. Without the filter you mix grading history into
current attainment.

Status constants: `0` needs update, `1` active, `2` incomplete, `3` archived.

## How this feeds the pipeline

Query 2's output loads into the assistant's own `lja_criterion_score` table,
joins to `lja_criterion_silo_map` (defined in this file — staff-editable data,
not code), and Query 6 aggregates the pair into per-SILO attainment and gap
classifications. That chain is the walking skeleton's spine.

## Open decisions for the project owner

Both items are tracked, with the rest of the dataset request, in the
data-fixtures README checklist.

- The gap-classification thresholds in query 6 (currently 50 and 65) are
  placeholders. On the 2026-08-11 call Scott said he isn't sure how the
  existing "at risk" band is determined either — there may be no
  institutional number to confirm against, meaning this could be a decision
  the team gets to make and justify, not one to keep chasing an answer for.
  `python/lja/model/gap_detection.py` uses the same two placeholders.
- Queries 3 and 4 represent the two competency mechanisms. Run both against the
  supplied dataset; whichever returns rows tells us which one La Trobe actually
  uses in production, and that should drive the architecture. If neither
  returns rows, the bridging table is not a workaround — it is the product.

  **Resolved (IOLG-87, 2026-09-15, against the devenv seeded with the IOLG-56
  rubric fixture):** both queries return **zero rows**.
  - **Query 3 (legacy Outcomes):** 0 rows. `$CFG->enableoutcomes` is off and
    no outcomes are attached to activities (`m_grade_outcomes` is empty).
  - **Query 4 (competency framework):** 0 rows. All competency tables are
    empty (`m_competency`, `m_competency_framework`, `m_competency_usercomp`,
    `m_competency_coursecomp` = 0). Critically, Query 4 reads *from*
    `competency_usercomp` — per-user proficiency ratings — and **importing a
    framework does not create those**; a marker would have to rate each student
    against each competency, which nothing in the LJA marking workflow does
    (marking happens through rubrics). So even after importing
    `data-fixtures/competency_framework_cse5idp.csv` via
    `admin/tool/lpimportcsv`, Query 4 would still return 0 rows until
    per-student competency proficiency exists.

  **Conclusion:** neither built-in attainment mechanism carries data for our
  subject. The rubric-fillings path (Query 2) joined to the staff-editable
  `criterion_silo_map` CSV **is the product**, not a workaround — which is why
  `moodle_loader.py` builds the dataset from Query 2 + the mapping CSV rather
  than from Outcomes or competency proficiency.

  A `{prefix}`-inside-a-line-comment bug in `sql.py`'s query slicer surfaced
  while running Query 4 here (a `;` in a `-- comment` truncated the statement
  and dropped a `LEFT JOIN`); fixed in IOLG-104 with a regression test.
