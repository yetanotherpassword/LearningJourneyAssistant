# Actions Register

**Running register of actions arising from team meetings — not a backlog, and not per-meeting
minutes.** Add rows, change states, record outcomes inline. An action closed in a later meeting
keeps its original ID so the decision trail survives.

## What belongs here, and what does not

The dividing line is **who acts, and when the row closes**:

| | Lives here | Lives in Jira (IOLG) |
|---|---|---|
| Kind | Decide · Confirm · Authorise · Assign · Raise a ticket | Engineering work that produces code or a deliverable |
| Closes when | the decision is made, or the ticket exists | the work is done and accepted |

**If an action produces code, it is a Jira ticket and the meeting action is "raise it."** Tracking
the engineering to completion here as well would create a second backlog competing with the board
— which is the exact fragmentation action A-17 exists to stop, so doing it would be self-defeating.

**States:** `OPEN` · `AGREED` · `BLOCKED` · `DONE` · `DROPPED` (with a reason)

Owners use the tender §10 numbering: T1 Allan · T2 Ayesha · T3 Istiaque · T4 Anup · T5 Sui Lung.
`ALL` means the meeting decides as a group, not that everyone does work.

---

## 1. Decisions the meeting must make

| ID | Decision | Owner | Agenda | State | Notes |
|---|---|---|---|---|---|
| A-01 | Ratify or replace WP2's **seven** `LJA_GAP_*` thresholds | ALL | A1 | **OPEN** | Now implemented and measured — see the box below. Shipped as config so a later change costs nothing, but these defaults are what gets demoed. |
| A-26 | Decide whether the near-flat profiles in the supplied dataset are an artefact or a fact about students | ALL | A1 | **OPEN** | Raised by the WP2 measurement. Determines whether A-01 can be answered on this data at all, and whether a better dataset is a Sprint 4 ask of Scott. |
| A-02 | Define the "At Risk" cohort | ALL | A2 | **OPEN** | Scott confirmed no institutional number exists. Mechanism built; `/cohort/at-risk` is 404 and a test asserts that. Implementing the decision includes deleting that test. |
| A-06 | Decide which sprint calendar is authoritative | ALL | B1 | **OPEN** | Runbook says Sprint 3 = 24 Aug–6 Sep; `sprint-plan.md` says 7–20 Sep and calls that range Sprint 2. |
| A-08 | Confirm `Refs IOLG-<n>` as the commit trailer convention | ALL | B2 | **OPEN** | `S3-<n>` is the runbook's shorthand for work packages, not a Jira key. |
| A-10 | Adopt one people-numbering scheme, M1–M5 or T1–T5 | ALL | B3 | **OPEN** | No stated mapping between them. Nothing should assume they correspond. |
| A-11 | Decide whether `docs/adr/` exists, and what goes there versus in bundle READMEs | ALL | B4 | **OPEN** | WP2 is briefed to create it; `docs/README.md` says decision records live beside the code. Decide *before* WP2 lands. |
| A-12 | Ratify `pip-audit` as non-blocking, or make it blocking | ALL | B5 | **OPEN** | First real run found nothing, so tightening is cheap right now. |
| A-13 | Ratify deferring `E501`, or schedule the reformat | ALL | B5 | **OPEN** | Enforcing today means reformatting 41 lines in files no work package is touching. |
| A-15 | Authorise the `devenv/env.sh` correction ("all six of us" → five) | ALL | C2 | **OPEN** | Blocked by a contradiction *inside* the runbook: §8 asks for it, §9 puts `devenv/` out of scope until Sprint 4. Needs an explicit go-ahead, then A-24. |
| A-17 | Strike the "create GitHub Issues backlog" item, or confirm it as a second tracker | ALL | C4 | **OPEN** | An M5 Sprint 1 deliverable never done; the team is evidently on Jira. |
| A-22 | Agree the corrected coverage target — 80% on core mapping and gap logic is **already met** | ALL | C1 | **OPEN** | Core modules are at 98–100%. The 70% headline is `cli.py` and `dashboard/__main__.py` at 0%, which is 62% of all uncovered statements. Decide that Sprint 5 targets entry-point wiring, then A-25. |

### Background for A-01 and A-26 — the seven thresholds, and what measuring them showed

Set as `LJA_GAP_*` environment variables in `python/lja/config.py`, and mirrored as flags on
`python -m lja.cli` so they can be swept without editing a `.env`. There is no UI — that is A-27.

| Variable | Default | Meaning |
|---|---|---|
| `LJA_GAP_ABSOLUTE_FLOOR` | 50.0 | Below this is a gap regardless of profile — catches the uniformly weak student |
| `LJA_GAP_ABSOLUTE_CEILING` | 75.0 | At or above this is never a gap — catches the uniformly strong student |
| `LJA_GAP_RELATIVE_GAP_CUTOFF` | −1.0 | MAD units below the student's own median at which it becomes a gap |
| `LJA_GAP_RELATIVE_STRONG_CUTOFF` | +1.0 | MAD units above at which it counts as proficient |
| `LJA_GAP_MIN_COMPETENCIES` | 4 | Below this many, fall back to absolute and record that |
| `LJA_GAP_MIN_SPREAD` | 1.0 | MAD below this is a flat profile; fall back to absolute |
| `LJA_GAP_FALLBACK_PROFICIENT` | 65.0 | On the fallback path only, at or above this is proficient |

**Two findings the meeting needs before it can ratify anything.**

*The first draft of `MIN_SPREAD` was wrong, and only measuring caught it.* At 2.0, **60% of all
classifications fell back to "insufficient data"** and the relative path — the whole point of
tender requirement 4 — fired for **4.8%** of them. Measured MAD across all 150 profiles is median
**0.90** (Q1 0.52, Q3 1.40, max 3.80), so 2.0 excluded nine students in ten. It is now 1.0, which
gives relative 27.5% / ceiling 29.1% / insufficient 37.6% / floor 5.9%.

*The more important finding is about the data, not the threshold.* These profiles are nearly flat
**by construction** — each competency's attainment averages several assessments of a single
per-student baseline plus independent noise, with no per-competency ability term at all. Of the 71
gaps found relatively, the distance below the student's own median is: min 1.0, median 2.2, max
6.8 percentage points, and **25 of 71 sit under two points below their own median**. On this data
"your weakest competency" is often a difference too small to act on.

That is an argument about the dataset rather than the algorithm, and a warning against tuning
`MIN_SPREAD` down to manufacture gaps — 0.5 would classify 89% of students relatively while making
a one-point difference a confident verdict. Full workings in
[`docs/adr/0001-relative-gap-detection.md`](../adr/0001-relative-gap-detection.md).

**Note the blast radius before ratifying:** on the supplied dataset the change moves
students-with-at-least-one-gap from **20 to 58 of 150**. That is a large shift driven by numbers
nobody has agreed yet, which is why this should be settled before the project owner sees a demo.

## 2. Administrative follow-ups — no code, no ticket

| ID | Action | Owner | Agenda | State | Notes |
|---|---|---|---|---|---|
| A-03 | Enable branch protection on `main` — no direct pushes, ≥1 approving review, CI must pass | GitHub admin | A3 | **OPEN** | **S3-3 cannot close without this.** A repository setting; no code can apply it. |
| A-04 | Verify protection: throwaway PR with a failing test, confirm the merge is blocked, close it | T2 | A3 | **BLOCKED** | Blocked by A-03. Acceptance evidence for the CI ticket, not a ticket itself. |
| A-05 | Assign reviewers to PRs #4, #5, #6 | ALL | A4 | **OPEN** | DoD requires a reviewer other than the author; all three are Allan's. #5 is meant to be T5's entry point. |
| A-07 | State at the review that WP1 (CI) is a slipped **Sprint 1** item, not new delivery | T1 | B1 | **OPEN** | `sprint-plan.md` §3 had it as an M5 Sprint 1 task. Cheap honesty point. |
| A-09 | Supply the IOLG issue numbers for WP1, WP4 and the docs work | T1 | B2 | **OPEN** | Three commits carry `Refs S3-3`/`S3-7`/`S3-4` and will not link. Left as-is rather than force-pushing over open, green PRs; real keys go into the PR descriptions. |
| A-21 | Merge, close or assign PR #2 ("Apple Silicon setup guide") | ALL | C5 | **OPEN** | Open since 2026-08-16. |

## 3. Jira tickets to raise — closes when the ticket exists, not when the work is done

| ID | Raise a ticket for | Owner | Agenda | State | Notes |
|---|---|---|---|---|---|
| A-18 | Viewer-adjustable **chart** parameters, starting with histogram bin size | T5 | C5 | **OPEN** | Requested 2026-08-26. Scope to WP4 part 2. Presentation only — no recomputation. `histogram()` already takes `bin_width`/`lower`/`upper`, so the Python side needs no change; the work is a control plus client-side rebinning. Must preserve cross-cohort comparability, which is why bins are fixed today. |
| A-27 | Viewer-adjustable **gap-detection thresholds**, with a re-evaluation run that updates the page when it finishes | T5 + T1 | A1 | **OPEN** | Requested 2026-08-26. **Bigger than A-18 and should be a separate ticket** — see the note below. |
| A-19 | Bump `actions/checkout@v4` and `setup-python@v5` off deprecated Node 20 | T2 | C5 | **OPEN** | Warning only, non-breaking. |
| A-20 | Vendor Chart.js into `static/` instead of the CDN | T5 | C5 | **OPEN** | Charts currently need internet; the rest of the page degrades gracefully. Matches the local-first stance. |
| A-23 | Stop hardcoding the test count in the root README — derive it or drop it | T4 | C3 | **OPEN** | Wrong three times already: 18 → 54 → 69 → 87. |
| A-28 | Generate synthetic data with **measurable** SILOs — more students, more subjects, more assessments, and genuine per-competency ability variation | T4 + T1 | A1 | **OPEN** | The practical answer to A-26. Current generator cannot produce a profile relative gap detection can act on — the missing term is identified below, along with candidate libraries to investigate. |
| A-24 | Correct `devenv/env.sh` to five team members | T2 | C2 | **BLOCKED** | Blocked by A-15. One line. |
| A-25 | Correct the coverage narrative in `sprint-plan.md` and the READMEs | T4 | C1 | **BLOCKED** | Blocked by A-22 agreeing what the corrected target is. |

### Background for A-27 — why the threshold controls are not just another slider

A-18 changes how existing numbers are *drawn*. A-27 changes what the numbers *are*, and that is an
architectural shift worth naming before someone starts it.

**Today** the seven thresholds are environment variables read once at import, or CLI flags on
`python -m lja.cli`. Changing one means editing `.env` or passing a flag, re-running the pipeline,
and restarting the dashboard. There is no way to see the effect of a different cut-off without
leaving the browser.

**The good news:** re-running gap detection does **not** need the LLM. Clustering is the expensive
step and it is already cached in `output/silo_clustering.json`; `compute_gaps()` is pure and runs
over the full 150-student dataset in well under a second. So a "re-evaluate" button is genuinely
cheap — this is not a long-running job needing a queue, and the "updates when finished" behaviour
the request asks for may be simpler than expected.

**The catch, and the thing to decide deliberately:** `lja/dashboard/app.py`'s module docstring
currently promises the dashboard is *read-only over an already-computed run*, and
`create_app(dataset, gaps, clustering)` receives its gaps rather than producing them. Accepting
thresholds from a viewer makes the dashboard a thing that *computes* gaps, which:

- changes what a URL means — two people on the same page could be looking at different
  classifications, so any threshold state must be visible and shareable (query parameters rather
  than hidden session state), or figures stop being reproducible between team members;
- interacts directly with **A-01** — if thresholds become viewer-adjustable, "the default" still
  needs ratifying, and arguably matters more, because it is what everyone sees first;
- interacts with **WP3** — a page that recomputes on demand needs to keep saying, loudly, that the
  clustering underneath it is unreviewed;
- needs a guard against being used as an accidental grade-changing tool. The tender's guardrail is
  that mastery estimates are formative indicators, never official evaluations, and a UI that lets
  someone slide a threshold until a student stops having gaps is exactly the misreading to prevent.
  Whatever ships should make it obvious the viewer is exploring sensitivity, not setting policy.

**Suggested scope for the ticket:** thresholds in the URL as query parameters, a "re-evaluate"
control rather than live-on-drag (the recompute is cheap, but re-rendering on every pixel of a
slider is not), the active values displayed alongside every affected figure, and a one-click reset
to the ratified defaults. This also gives Sprint 5's sensitivity testing (S4-8's successor) a
usable interface rather than a shell loop — which may be the strongest argument for building it.

### Background for A-28 — what "measurable SILOs" actually requires

This is the practical answer to A-26. Relative gap detection needs students who are genuinely
**better at some competencies than others**. The supplied dataset does not contain such students,
and neither does anything `lja/data/synth_generator.py` can currently produce.

**The precise defect.** The generator draws one baseline per student and adds independent noise per
assessment:

```
score(student, assessment) = baseline(student) + noise
```

There is no term indexed by *competency*. Every competency is therefore an estimate of the same
underlying number, and within-profile variation is pure measurement noise — which is why the
measured MAD is a median of 0.90 percentage points, and why averaging several assessments per
competency shrinks it further. **Relative detection cannot work on data generated this way**, no
matter how the thresholds are set. Any gap it finds is noise, by construction.

**What is needed** is a student × competency interaction — a per-student *ability vector* rather
than a scalar:

```
score(student, competency, assessment)
    = μ  +  student_effect(student)          # overall ability
       +  competency_effect(competency)      # some competencies are harder for everyone
       +  ability(student, competency)       # ← THE MISSING TERM: individual strengths
       +  noise
```

The third term is the entire feature. Its standard deviation relative to the noise term is the
knob that decides whether gap detection has anything to detect, and it should be a generator
parameter so the team can produce datasets that are deliberately easy or hard. That also gives the
Sprint 4 validation harness (S4-8) real ground truth: the generator knows each student's true
weakest competency, so recovery rate becomes measurable rather than asserted. The existing
`--planted-gap-silos` mechanism is a crude special case of this and should be subsumed by it.

**Scale wanted alongside it:** more students (the current 150 is thin for distribution work), more
subjects than three, more assessments per subject, and more competencies per student than the
current uniform five — a varying count would also exercise `MIN_COMPETENCIES`, which currently
excludes nobody and is therefore untested against real data.

#### Candidate libraries and references to investigate

Listed as starting points from prior knowledge, **not verified against their current
documentation** — checking they are alive and suitable is part of this action.

| Candidate | Where | Why it is on the list |
|---|---|---|
| **Item Response Theory** — `mirt` (R), `py-irt`, `girth` (Python) | `philchalmers.github.io/mirt`, `eribean.github.io/girth` | The established psychometric model for exactly this problem: a latent ability per trait, plus item difficulty and discrimination. Nearest thing to a principled, defensible answer, and it is *the* literature an examiner will expect to see cited. **Highest priority.** |
| **Hierarchical / multilevel simulation** — PyMC, NumPyro | `pymc.io`, `num.pyro.ai` | Lets the model above be written down directly as random effects, with the student×competency term explicit and tunable. Most transparent option: the generating model is the documentation. |
| **Synthetic Data Vault (SDV)** | `sdv.dev` | Learns a joint distribution from real data and samples more of it. Useful *later*, once there is genuinely varied data to learn from — it cannot invent structure the source lacks, so it does not solve today's problem. |
| **copulas / CTGAN / TVAE** (within SDV) | `sdv.dev` | Preserve correlation structure between columns. Same caveat: only as good as the input's structure. |
| **scikit-learn** `make_*` generators | `scikit-learn.org` | Quick controlled covariance structures for unit-test fixtures. Not realistic enough for a demo dataset, but cheap. |
| **Faker** | `faker.readthedocs.io` | Names, IDs, dates only. **Explicitly not suitable for correlated numerics** — noted here so nobody reaches for it expecting scores. |

**Before building anything, ask Scott whether real de-identified attainment data can be obtained.**
Calibrating the generator's parameters against even a small sample of real profiles would settle
A-26 outright, and no amount of synthetic sophistication substitutes for knowing what real
within-student variation looks like. That question is cheap to ask and gates the rest.

## 4. Closed

| ID | Action | Owner | Agenda | Outcome |
|---|---|---|---|---|
| — | — | — | — | *Nothing closed yet — register opened 2026-08-26.* |
