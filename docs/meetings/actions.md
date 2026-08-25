# Actions Register

**Running register across all meetings — not per-meeting, and not rewritten.** Add rows, change
states, record outcomes inline. An action closed in a later meeting keeps its original ID so the
decision trail survives.

**States:** `OPEN` · `IN PROGRESS` · `BLOCKED` · `DONE` · `DROPPED` (with a reason)

Owners use the tender §10 numbering: T1 Allan · T2 Ayesha · T3 Istiaque · T4 Anup · T5 Sui Lung.
`ALL` means it needs a group decision, not that everyone does work.

---

## Open — blocking work in progress

| ID | Action | Owner | Raised | State | Notes |
|---|---|---|---|---|---|
| A-01 | Ratify or replace WP2's four thresholds: floor 50%, ceiling 75%, relative cut-off −1.0 MAD, minimum 4 competencies | ALL | Agenda A1 | **OPEN** | Blocks WP2 completion, therefore WP4 part 2 and A-02. Shipped as `LJA_*` config, so changing later is a config edit — but the defaults are what gets demoed. |
| A-02 | Decide the "At Risk" cohort definition | ALL | Agenda A2 | **OPEN** | Scott confirmed no institutional number exists. Mechanism is built; `/cohort/at-risk` is 404 and a test asserts the absence. Deleting that test is part of implementing the decision. |
| A-03 | Enable branch protection on `main` — no direct pushes, ≥1 approving review, CI must pass | GitHub admin | Agenda A3 | **OPEN** | **S3-3 cannot close without this.** Not code; a repository setting. |
| A-04 | Run the branch-protection verification: throwaway PR with a failing test, confirm merge is blocked, close it | T2 | Agenda A3 | **BLOCKED** | Blocked by A-03. |
| A-05 | Assign reviewers to PRs #4, #5, #6 | ALL | Agenda A4 | **OPEN** | DoD requires a reviewer other than the author; all three are Allan's. #5 is intended as T5's entry point into the codebase. |

## Open — conventions

| ID | Action | Owner | Raised | State | Notes |
|---|---|---|---|---|---|
| A-06 | Decide which sprint calendar is authoritative, then correct the other document | ALL | Agenda B1 | **OPEN** | Runbook says Sprint 3 = 24 Aug–6 Sep; `sprint-plan.md` says 7–20 Sep and calls 24 Aug–6 Sep Sprint 2. |
| A-07 | Announce at the review that WP1 (CI) is a slipped **Sprint 1** item, not new delivery | T1 | Agenda B1 | **OPEN** | `sprint-plan.md` §3 had it as an M5 Sprint 1 task. Honesty point, cheap to state. |
| A-08 | Confirm `Refs IOLG-<n>` as the commit trailer convention | ALL | Agenda B2 | **OPEN** | Board is `latrobecomsci.atlassian.net`, project **IOLG**. `S3-<n>` is runbook shorthand for work packages, not a Jira key. |
| A-09 | Supply the IOLG issue numbers for WP1, WP4 and the docs work | T1 | Agenda B2 | **OPEN** | Three commits carry `Refs S3-3`/`S3-7`/`S3-4` and will not link. Left as-is rather than force-pushing over open, green PRs; the real keys go in the PR descriptions instead. |
| A-10 | Adopt one people-numbering scheme (M1–M5 or T1–T5) and correct the other document | ALL | Agenda B3 | **OPEN** | No stated mapping between them anywhere. Do not assume they correspond. |
| A-11 | Decide whether `docs/adr/` exists, and what belongs there versus in bundle READMEs | ALL | Agenda B4 | **OPEN** | WP2 is briefed to create it; `docs/README.md` says decision records live beside the code. Decide before WP2 lands, not after. |
| A-12 | Ratify `pip-audit` as non-blocking, or make it blocking | ALL | Agenda B5 | **OPEN** | First real run found nothing, so tightening is cheap right now. |
| A-13 | Ratify deferring `E501`, or schedule the reformat | ALL | Agenda B5 | **OPEN** | Enforcing today means reformatting 41 lines in files no work package is touching. |

## Open — corrections

| ID | Action | Owner | Raised | State | Notes |
|---|---|---|---|---|---|
| A-14 | Correct the coverage narrative in `sprint-plan.md` and the READMEs | T4 | Agenda C1 | **OPEN** | Core mapping and gap logic are at **98–100%**; the tender's 80% target is met. The 70% headline is `cli.py` and `dashboard/__main__.py` at 0%, which is 62% of all uncovered statements. Sprint 5 should target entry-point wiring. |
| A-15 | Authorise the one-line fix to `devenv/env.sh` ("all six of us" → five) | ALL | Agenda C2 | **OPEN** | Blocked by a contradiction *inside* the runbook: §8 asks for it, §9 puts `devenv/` out of scope until Sprint 4. Needs an explicit go-ahead. |
| A-16 | Stop hardcoding the test count in the root README — derive it or drop it | T4 | Agenda C3 | **OPEN** | Wrong three times already: 18 → 54 → 69 → 87. |
| A-17 | Strike the "create GitHub Issues backlog" item, or confirm it as a second tracker | ALL | Agenda C4 | **OPEN** | An M5 Sprint 1 deliverable never done; the team is evidently on Jira. |
| A-18 | Build viewer-adjustable chart parameters, starting with histogram bin size | T5 | Agenda C5 | **OPEN** | Requested 2026-08-26. Scoped to WP4 part 2. `histogram()` already takes `bin_width`/`lower`/`upper`, so the Python side needs no change. Must preserve cross-cohort comparability — that is why bins are fixed today. |
| A-19 | Bump `actions/checkout@v4` and `setup-python@v5` off deprecated Node 20 | T2 | Agenda C5 | **OPEN** | Warning only, non-breaking. |
| A-20 | Vendor Chart.js into `static/` instead of loading from CDN | T5 | Agenda C5 | **OPEN** | Charts currently need internet; everything else on the page degrades gracefully. Matches the project's local-first stance. |
| A-21 | Merge, close or assign PR #2 ("Apple Silicon setup guide") | ALL | Agenda C5 | **OPEN** | Open since 2026-08-16. |

## Closed

| ID | Action | Owner | Raised | State | Outcome |
|---|---|---|---|---|---|
| — | — | — | — | — | *Nothing closed yet — this register was opened 2026-08-26.* |
