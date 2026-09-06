# Sprint 3 Implementation Runbook — Revision 2

**For:** Claude Code, working in `github.com/yetanotherpassword/LearningJourneyAssistant`
**Sprint:** IOLG Sprint 3 — **dates disputed, see §A.2**
**Supersedes:** `docs/sprint-3-implementation-runbook.md` (r1), which remains the record of what was
originally asked for. This revision does not replace r1's intent; it records what has since been built,
what was decided, and what r1 got wrong about the repository.
**Repo state this was written against:** `95ba39d` (WP1, branch `s3-3/ci-pipeline`) and `65705af`
(WP4 part 1, branch `s3-7/dashboard-views`), both branched from `410abb6`.

> **Section numbers are not work-package numbers, but §4–§8 are the work packages.** This tripped people
> up against r1, so: §0–§3 and §9–§10 are cross-cutting rules that apply to every work package; §4 is WP1,
> §5 is WP2, §6 is WP3, §7 is WP4, §8 is WP5. A reference to "§9" is the stop-and-ask list, not a ninth
> work package. The mapping table is in §A.1.

---

> **Status 6 September 2026 — read `docs/meetings/actions.md` for the live record; this file is a
> point-in-time revision.** WP1 merged (PR #4) with branch protection on and verified (A-03, A-04);
> WP2 merged (PR #7); S3-9 merged (PR #9); PRs #5 (WP4 part 1), #6 (this document) and #8 (WP3) are
> open. Test counts below are historical — they are no longer quoted in the READMEs (A-23).

## 0. How to start a session

Unchanged from r1, and it still matters:

> Read `docs/sprint-3-implementation-runbook-r2.md`. Work package **WP2** only. Follow the ground rules
> in §2 — branch, TDD, conventional commits, and stop at the escalation points rather than deciding for
> me. Start by reading the files listed under WP2 and telling me your plan before you write anything.

**One work package per session.** Two have now landed as two branches with two reviewable diffs, which is
the outcome this rule exists to produce. Keep it.

---

## A. What changed since r1

### A.1 Section-to-work-package map

| § | Work package | Jira | Owner | Status at r2 |
|---|---|---|---|---|
| §4 | WP1 — CI pipeline | S3-3 | Ayesha | **Done 6 Sep** — merged (PR #4), protection on, verified (A-03/A-04) |
| §5 | WP2 — Relative gap detection | S3-6 | Allan | Not started — **now blocking two things** |
| §6 | WP3 — Confirmation gate | S3-5 | Istiaque | Not started |
| §7 | WP4 — Dashboard views | S3-7, S3-13 | Sui Lung + Allan | **Partially delivered**, see §7 |
| §8 | WP5 — README truth pass | S3-4 | Anup | Partially absorbed into the above |

### A.2 Contradictions found in r1, not yet resolved

> **Revised 2026-09-05.** This section was written against `docs/sprint-plan.md` and r1 only. The
> actual authority — *Sprint Plan Rev 5, 24 Aug* — was never in the repository, and it had already
> settled three of the four items below the day before r2 was written: the calendar (Rev 5 §3),
> the `Refs IOLG-nn` trailer convention (§10), and the retirement of M1–M5 (§1). It also records the
> tender's six-vs-five inconsistency itself and authorises the `devenv/env.sh` fix. Both plans are
> now committed: [`LJA_Sprint_Plan_3-6_rev5.pdf`](LJA_Sprint_Plan_3-6_rev5.pdf) (binding Sprint 3,
> indicative 4–6) and [`LJA_Sprint_Plan_A-C_rev3.pdf`](LJA_Sprint_Plan_A-C_rev3.pdf) (epic
> structure and Jira terminology). **Read Rev 5 before this file.** The one item Rev 5 does not
> resolve is the §8/§9 conflict on `devenv/` — it authorises the fix, which is enough.

r1's §1 says "the code is the truth… if what you find contradicts this document, say so." Three did.

**The sprint dates disagree with the sprint plan.** r1's header says *IOLG Sprint 3, 24 Aug – 6 Sep 2026*.
`docs/sprint-plan.md` §5 dates Sprint 3 as **2026-09-07 – 2026-09-20**, and 24 Aug – 6 Sep is **Sprint 2**
there (§4). Either the schedule slipped a sprint and the plan is stale, or r1 mislabelled the sprint.
Nobody has decided. Related: standing up CI was M5's **Sprint 1** task (`sprint-plan.md` §3), so WP1 is a
slipped Sprint 1 item rather than new work — worth saying out loud at the review.

**The issue tracker is ambiguous.** r1 cites Jira keys (`S3-3`, `S3-6`), its commit template says
`Refs IOLG-<n>`, commit `410abb6` used `Refs IOLG-11`, and `sprint-plan.md` refers to a **GitHub Issues**
backlog rather than Jira at all. **Decision taken for now:** commits use `Refs S3-<n>`, the IDs r1 cites
against each work package. This needs ratifying before it spreads further.

**People are numbered two incompatible ways.** `sprint-plan.md` refers only to **M1–M5** and never maps
them to names. The tender §10 uses **T1–T5**: T1 Allan Campton, T2 Ayesha Mosaddeque, T3 Istiaque Bhuiyan,
T4 Anup Tumbalam Gooty, T5 Sui Lung Tang. Whether M-numbers and T-numbers share an ordering is stated
nowhere. Do not assume they do. The tender is the authority on team composition (five, not six).

**r1 contradicts itself on `devenv/`.** §8 instructs correcting `devenv/env.sh`'s "all six of us"; §9
lists "anything touching … `devenv/`" as a Sprint 4 stop-and-ask owned by Ayesha. The file is therefore
**still wrong and still untouched**. It is a one-line comment fix and someone should be told to make it.

### A.3 Facts r1 stated that are no longer true

r1's §1 orientation table was accurate on 24 August. Current verified state:

| Fact | r1 said | Now |
|---|---|---|
| Test suite | 69 tests | **87 tests**, all passing, run from `python/` |
| CI | `.github/workflows/` absent | on `main` since 6 Sep (PR #4); badge live |
| Lint config | none | `python/pyproject.toml`, ruff `E`/`F`/`I` at width 120 |
| `python/README.md` | claimed 54 tests | corrected to 87 |
| Root `README.md` | claimed 18 and 54 tests | both corrected to 69, **now stale again at 87** |
| `docs/adr/` | absent | `docs/adr/0001-relative-gap-detection.md` on `main` (PR #7) |
| `docs/compliance-checklist.md` | absent | still absent |

> The root README's counts are stale *again* because WP1 fixed them to 69 before WP4 added 18 more. This
> is exactly why r1's §2 says fix the count in whichever PR you touch it in, and why a hardcoded count in
> prose is a bad idea. Consider deriving it, or stop quoting a number.

---

## 1. Orientation

As r1 §1, with §A.3's corrections applied. Two additions:

**Environment.** The conda env is `lja` (Python 3.12). On a machine with several environments, `conda run
-n lja` may resolve elsewhere — invoke the interpreter by path if `pytest` appears to be missing.

**The dashboard has grown a third route.** `lja/dashboard/` is now `app.py`, `stats.py`, four templates and
two static files. `create_app(dataset, gaps, clustering)` takes three arguments, not two.

---

## 2. Ground rules

Unchanged from r1, plus what practice has settled:

**Commit trailer.** `Refs S3-<n>` (see §A.2), and `Co-Authored-By: Claude <noreply@anthropic.com>` — the
form the root README's "AI tool usage" section already documents.

**Branch names in use.** `s3-3/ci-pipeline`, `s3-7/dashboard-views`. Continue the pattern:
`s3-6/relative-gap-detection`, `s3-5/confirmation-gate`.

**"Never reformat files you aren't otherwise changing" has teeth.** It is the reason `E501` is not
enforced (§4) and it held through both landed work packages. Do not quietly relax it to make a linter green.

---

## 3. Order of work

```
WP1  CI pipeline            ── DONE 6 Sep: merged, protection on, verified
WP2  Relative gap detection ── NOT STARTED; now blocks WP4's remainder AND the At-Risk cohort
WP3  Confirmation gate      ── NOT STARTED; independent, can run in parallel
WP4  Dashboard views        ── PART 1 LANDED (cohorts, statistics, sorting)
                               PART 2 BLOCKED on WP2 (S3-7 understanding level, S3-13 strengths, At Risk)
WP5  README truth pass      ── partially absorbed; residue listed in §8
```

**WP2 is now the critical path.** It was always going to block WP4; it now also blocks a feature the team
has explicitly asked for (the At-Risk cohort). Nothing else in the sprint has two things waiting on it.

---

## 4. WP1 — CI pipeline and scanning *(S3-3, owner Ayesha)* — **DONE 6 Sep**

Landed on `s3-3/ci-pipeline` as `95ba39d`. Three independent jobs in `.github/workflows/ci.yml`:

| Job | Does | Blocking |
|---|---|---|
| lint | `ruff check` over `python/`, rules `E`/`F`/`I` | yes |
| test | Python 3.12, `pip install -r requirements.txt`, pytest with coverage | yes on failure |
| security | gitleaks over **full history**, plus `pip-audit` | secret scan yes; audit **no** |

**Decisions taken, all reversible, all needing a reviewer's eye:**

- **`line-length = 120`, not ruff's default 88.** Measured, not preferred: at 88 this codebase reports 208
  `E501`s *and seven spurious `I001`s* — isort only wants to explode those single-line imports because they
  overflow the configured width. At 120 the import findings vanish, leaving two genuine ones, both fixed.
- **`E501` selected but ignored.** Enforcing it means reformatting 41 lines in modules no work package is
  touching, which §2 forbids. Remove the ignore in the same change that brings lines to width, and let that
  change touch nothing else.
- **Coverage reported, not gated** — as r1 directed. Add `--cov-fail-under` when the number is met.
- **`pip-audit` non-blocking.** This one is *not* r1's instruction and needs ratifying. Its result depends
  on the CVE feed rather than on the diff, so an advisory published overnight would block every unrelated PR
  the next morning. Triage the first real findings, then flip `continue-on-error` to `false`.
- **`libpq-dev` installed in the test job.** `requirements.txt` pins `psycopg2`, not `psycopg2-binary`,
  which ships as an sdist and compiles against libpq. Without the headers the job fails with a bare
  "pg_config executable not found". Changing the pin instead is a Sprint 4 dependency decision, not CI's.

> **Resolved 6 Sep — protection enabled and verified (A-03, A-04); kept for the record.** Branch protection on `main` — no direct
> pushes, one approving review, CI required — is a GitHub repository setting no code can apply. Until it is
> switched on, these jobs are advisory and a red build is still mergeable. r1's verification step (open a
> throwaway PR with a deliberately failing test, confirm the merge is blocked, close it) is also
> outstanding, and cannot pass before protection exists.

**Unverified:** the security job has never run. It downloads gitleaks and runs `pip-audit`, and the
machine this was built on had no network. Expect the first real run to be where the download URL and the
audit output get tested.

---

## 5. WP2 — Relative gap detection *(S3-6, owner Allan)* — **NOT STARTED, CRITICAL PATH**

r1 §5 stands in full: read it rather than this section for the design. Three things r2 adds.

**Use `statistics.median`.** `lja/dashboard/stats.py` already computes a median — over students within a
cohort, a different population to WP2's competencies within a student, but the same operation. It calls the
standard library deliberately so WP2 can too. **Do not write a second median.** If WP2 needs a MAD helper,
put it beside that one rather than growing a private implementation in `gap_detection.py`.

**Population versus sample is now a precedent.** `stats.py` uses population variance and standard
deviation, on the reasoning that a cohort is every student it describes rather than a sample drawn from a
wider body, and `test_variance_is_population_not_sample` pins it. WP2 should either follow that reasoning
or say why a student's competency profile is different. Two conventions in one codebase is the bad outcome.

**The dashboard is now waiting on your configuration.** WP4 part 2 and the At-Risk cohort both need WP2's
threshold config and classification-basis field. When you add `CompetencyGap`'s basis field, `app.py`'s
`view_model()` and `_cohort_body.html` are where it surfaces.

Everything else — the degenerate cases, the floor/ceiling guards, preserving persistent-versus-isolated,
the `sql/` Query 6 comment update, the ADR under `docs/adr/` — is exactly as r1 §5 describes.

---

## 6. WP3 — Staff confirmation gate *(S3-5, owner Istiaque)* — **NOT STARTED**

r1 §6 stands unchanged. Independent of WP2; can run in parallel with it, and given WP2 is now the critical
path, running WP3 alongside is the obvious parallelism.

One note from WP4: the dashboard is still strictly read-only and has no confirm control. `python/README.md`
says the natural home for one is a per-competency action on the student page. That remains true and remains
unbuilt.

---

## 7. WP4 — Dashboard views *(S3-7 and S3-13, owner Sui Lung, paired with Allan)* — **PART 1 LANDED**

### What landed (`65705af`, branch `s3-7/dashboard-views`)

Not the two tickets r1 scoped — this was a team request that arrived mid-sprint and is WP2-independent:

- **Cohort drill-down.** Every stat-strip figure links to `/cohort/<key>`, rendering the same student table
  and statistics over that subset, with a sentence stating what put students in it (requirement 5's
  traceability). Cohorts are registered in `_COHORTS` in `app.py`; adding one is a registry entry.
- **Descriptive statistics.** Mean, median, population variance and standard deviation, min/max, quartiles
  and IQR, plus a distribution histogram and a classification breakdown. Arithmetic is in
  `lja/dashboard/stats.py` as pure functions, tested in `tests/test_dashboard_stats.py` with the working
  hand-calculated in each docstring.
- **Sortable columns**, client-side progressive enhancement in `static/sort.js`. The server still renders
  student-id order, so the table is correct without JavaScript.

18 new tests; suite now 87. Verified against the real 150-student dataset: 6 students in the persistent-gap
cohort, whose mean (46.93%) and spread (σ 2.73) differ sharply from the whole cohort's (68.20%, σ 10.99).

### Still to do — blocked on WP2

- **S3-7, current understanding level.** Per-student mastery across *all* competencies, not only gaps.
- **S3-13, strengths.** Threshold-driven from WP2's configuration. No second hardcoded number, and no
  reimplementation of classification in the template.
- **The At-Risk cohort** — see §9, this is a decision before it is a task.
- **Surface WP2's classification basis** wherever a figure is shown, so traceability holds.

### Constraints, still in force

Build view models in `app.py`, not Jinja — `view_model()` is the pattern to extend. Reuse the semantic
palette; charts already read the same CSS custom properties the badges use. Extend `test_dashboard.py` with
the existing in-memory fixtures. **This is still Sui Lung's entry point** and the pairing with Allan is
still deliberate — part 1 landing early does not change that, and part 2 is the better onboarding anyway
because it exercises WP2's data model.

---

## 8. WP5 — README truth pass *(S3-4, owner Anup)* — **PARTIALLY ABSORBED**

Done in passing, because §2 requires fixing counts in whichever PR touches the file:

- Root `README.md`: "18 passing tests" and "54 passing tests" → 69 (WP1). **Now stale at 87.**
- `python/README.md`: 54 → 87; `create_app(dataset, gaps)` → `create_app(dataset, gaps, clustering)`;
  cohort, statistics and sorting behaviour documented (WP4).

Residue for Anup:

- `devenv/env.sh` still says "all six of us"; the team is five (tender §10). **Blocked by r1's own
  §8/§9 contradiction — see §A.2.** Someone should simply authorise the one-line fix.
- `docs/compliance-checklist.md` still absent.
- Root README's test count will keep going stale. Derive it or drop it.
- Anup's clean-machine rebuild (S3-4) has not happened; that list is still the real input to this work
  package, and this section is not a substitute for it.

---

## 9. Stop and ask — do not decide these alone

r1's table stands. Two items are now live rather than hypothetical:

| Decision | State |
|---|---|
| **The At-Risk cohort definition** | **Live and blocking a requested feature.** The dashboard has the mechanism and deliberately no tile. `/cohort/at-risk` returns 404 and `test_at_risk_cohort_is_not_registered_yet` asserts that absence, so adding it forces the decision to be recorded. Candidates discussed: ≥1 persistent gap; any gap persistent or isolated (matches `_AT_RISK_CLASSIFICATIONS`, already in `app.py` for a different purpose); or a low overall average, the only option WP2 cannot disturb. **Due at WP2 planning.** |
| WP2's threshold values — relative cut-off, floor, ceiling, minimum competency count | Unchanged from r1. Implement as configuration, propose defaults with reasoning, let the team choose. |
| **The sprint dates and the issue tracker** | New — see §A.2. Neither is a code decision, both affect every commit trailer and every status report. |
| Whether to add an embedding pre-pass | Unchanged. Not Sprint 3, either way. |
| Anything touching Moodle extraction, SQL beyond comments, or `devenv/` | Unchanged, but note the §8 contradiction in §A.2. |
| Changing what `compute_gaps()` computes, versus how it classifies | Unchanged. |
| Descoping anything | Unchanged. Declared out loud at the review. |

---

## 10. Before opening any PR

```bash
cd python
pytest -q                              # all green (counts no longer quoted -- A-23)
ruff check .                           # clean; config is python/pyproject.toml
git log --oneline origin/main..HEAD    # conventional commits, Refs S3-<n> present
git diff origin/main --stat            # only files this work package should touch
```

Definition of Done, unchanged from r1 — merged via PR reviewed by someone other than the author; new logic
carries unit tests and existing tests are re-expressed rather than deleted; relevant README updated in the
same PR; no secrets and `.env.example` updated if configuration was added; demoable from the dashboard or a
documented CLI entry point; acceptance evidence on the Jira issue; ticket moved as work completes.

**Jira state, spelled out because it was asked:** a work package is *In Progress* while it is uncommitted or
unpushed — nothing is inspectable, so nothing is Ready for Review. It becomes *Ready for Review* when the
branch is pushed and a PR is open. It becomes *Done* only when the full Definition of Done is met, which
requires a reviewer other than the author. **S3-3 additionally cannot close on the workflow alone** — branch
protection is part of that ticket and only a repo admin can apply it.

The sprint review demo is driven by Anup from his own clean clone. If it only runs on the machine it was
written on, the work package isn't finished.
