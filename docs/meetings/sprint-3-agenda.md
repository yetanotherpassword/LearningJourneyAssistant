# Sprint 3 — Team Meeting Agenda

**Prepared:** 2026-08-26 · **Meeting date:** TBC · **Prepared by:** Allan (T1), from Sprint 3 implementation
**Related:** [`docs/sprint-3-implementation-runbook-r2.md`](../sprint-3-implementation-runbook-r2.md) §A.2 · actions register in [`actions.md`](actions.md)

Everything below was hit while implementing WP1 and WP4. None of it was decided unilaterally —
the runbook's §9 is explicit that a blocked task with a clear question beats a merged
assumption, so each item was left open with the reasoning recorded next to where it bites.

**Sections A and B are blocking work in progress. Section C is not, but compounds if ignored.**

---

## A. Blocking right now — decide at this meeting

### A1. WP2 threshold values *(owner: Allan · blocks WP2 → WP4 part 2 → the At-Risk cohort)*

Relative gap detection needs four numbers, and §9 puts them with the team because they get
defended in the implementation report and sensitivity-tested in Sprint 5:

| Setting | Proposed | Reasoning |
|---|---|---|
| Absolute floor | 50% | The Fail/Pass boundary. Below it is a gap regardless of the student's own profile — otherwise a uniformly weak student is told they have no gaps. |
| Absolute ceiling | 75% | The Distinction boundary. Above it is never a gap — otherwise a student on 90% everywhere gets their 85% flagged, which teaches them to distrust the tool. |
| Relative cut-off | −1.0 MAD | One median-absolute-deviation below the student's own median. |
| Minimum competencies | 4 | Below this there is no meaningful spread; fall back to absolute and record that it happened. |

**Decision needed:** ratify, or supply different numbers. They are configuration
(`LJA_*` environment variables), so changing them later is a config edit, not a code change —
but the defaults are what ships and what gets demoed.

### A2. The "At Risk" cohort definition *(owner: team · blocks a feature already requested)*

Scott confirmed there is **no institutional "at risk" number** to match, so this is ours to
choose and defend. The dashboard has the mechanism built and deliberately no tile;
`/cohort/at-risk` returns 404 and a test asserts that absence so it cannot be added silently.

Candidates: one or more **persistent** gaps (recurs across 2+ subjects); **any** gap, persistent
or isolated (matches the existing `_AT_RISK_CLASSIFICATIONS` constant, though that is currently
used for a different purpose); or a **low overall average**, which is the only option WP2's
thresholds cannot disturb.

**Decision needed:** pick one, or explicitly defer again and accept the tile stays absent.

### A3. Branch protection on `main` *(owner: whoever holds GitHub admin)*

**S3-3 cannot close without this.** CI is merged-ready and green, but a workflow cannot enforce
itself: until an admin enables "no direct pushes, at least one approving review, CI must pass",
the jobs are advisory and a red build is still mergeable. This is a repository setting, not code.

The runbook's verification step — open a throwaway PR with a deliberately failing test, confirm
the merge is blocked, close it — is also outstanding and cannot pass until protection exists.

### A4. Who reviews the three open PRs *(owner: team)*

The Definition of Done requires **a reviewer other than the author** — "the review is the point,
not the merge". PRs [#4](https://github.com/yetanotherpassword/LearningJourneyAssistant/pull/4),
[#5](https://github.com/yetanotherpassword/LearningJourneyAssistant/pull/5) and
[#6](https://github.com/yetanotherpassword/LearningJourneyAssistant/pull/6) are all authored by
Allan. #5 in particular is meant to be Sui Lung's entry point into the codebase.

**Decision needed:** assign reviewers, or consciously record a departure from the DoD.

---

## B. Conventions that are actively causing errors

### B1. Sprint dates disagree by a full sprint

The runbook header says *Sprint 3, 24 Aug – 6 Sep 2026*. `sprint-plan.md` §5 dates Sprint 3 as
**7–20 Sep**, and 24 Aug – 6 Sep is **Sprint 2** there. Related: CI was an M5 **Sprint 1** task
in the plan, so WP1 is a *slipped* item rather than new work — that should be said out loud at
the review rather than presented as fresh delivery.

**Decision needed:** which calendar is authoritative; then correct the other.

### B2. Jira key convention — `IOLG-<n>`, not `S3-<n>`

Now partly resolved: the board is `latrobecomsci.atlassian.net`, project key **IOLG**, board 2326.
So `S3-3`, `S3-6`, `S3-7` are the **runbook's internal shorthand for work packages, not Jira
keys**. Real keys are `IOLG-<number>`, consistent with `Refs IOLG-11` on commit `410abb6`.

Three commits already carry `Refs S3-3` / `S3-7` / `S3-4` and will not link to anything. They
were left as-is rather than force-pushing over open, green PRs for a metadata fix.

**Decision needed:** confirm `Refs IOLG-<n>` going forward, and supply the IOLG numbers for the
three landed work packages so the PR descriptions can carry the real keys.

### B3. People are numbered two incompatible ways

`sprint-plan.md` refers only to **M1–M5** and never names them. The tender §10 uses **T1–T5**:
T1 Allan Campton, T2 Ayesha Mosaddeque, T3 Istiaque Bhuiyan, T4 Anup Tumbalam Gooty,
T5 Sui Lung Tang. Whether the two orderings correspond is stated nowhere, so nothing should
assume it.

**Decision needed:** adopt one scheme and correct the other document.

### B4. Where do decision records live?

WP2 is briefed to create `docs/adr/`, but `docs/README.md`'s stated convention is that decision
records live in the bundle README next to the code they affect. Both cannot be right.

**Decision needed:** ADRs for cross-cutting algorithm decisions with bundle READMEs for local
ones, or no `docs/adr/` and WP2's record goes in `python/README.md`.

### B5. Two CI gates deliberately left soft — ratify or tighten

- **`pip-audit` does not block.** Unlike the secret scan, its result depends on the CVE feed
  rather than the diff, so an advisory published overnight would block every unrelated PR the
  next morning. First real run found **nothing**, so tightening it now is cheap.
- **`E501` (line length) is measured but not enforced.** Enforcing means reformatting 41 lines
  in modules no work package is touching, which the ground rules forbid as it destroys the diff.

**Decision needed:** ratify both as-is, or schedule the tightening.

---

## C. Corrections and housekeeping — resolve by assignment, not discussion

### C1. The 80% coverage target is aimed at the wrong thing

First CI run reports **70% overall**, but the tender's commitment is 80% on *core mapping and
gap logic*, and that is **already met**:

| Module | Coverage |
|---|---|
| `silo_clustering.py` (mapping) | **100%** |
| `gap_evidence.py` | **100%** |
| `dashboard/app.py` | **100%** |
| `excel_loader.py` | 99% |
| `gap_detection.py` (gap logic) | **98%** |
| `cli.py` | **0%** |
| `dashboard/__main__.py` | **0%** |

`cli.py` and `__main__.py` are 129 of the 207 uncovered statements — 62% of everything missing.
Sprint 5's coverage work should target **entry-point wiring**, not more algorithm tests.
This is good news that is currently being reported as bad news.

### C2. `devenv/env.sh` still says "all six of us" — the team is five

Blocked by a contradiction inside the runbook itself: §8 asks for the fix, §9 puts `devenv/`
out of scope until Sprint 4. It is a one-line comment. **Someone just needs to authorise it.**

### C3. The root README's test count keeps going stale

It has now been wrong three times (18 → 54 → 69 → 87). Derive it, or stop quoting a number.

### C4. Is the GitHub Issues backlog item obsolete?

`sprint-plan.md` made "create the full GitHub Issues backlog" an M5 **Sprint 1** deliverable. It
was never done, and the team is evidently on Jira. **Decision needed:** strike the item, or
confirm GitHub Issues is a second tracker (and say why).

### C5. Smaller items

- **Interactive charts** — requested: viewer-adjustable histogram bin size (slider or similar),
  and other parameters. Scoped to WP4 part 2. Must preserve cross-cohort comparability, which is
  why the bins are currently fixed.
- **Node 20 deprecation** — `actions/checkout@v4` and `setup-python@v5` raise warnings. Non-breaking; bump in a later pass.
- **Chart.js loads from a CDN**, so charts need internet. Vendoring it into `static/` would match the project's local-first stance.
- **PR #2 ("Apple Silicon setup guide") has been open since 2026-08-16** — merge, close, or assign.
