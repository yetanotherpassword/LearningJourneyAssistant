# Validation worksheet — IOLG-110

Prepared 28 September 2026 for Anup and Allan's review.
Expected results below are calculated from the seven profiles in the
27 September Sprint 5 brief, independently of the detector's output.
The CSV is [cases.csv](../python/tests/validation/cases.csv).

**Row-count discrepancy:** the brief says 30 competency rows, but its seven
profiles contain `4 + 4 + 4 + 4 + 3 + 5 + 4 = 28`. The CSV contains those
28 rows and the specified numbers exactly. No extra competencies were invented.

## Rules and thresholds

Apply the absolute floor (`attainment < 50`) first, then the absolute ceiling
(`attainment >= 75`). Otherwise, fewer than four competencies or MAD below
1.0 gives `insufficient data`: proficient at 65 or above, developing below 65.
For a sufficiently large and varied profile, median absolute deviation
(MAD) is the median of `abs(attainment - profile median)`, without scaling.
Position is `(attainment - median) / MAD`. At or below -1.0 is a gap;
at or above +1.0 is proficient; everything between is developing.
A gap is isolated for one evidencing subject and persistent for two or more.

The CSV uses the exact report strings: `absolute floor`, `absolute ceiling`,
`insufficient data`, and `relative position`.
The verification pins these thresholds explicitly so a local `.env` cannot
change the expected answers. Profile medians and MADs are not rounded before
classification. On an absolute or fallback decision, relative position is
not used and the report should record `None`.

## uniform_weak

A–D: 40, 45, 42, 48; one subject each. Sorted: 40, 42, 45, 48.
Median = `(42 + 45) / 2 = 43.5`. Absolute deviations in A–D order:
3.5, 1.5, 1.5, 4.5; sorted: 1.5, 1.5, 3.5, 4.5.
MAD = `(1.5 + 3.5) / 2 = 2.5`.
Every attainment is below 50, so the absolute floor decides all four before
any relative comparison.

- A → isolated gap (`absolute floor`, 40 < 50).
- B → isolated gap (`absolute floor`, 45 < 50).
- C → isolated gap (`absolute floor`, 42 < 50).
- D → isolated gap (`absolute floor`, 48 < 50).

## uniform_strong

A–D: 80, 78, 85, 90; one subject each. Sorted: 78, 80, 85, 90.
Median = `(80 + 85) / 2 = 82.5`. Deviations: 2.5, 4.5, 2.5, 7.5;
sorted: 2.5, 2.5, 4.5, 7.5. MAD = `(2.5 + 4.5) / 2 = 3.5`.
Every attainment is at least 75, so the absolute ceiling decides all four.

- A → proficient (`absolute ceiling`, 80 >= 75).
- B → proficient (`absolute ceiling`, 78 >= 75).
- C → proficient (`absolute ceiling`, 85 >= 75).
- D → proficient (`absolute ceiling`, 90 >= 75).

## flat_profile

A–D: 62.0, 62.5, 63.0, 62.8; one subject each.
Sorted: 62.0, 62.5, 62.8, 63.0. Median = `(62.5 + 62.8) / 2 = 62.65`.
Deviations: 0.65, 0.15, 0.35, 0.15; sorted: 0.15, 0.15, 0.35, 0.65.
MAD = `(0.15 + 0.35) / 2 = 0.25`. No absolute guard applies.
There are four competencies, but `0.25 < 1.0`, so use the fallback.
All four attainments are below 65.

- A → developing (`insufficient data`, 62.0 < 65).
- B → developing (`insufficient data`, 62.5 < 65).
- C → developing (`insufficient data`, 63.0 < 65).
- D → developing (`insufficient data`, 62.8 < 65).

## relative_clear

A–D: 70, 68, 72, 55; one subject each. Sorted: 55, 68, 70, 72.
Median = `(68 + 70) / 2 = 69`. Deviations: 1, 1, 3, 14;
sorted: 1, 1, 3, 14. MAD = `(1 + 3) / 2 = 2`.
No absolute guard applies, there are four competencies, and MAD >= 1.0.

- A → developing (`relative position`, `(70 - 69) / 2 = +0.5`).
- B → developing (`relative position`, `(68 - 69) / 2 = -0.5`).
- C → proficient (`relative position`, `(72 - 69) / 2 = +1.5`).
- D → isolated gap (`relative position`, `(55 - 69) / 2 = -7.0`, one subject).

## three_competencies

A–C: 55, 70, 72; one subject each. Sorted: 55, 70, 72; median = 70.
Deviations: 15, 0, 2; sorted: 0, 2, 15; MAD = 2.
No absolute guard applies. There are only three competencies (`3 < 4`),
so the fallback applies even though the MAD is large enough.

- A → developing (`insufficient data`, 55 < 65).
- B → proficient (`insufficient data`, 70 >= 65).
- C → proficient (`insufficient data`, 72 >= 65).

## boundary_exact

A–E: 60, 62, 64, 66, 68; one subject each. Already sorted; median = 64.
Deviations: 4, 2, 0, 2, 4; sorted: 0, 2, 2, 4, 4; MAD = 2.
Five competencies, sufficient spread, and no absolute guard: use relative
positions. Both cutoffs are inclusive.

- A → isolated gap (`relative position`, `(60 - 64) / 2 = -2.0`).
- B → isolated gap (`relative position`, `(62 - 64) / 2 = -1.0`, exactly the gap cutoff).
- C → developing (`relative position`, `(64 - 64) / 2 = 0.0`).
- D → proficient (`relative position`, `(66 - 64) / 2 = +1.0`, exactly the strong cutoff).
- E → proficient (`relative position`, `(68 - 64) / 2 = +2.0`).

## persistent

A–D: 70, 68, 72, 55; subjects evidencing: 1, 1, 1, 2.
Sorted: 55, 68, 70, 72; median = `(68 + 70) / 2 = 69`.
Deviations: 1, 1, 3, 14; MAD = `(1 + 3) / 2 = 2`.
The positions match `relative_clear`. Only D's subject count changes.

- A → developing (`relative position`, `(70 - 69) / 2 = +0.5`).
- B → developing (`relative position`, `(68 - 69) / 2 = -0.5`).
- C → proficient (`relative position`, `(72 - 69) / 2 = +1.5`).
- D → persistent gap (`relative position`, `(55 - 69) / 2 = -7.0`, two distinct subjects).

## Verification and limits

From `python/`, run `python -m pytest -q tests/test_validation_cases.py`.
The test reads the CSV, builds one assessment per competency and evidencing
subject, and calls `compute_gaps()`. Equal scores in both subjects for
`persistent/D` preserve its 55% attainment while exercising distinct-subject
counting. It compares every row's attainment, classification, basis, and
subject count, plus the independently calculated profile statistics and
relative positions. Expected labels are read from the CSV, never generated
by the production classifier.

These cases validate classification of already-established competency
attainments; they do not validate LLM clustering quality or every weighting,
missing-data, and threshold-boundary condition. Existing detector tests
cover additional scenarios. Allan and Anup should review this arithmetic
before recording the individual human-validation task as complete.

The supplied workbook has nearly flat within-student profiles: the earlier
measurement in [ADR 0001](adr/0001-relative-gap-detection.md#the-finding-the-team-most-needs-to-see)
reports a median MAD of about 0.9. Many competencies that escape the absolute
floor and ceiling therefore take the insufficient-data fallback. This is
synthetic/modelled data, not evidence about real students. The IOLG-113
synthetic cohort introduces competency-specific variation to exercise the
relative rules, alongside the explicit profiles above. The ADR's earlier
measurement depends on its clustering; it should not be presented as a new
measurement of the current reference run.
