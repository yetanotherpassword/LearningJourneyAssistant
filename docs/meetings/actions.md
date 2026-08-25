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
| A-01 | Ratify or replace WP2's four thresholds — floor 50%, ceiling 75%, relative cut-off −1.0 MAD, minimum 4 competencies | ALL | A1 | **OPEN** | Blocks WP2, therefore WP4 part 2 and A-02. Shipped as `LJA_*` config so a later change costs nothing — but these defaults are what gets demoed. |
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
| A-18 | Viewer-adjustable chart parameters, starting with histogram bin size | T5 | C5 | **OPEN** | Requested 2026-08-26. Scope to WP4 part 2. `histogram()` already takes `bin_width`/`lower`/`upper`, so the Python side needs no change. Must preserve cross-cohort comparability — that is why bins are fixed today. |
| A-19 | Bump `actions/checkout@v4` and `setup-python@v5` off deprecated Node 20 | T2 | C5 | **OPEN** | Warning only, non-breaking. |
| A-20 | Vendor Chart.js into `static/` instead of the CDN | T5 | C5 | **OPEN** | Charts currently need internet; the rest of the page degrades gracefully. Matches the local-first stance. |
| A-23 | Stop hardcoding the test count in the root README — derive it or drop it | T4 | C3 | **OPEN** | Wrong three times already: 18 → 54 → 69 → 87. |
| A-24 | Correct `devenv/env.sh` to five team members | T2 | C2 | **BLOCKED** | Blocked by A-15. One line. |
| A-25 | Correct the coverage narrative in `sprint-plan.md` and the READMEs | T4 | C1 | **BLOCKED** | Blocked by A-22 agreeing what the corrected target is. |

## 4. Closed

| ID | Action | Owner | Agenda | Outcome |
|---|---|---|---|---|
| — | — | — | — | *Nothing closed yet — register opened 2026-08-26.* |
