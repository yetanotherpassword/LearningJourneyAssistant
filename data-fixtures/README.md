# LJA — Data fixtures bundle

## Contents

| File | Purpose |
| --- | --- |
| `competency_framework_cse5idp.csv` | Moodle competency framework import fixture. CSE5IDP's own SILOs, as a worked example. |

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
