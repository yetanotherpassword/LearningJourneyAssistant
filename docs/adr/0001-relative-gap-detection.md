# ADR 0001 — Relative gap detection

**Status:** Proposed — the algorithm is implemented and merged-ready; **the threshold values are
not ratified.** See `docs/meetings/actions.md`, action A-01.
**Date:** 2026-08-26 · **Work package:** WP2 (Jira S3-6) · **Author:** Allan (T1)
**Supersedes:** the absolute 50/65 classification in `gap_detection.py` and SQL Query 6.

> **Note on where this file lives.** `docs/README.md`'s stated convention is that decision
> records live in the bundle README beside the code they affect; the Sprint 3 runbook §5
> instructed creating `docs/adr/`. Both cannot be right, and it is action **A-11**. This file
> follows the runbook; if the team prefers bundle READMEs, it moves into `python/README.md`
> wholesale rather than being split.

---

## Problem

The lodged tender, requirement 4, promises gap detection based on the variability **within an
individual student's profile**, explicitly *"rather than raw pass or fail thresholds."*

The implementation did the opposite. `gap_detection.py` classified against
`DEFAULT_LOW_THRESHOLD = 50.0` and `DEFAULT_HIGH_THRESHOLD = 65.0` — precisely the mechanism the
tender excludes. This is a contradiction with a document already submitted, not a refinement, and
it is why WP2 exists.

## Decision

Keep `compute_gaps()`'s weighted-attainment calculation exactly as it was — it is sound, and the
approximation it makes (one assessment score counting as full evidence for every SILO it touches)
is already documented and was flagged to the project owner. **Only `_classify()` changes.**

Each student's competency attainments form a profile. For each competency:

1. Compute the profile's **median** and **median absolute deviation (MAD)**.
2. Apply the two absolute guards, **first**.
3. If the profile is too short or too flat, fall back to absolute classification **and record that**.
4. Otherwise classify by relative position, `(attainment − median) / MAD`, in MAD units.

### Why median and MAD, not mean and standard deviation

Students carry roughly 4–8 competencies. At that n a single catastrophic result drags the mean far
enough to hide everything else — the one result that most needs surfacing is also the one that
most distorts the baseline it is measured against. The median barely moves.

MAD is deliberately **not** scaled by the usual 1.4826 constant. The cut-offs are expressed
directly in MAD units, and that constant exists to make MAD approximate a standard deviation under
normality — an assumption nothing about a 5-point distribution justifies.

### Why the absolute guards stay

Pure relative classification has two degenerate cases, each **worse** than the absolute logic it
replaces:

| Case | Pure relative behaviour | Guard |
|---|---|---|
| **Uniformly weak** — everything near 35% | Almost no within-profile variance, so no outliers, so **no gaps reported to a student failing everything** | **Floor**: below it is a gap regardless |
| **Uniformly strong** — everything at 90% except one at 85% | Flags the 85% as a gap. Worse than useless — it teaches students to distrust the tool | **Ceiling**: at or above it is never a gap |

The guards are checked **before** the spread test, not after. In both degenerate cases the profile
is *also* flat, so testing spread first would route them to the fallback and lose the explicit
reason. Order is load-bearing, and `test_single_catastrophic_result_among_strong_ones_is_still_a_gap`
pins it: a 30% among four 90s must be a gap on the floor, not swallowed by the ceiling.

### Recording the basis

`CompetencyGap` gains two fields:

- `classification_basis` — `relative position` · `absolute floor` · `absolute ceiling` · `insufficient data`
- `relative_position` — the value in MAD units, or `None` when the relative path was not taken

Two reasons this is not optional. Tender requirement 5 promises every displayed figure is
traceable to a source record, and *"you have a gap here"* with no visible basis is not traceable.
And Sprint 5's feedback evidence panel renders exactly this. Reporting a relative number that did
not actually drive the verdict would be worse than reporting none, hence the `None`.

The persistent-versus-isolated distinction (`subjects_evidencing >= 2`) survives untouched. It
describes whether a gap *recurs across subjects*, which is orthogonal to how it was detected, and
Sprint 5's study-strategy generation depends on it.

## Proposed defaults — and the measurement that changed one

Every value is an `LJA_GAP_*` environment variable. There are no numeric literals in
`gap_detection.py`, specifically so Sprint 5 can sensitivity-test without a code change.

| Setting | Proposed | Reasoning |
|---|---|---|
| `ABSOLUTE_FLOOR` | 50.0 | The Fail/Pass boundary. Below it is a gap however the rest of the profile looks. |
| `ABSOLUTE_CEILING` | 75.0 | The Distinction boundary. At or above it, never a gap. |
| `RELATIVE_GAP_CUTOFF` | −1.0 | One MAD below the student's own median. |
| `RELATIVE_STRONG_CUTOFF` | +1.0 | One MAD above. |
| `MIN_COMPETENCIES` | 4 | Below this, any statistic is noise. All 150 students in the supplied dataset carry exactly 5, so this currently excludes nobody. |
| `MIN_SPREAD` | **1.0** | See below — this one was measured, not assumed. |
| `FALLBACK_PROFICIENT` | 65.0 | The old `DEFAULT_HIGH_THRESHOLD`. The fallback deliberately reproduces previous behaviour rather than inventing a third set of semantics. |

### MIN_SPREAD: the first draft was wrong

The first draft used 2.0 on the reasoning that a MAD under two points is noise. Running it against
the supplied dataset showed that **60% of all classifications fell back to "insufficient data"**
and the relative path — the entire point of requirement 4 — fired for **4.8%** of them.

Measured MAD across all 150 student profiles:

```
min 0.00   Q1 0.52   median 0.90   Q3 1.40   max 3.80   mean 1.04
```

| `MIN_SPREAD` | Students classified relatively |
|---|---|
| 0.5 | 134/150 (89%) |
| **1.0** | **72/150 (48%)** |
| 1.5 | 35/150 (23%) |
| 2.0 | 15/150 (10%) |

1.0 is justified on a principle first — attainment is reported to one decimal place, so a profile
whose median deviation is under a whole point is flat within the resolution of the figures
themselves — and the measurement is a check on that, not the source of it. At 1.0 the basis
distribution becomes: relative 27.5%, ceiling 29.1%, insufficient 37.6%, floor 5.9%.

### The finding the team most needs to see

**These profiles are nearly flat, and that may be an artefact rather than a fact about students.**

Each competency's attainment is a weighted average over several assessments, and in the generator
each assessment is a single per-student baseline plus independent noise. There is no
per-competency ability term at all, so within-profile variation is *by construction* mostly noise.
Real students have genuine strengths and weaknesses; this dataset largely does not.

The consequence is visible in the output. Of the 71 gaps found by relative position:

```
distance below the student's own median, in percentage points:
  min 1.0   Q1 1.8   median 2.2   Q3 3.3   max 6.8
  25 of 71 are less than 2 points below their own median
```

**A quarter of relative gaps are under two percentage points below the student's own median.** On
this data, "your weakest competency" often means a difference too small to act on. That is not an
argument against relative detection — it is an argument that this dataset cannot demonstrate it
well, and a warning against tuning the thresholds to fit.

**Do not tune `MIN_SPREAD` down to make more gaps appear.** Lowering it to 0.5 would classify 89%
of students relatively while making a one-point difference a confident verdict. The right response
is either better data, or accepting that the absolute guards carry most of the load until there is
some.

## Consequences

- `compute_gaps()` can no longer classify in a single pass — a competency's verdict depends on the
  student's *other* competencies, so the whole profile must exist first. Attainment is computed for
  all pairs, then profiles are assembled, then everything is classified.
- `compute_gaps()`'s signature changes: `low_threshold`/`high_threshold` become one `GapThresholds`
  object. `lja.cli` and `lja.dashboard.__main__` are updated; the CLI exposes all six tunables as
  flags for Sprint 5's sweep, the dashboard only the two absolute guards.
- The gap report CSV gains `classification_basis` and `relative_position` columns.
- The student page states how each verdict was reached.
- **`sql/moodle_attainment_extraction.sql` Query 6 is now divergent and annotated as such.** It
  still carries 50/65. The Moodle path is not wired until Sprint 4, so porting this logic to SQL
  now would be maintaining two implementations of an unratified algorithm. Reconciling them is a
  Sprint 4 task. An annotated divergence is fine; a silent one is not.
- On the supplied dataset the change moves students-with-at-least-one-gap from 20 to 58 of 150.
  That is a large behavioural shift driven by unratified numbers, which is the main reason A-01
  should be settled before this is demonstrated to the project owner.

## Alternatives considered

**Keep absolute thresholds.** Rejected: it contradicts a lodged tender commitment.

**Pure relative, no guards.** Rejected: the two degenerate cases above make it worse than what it
replaces, for exactly the students who most need the tool to work.

**Mean and standard deviation.** Rejected: at n≈5 one catastrophic result distorts the baseline it
is being measured against.

**Z-scores against the whole cohort rather than the student's own profile.** Rejected as a
misreading of the requirement — that measures a student against their peers, which is a different
and more sensitive claim than measuring them against themselves. Worth revisiting deliberately if
the team ever wants cohort-relative reporting, but it is not what requirement 4 promises.

**Porting the logic to SQL now.** Rejected: two implementations of an unratified algorithm, on a
path that is not wired until Sprint 4.
