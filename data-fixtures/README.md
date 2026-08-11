# LJA — Data fixtures bundle

Import fixtures, plus the tracking checklist for the dataset we have requested
from the project owner.

## Contents

| File | Purpose |
| --- | --- |
| `CSE_results_150_students_3_Subjects.xlsx` | **The real dataset**, supplied by Scott Mann on the 2026-08-11 call. Three sheets: `Assessment Map` (SILOs + assessment weights per subject), `Results` (1650 rows — 150 synthetic students × 11 assessments, scored, with feedback), `Student Summary` (per-subject totals + performance band). See `python/README.md` — this is what `lja.cli` actually runs against. |
| `CSE_results_300_students_3_Subjects_synthetic.xlsx` | **Generated, not supplied** — the 150 real students above plus 150 more from `lja/data/synth_generator.py`, same shape, same subjects/SILOs/assessments. 11 of the new students have a deliberately planted, known gap on `CSE1OOF:SILO2` + `CSE2ALG:SILO2`/`SILO3`. Running the pipeline against this file and checking that those exact students come back as a persistent gap is a real correctness test — see `python/README.md`'s "Generating more synthetic data" section. Regenerable; not load-bearing to keep in git if the team would rather `.gitignore` it and regenerate on demand. |
| `backup-moodle2-course-2-demo101-20260809-1200-nu.mbz` | A small external sample Moodle backup used to prove the restore path (see `devenv/README.md`). Not from Scott, no rubric-graded activities — kept as a restore-mechanics reference only, not sample data. |
| `competency_framework_cse5idp.csv` | Moodle competency framework import fixture. CSE5IDP's own SILOs, as a worked example. |

## Incoming dataset — what we asked for, and what actually arrived

We never receive real student data; every student in the xlsx above is
synthetic (`STU0001`...`STU0150`), per the proposal. Checklist below, updated
against the 2026-08-11 call transcript.

- [x] **Structured subject/assessment/SILO/score data for 3 subjects** — not
      the `.mbz` backup route originally planned; Scott instead supplied a
      pre-extracted Excel workbook directly. Simpler for this phase, and the
      one now driving `python/lja`. The `.mbz` restore path in `devenv/` is
      still real (and still worth knowing), just not the thing currently
      feeding the pipeline.
- [x] **Subjects forming a progression sequence** — confirmed real subjects:
      `CSE1OOF` (first year, object-oriented programming), `CSE2ALG` (second
      year, algorithms & data structures), `CSE3CAP` (capstone). Exactly the
      "gap in first year, consequence in third year" narrative Scott
      described — this is not a coincidence, it's the point of the demo set.
- [x] **SILOs, with stable IDs** — in the `Assessment Map` sheet, `SILO1`
      through `SILO5` **numbered locally per subject** (CSE1OOF has 4,
      CSE2ALG has 5, CSE3CAP has 4 — 13 total). The same number means
      different things in different subjects; only `(subject_code,
      silo_local_id)` together is a stable key. This is the exact problem
      Scott described wanting semantic (not keyword) matching for.
- [x] **Exemplar feedback per assessment** — present in `Results`, but
      **templated**: only 45 unique feedback strings across 1650 rows,
      confirmed by inspection. Scott named this directly on the call
      ("cut and paste... automated rubrics") and separately offered to try
      sourcing real custom feedback, flagging a student re-identification
      risk if he does — expect a sanitised version, not raw text, if it
      arrives at all.
- [ ] **Decision: which mechanism production Moodle uses** — Outcomes,
      Competency subsystem, or neither. Still open; this Excel dataset
      sidesteps it entirely, since it was extracted from Moodle already
      structured rather than requiring us to read the mechanism ourselves.
      Still relevant for the production Moodle-integration path.
- [ ] **Decision: gap-classification thresholds** — Scott explicitly said on
      the call he doesn't know how "at risk" is currently determined
      ("I'm not sure how we determined at risk"). The 50/65 in
      `sql/moodle_attainment_extraction.sql` Query 6 and
      `lja/model/gap_detection.py` remain placeholders — there is no
      existing institutional number to match, so this is now an open design
      decision for the team, not a confirmation to chase.
- [ ] **Scale, at production**: Scott was explicit this canned 3-subject,
      150-student set is deliberately small — "the power will come at scale
      when we do this across all of our, what, 30-plus subjects." Nothing to
      action now; a note for when this moves toward production.

When the real frameworks arrive, swap them in for the CSE5IDP worked example
below — that file exists to prove the import path, not to ship.

## Why this exists

Moodle already has two native mechanisms for the outcome mapping the project
owner asked for, and neither appears in the project proposal. Finding this
early changes the architecture.

**Outcomes** (legacy, simpler). Enabled via `$CFG->enableoutcomes`. Outcome
statements attach to grade items and are scored separately from the mark;
`mdl_grade_items` carries an `outcomeid` column. This is essentially outcome
attainment already modelled in the schema.

**Competency frameworks** (modern, richer). A framework holds a hierarchy of
competencies. Competencies link to courses via `mdl_competency_coursecomp` and to
individual activities via `mdl_competency_modulecomp`. Per-user proficiency
accumulates in `mdl_competency_usercomp` with an audit trail in
`mdl_competency_evidence`. Learning plans are a built-in concept.

Subject intended learning outcomes map onto a competency framework almost
one-to-one, and Moodle can already answer "which competencies is this student
weak in across their enrolled courses" — which is the aggregation layer the
project owner said last semester's teams failed to build.

Deciding whether we build our competency model on top of Moodle's or alongside it
is a Sprint 1 spike. Either answer is defensible. Not having considered it is not.

## What is in the file

Eighteen rows: the framework itself, five SILOs taken verbatim from the CSE5IDP
handbook entry and Subject Learning Guide, and thirteen indicator-level children.
The taxonomy is `outcome,indicator`, so Moodle labels level one "Outcome" and
level two "Indicator" in the UI.

## Format notes

- Hierarchy comes from `Parent ID number` referencing another row's
  `ID number`. Row order is flexible, but every referenced parent must exist.
- The framework row is the one with `Is framework` set to `1` and an empty parent.
- `Rule type` of `core_competency\competency_rule_all` with `Rule outcome` of `2`
  means "when all children are complete, recommend this competency for review" —
  appropriate for a SILO evidenced by several indicators.
- `Related ID numbers` links SILO4 and SILO5, since documentation and oral
  communication are assessed together in the final handover.

## Two caveats before importing

**The scale configuration needs verifying.** `Scale configuration` references a
`scaleid`, left as `0` in this file. The importer's handling of scale creation is
version-specific and worth confirming rather than trusting.

The safe workflow, which is worth doing regardless: build a small throwaway
framework by hand at Site administration → Competencies → Competency frameworks,
export it to CSV, and diff that export against this file. The export is by
definition valid input to the importer on our exact Moodle version, so it settles
the format question in about ten minutes. Fix the scale row to match, then
import.

**This is a demonstration, not the product.** CSE5IDP's own SILOs are convenient
because we have them to hand. The frameworks the product actually needs are for
the subjects in the supplied dataset — likely first and second year subjects,
where the "gap in first year, consequence in third year" narrative the project
owner described actually plays out. Use this file to prove the import path and to
have something visible in the UI for the trade show booth. Swap in the real
frameworks the day the dataset lands.

## Import path

Site administration → Competencies → Import competency framework → upload the
CSV → map columns → confirm.
