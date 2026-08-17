# LJA — Sprint Plan (Sprints 1–5)

**Status:** active specification. Update this file at the end of every sprint —
the "current" column in each sprint table should reflect what actually shipped,
not just what was planned.

## 0. The one decision this whole plan hangs off

**We build to a working MVP, not a throwaway demo.** Every sprint review is a
live demo against the real running system — Docker Moodle, real (or supplied)
subject structure, the actual extraction → mapping → gap-detection → dashboard
pipeline. No slide decks standing in for a feature, no hand-wired mock data
paths presented as if they were the real pipeline. If a feature isn't running
end-to-end on real code, it isn't done, regardless of how it looks in a demo
script.

The corollary: **scope flexes, the pipeline doesn't.** When time runs short,
we cut a whole feature (see §8, Descope policy) rather than fake depth on a
feature that's actually a mock. A smaller set of genuinely working features
beats a full checklist of features that don't survive being run twice.

This plan targets **Sprints 1–5, two weeks each, 2026-08-10 → 2026-10-18**.
Adjust the calendar to your unit's actual submission/trade-show date — this
schedule assumes roughly two weeks of buffer after Sprint 5 for whatever the
university requires on top of the working system (final report, trade show
setup, etc.).

## 0.5. Amendment — dataset arrived early, Excel path built (2026-08-11)

On the 2026-08-11 call, Scott supplied a ready-extracted Excel workbook
(`data-fixtures/CSE_results_150_students_3_Subjects.xlsx` — 3 real subjects,
150 synthetic students, SILOs, scores, feedback) instead of the `.mbz`
backups Sprint 1/2 originally planned around. In response, the following got
built and run end-to-end the same day, ahead of schedule:

- `python/lja/llm/` — the full provider-agnostic LLM layer from Sprint 1's
  M3 row, including the `OpenAICompatibleClient` retry/validation path
  (planned as a "smoke test"; actually load-bearing sooner than expected).
- `python/lja/data/excel_loader.py` — an extraction layer for this dataset.
- `python/lja/model/silo_clustering.py` + `gap_detection.py` — Sprint 2's
  walking-skeleton logic (M2's row), built against the Excel path instead of
  `lja_criterion_score` from Moodle SQL.
- `python/lja/cli.py` + 18 passing pytest tests.

**This does not replace the Moodle-path work in M1's Sprint 1/2 rows below —
it runs in parallel.** The production system still needs to read a live
Moodle instance; Scott's Excel export was this phase's data, not a
permanent substitute. Treat the rows below as still real, now de-risked by
having a working reference implementation to port them against.

**One real finding worth carrying into planning:** local LLM quality on the
cross-subject SILO clustering task varies enormously — an 8B model failed
outright (grouped by subject, semantically inert) even after prompt
strengthening; a 30B model produced genuinely correct cross-subject
reasoning but needed a coverage validator to catch it silently dropping
SILOs. Whichever model M3 ends up using for real, budget time to validate
its output quality specifically, not just that the pipeline runs.

## 1. Roles & workload allocation

Five people, five stable ownership areas. Everyone writes their own tests and
touches their own bundle's README — ownership means "the person who says yes
or no on PRs in this area and carries the pager for its bugs," not "the only
person allowed to edit it."

| Owner | Area | Primary paths |
| --- | --- | --- |
| **M1** | Moodle integration & extraction | `python/lja/extraction/`, `sql/`, devenv liaison |
| **M2** | Data model & gap engine | `python/lja/model/`, `lja_criterion_silo_map`, `lja_criterion_score`, the assistant's own database |
| **M3** | AI / LLM layer | `python/lja/llm/`, learning-plan generation, quiz generation, study-strategy recommendations |
| **M4** | Dashboard | `python/lja/dashboard/`, the four mastery views, UX |
| **M5** | DevOps, QA, security, docs | `devenv/`, CI, testing infrastructure, compliance checklist, `docs/`, handover |

Fill in real names against M1–M5 before Sprint 1 planning.

**Scrum Master rotates — one sprint each, in owner order (M1 → M5).** With
five sprints and five people this lands exactly once per person; no one
carries facilitation and a full feature load in the same sprint. The Scrum
Master for a sprint runs standups, the sprint review, and the retro; they
still own their area's engineering work.

| Sprint | Scrum Master |
| --- | --- |
| 1 | M1 |
| 2 | M2 |
| 3 | M3 |
| 4 | M4 |
| 5 | M5 |

## 2. Engineering ground rules (apply to every sprint, not repeated per-sprint below)

**Definition of Done, every backlog item:**

- Merged via PR into `main` with at least one review from a **different**
  owner than the author.
- `pytest` passes locally; new logic has unit test coverage; anything in
  `extraction/` or `model/` has at least one integration test that runs
  against the seeded Docker Moodle instance.
- The relevant bundle README is updated if setup or behaviour changed —
  not deferred to "docs later."
- No secrets committed; `.env.example` updated if new config was added.
- **Demoable**: reachable from the dashboard or a documented CLI entry
  point. Code that only exists as an unused function is not done.

**Branching:** `main` is protected. Feature branches `feat/<owner>-<short-desc>`.
PR required, one review minimum, squash merge. No direct pushes to `main`.

**Backlog:** GitHub Issues + a Project board, created in Sprint 1. Epics map
1:1 to the proposal's must-haves; every story carries acceptance criteria
before it's pulled into a sprint.

**Ceremonies:** standup 2–3×/week (async on off-days is fine), sprint review
demo to Scott at every sprint boundary from the running system, retro
straight after with one concrete change actually adopted, backlog refinement
mid-sprint so the next planning session isn't cold.

**Testing tiers:**

- Unit tests (pytest) — every owner, every PR, runs in CI.
- Integration tests against seeded Docker Moodle — owned by the component
  that touches Moodle data (M1, M2); run locally as a mandatory pre-PR
  check from Sprint 2 onward, added to CI once M5 confirms Docker-in-CI is
  workable (Sprint 1 spike — see below).
- Manual regression pass — full team, Sprint 4 and Sprint 5.

## 3. Sprint 1 — Foundations & Spikes (2026-08-10 – 2026-08-23)

**Goal:** resolve the two open architecture spikes, get every team member's
environment working end-to-end, stand up the backlog and CI, and land the
first slice of a typed extraction layer — against synthetic data, since the
requested dataset (see `data-fixtures/README.md`) may not have arrived yet.

**Entry criteria:** repo as-is (devenv, sql, python spike, data-fixtures).

| Owner | Work items |
| --- | --- |
| M1 | Wrap `moodle_probe.py` into a typed `python/lja/extraction` client (site info, courses, enrolled users, grade items, assignments). Implement the DB-side reader for SQL Queries 1 & 2 against the `lja_reader` role. Spike the competency-mechanism decision: run Queries 3 & 4 against the CSE5IDP fixture (and real data if it has landed) and record which mechanism, if either, returns rows. |
| M2 | Design and migrate `lja_criterion_silo_map` and `lja_criterion_score` into the assistant's **own** Postgres database (not Moodle's) — SQLAlchemy + Alembic recommended. Stub the mapping loader (no automation yet, a script is fine). |
| M3 | **Done outside the original plan — see §0.5.** `python/lja/llm` exists: `LLMClient` protocol, `AnthropicClient`, `OpenAICompatibleClient`, `.env` wiring. Remaining for Sprint 1: verify the `AnthropicClient` path against a real API key (only the local path has been run live so far) and own the "budget time to validate LLM output quality" item from §0.5. |
| M4 | Spike the dashboard stack. **Recommendation to validate:** FastAPI + Jinja2 templates + Chart.js — same language as the rest of the stack, minimal new tooling for a 5-person team on a 10-week clock, and screenshot/demo-friendly for the trade show. Scaffold `python/lja/dashboard` serving a single placeholder page. If the team picks differently, record the decision and why. |
| M5 | Stand up CI (GitHub Actions: lint + pytest on every PR). Create the full GitHub Issues backlog — one epic per proposal must-have, broken into stories with acceptance criteria. Draft `docs/compliance-checklist.md` from the proposal's admin-only checklist (legal, security, financial, technical, HR, communication, QA, documentation sections). Chase the dataset request status with Scott (see `data-fixtures/README.md` checklist) — this is the #1 external dependency and every day it slips is a day the walking skeleton runs on weaker fixtures. |

**Sprint 1 Definition of Done / review demo:**

- Every team member can run `devenv/bootstrap.sh` + `seed.sh` and reach
  Moodle locally.
- Backlog exists in GitHub with acceptance criteria on every story.
- `python/lja/llm` answers a trivial prompt via **both** configured backends.
- The competency-mechanism decision (Outcomes vs Competency framework vs
  neither) is written down in `sql/README.md`, with the query output that
  justifies it.
- CI is green on `main`.

**Risk:** dataset hasn't arrived. **Mitigation:** proceed on synthetic
fixtures (`tool_generator` + hand-seeded rubric fillings); the walking
skeleton in Sprint 2 does not block on real data — swap it in later without
architecture changes.

## 4. Sprint 2 — Walking Skeleton (2026-08-24 – 2026-09-06)

**Goal, revised per §0.5:** the backend half of the walking skeleton
(extraction → clustering → gap detection) is already done for the Excel
path — confirmed working, not aspirational: a full run against
`qwen3-vl:30b` produced 7 correct cross-subject competency groups from 13
SILOs and found 6 students with a genuine persistent gap in "Data
Structures Knowledge and Application" (evidenced across `CSE1OOF` and
`CSE2ALG`, 40–50% attainment). **Sprint 2's real goal is now the dashboard**
— rendering that output — plus the Moodle-DB path for M1, which the Excel
path does not replace.

| Owner | Work items |
| --- | --- |
| M1 | The Moodle-DB path is still real work: loader that populates `lja_criterion_score` from SQL Query 2's output, and the rubric-fills DB-read path end-to-end against seeded fillings — the trickiest join in the codebase (see `sql/README.md`'s two gotchas: `grading_instances.itemid` and the `status = 1` filter, plus the confirmed `mdl_`/`m_` table-prefix discrepancy between our own two environments). Pair with M5 if it slips past two days. |
| M2 | **Mostly done — see §0.5.** `python/lja/model/silo_clustering.py` and `gap_detection.py` exist and are tested (18 pytest cases, all offline). Remaining: a `confirmed_by_staff`-equivalent gate for the LLM's clustering output — right now nothing stops an unreviewed clustering from driving a gap report, unlike the Moodle path's `lja_criterion_silo_map` design. Also: port `gap_detection.py`'s logic to consume `lja_criterion_score` once M1's Moodle loader exists, so both paths share one gap engine. |
| M3 | LLM layer done (§0.5) and now proven against a real semantic task, not just a smoke test. Next: the "explain this gap" prompt template, grounded in the gap report, as a demonstration hook — even if the dashboard doesn't call it yet. |
| M4 | **Done, first slice** — `python/lja/dashboard/` (FastAPI + Jinja2 + Chart.js, per the Sprint 1 stack spike). A student list plus a per-student page — attainment chart, gap table with classification badges — sourced live from `compute_gaps()`, not a hardcoded student; the dashboard never calls the LLM itself. Remaining for later sprints: multiple students/subjects side by side, the other three dashboard views, and a `confirmed_by_staff` review action (see M2's item below) surfaced here once it exists. |
| M5 | Write the integration test that loads → clusters → gap-detects → asserts the dashboard page renders, using the Excel path as the primary CI-friendly test (no Docker Moodle dependency) — add the Docker Moodle integration test once M1's loader exists. Update every README touched this sprint. |

**Sprint 2 Definition of Done / review demo:** open the dashboard, see one
real student's actual gap data — computed live by the full pipeline, Excel
path acceptable, Moodle path a bonus if M1 lands it this sprint. If any
layer is stubbed, the sprint is not done, no matter how the UI looks.

## 5. Sprint 3 — Multi-subject Competency Model + Full Dashboard (2026-09-07 – 2026-09-20)

**Goal:** expand from one subject to the full candidate set (real dataset if
it has arrived, expanded synthetic if not), ship all four dashboard views,
and land the first LLM-generated feature — learning plans.

| Owner | Work items |
| --- | --- |
| M1 | Extend extraction to every candidate subject. If the `.mbz` backups have arrived (see `devenv/README.md`'s restore procedure), restore and validate against them; log any schema surprises in `sql/README.md`. Turn the mapping loader from a manual script into an automated job. |
| M2 | Add the "strengths" (high attainment) and "progress trends" (attainment over time / across attempts) queries alongside gaps. Add a `confirmed_by_staff` toggle workflow for `lja_criterion_silo_map` rows — a CLI/admin script is sufficient for MVP; a UI is not required. |
| M3 | First LLM feature: personalised learning-plan generation, grounded in M2's gap output, via the layer built in Sprint 1. Write a grounding test suite that asserts generated plans only ever reference SILOs and subjects present in the input — this is the anti-hallucination constraint from the proposal, and it needs a test, not just a prompt instruction. |
| M4 | Build out all four dashboard views (understanding level, strengths, gaps, progress trends) across multiple subjects and students. Add a dev-mode student selector — full auth is out of scope for MVP. |
| M5 | Security pass 1: confirm `lja_reader` is genuinely read-only, API tokens carry only the capabilities listed in `python/README.md`, no secrets in git history (`git log -p` audit or `trufflehog`/similar). Extend CI to run the Sprint 2 integration test on every PR if not already there. |

**Sprint 3 Definition of Done / review demo:** multi-subject dashboard, all
four views live, at least one student's learning plan generated end-to-end
from real gap data, demoed against real or expanded-synthetic data.

## 6. Sprint 4 — Adaptive Quizzes, Study Strategies, Hardening Pass 1 (2026-09-21 – 2026-10-04)

**Goal:** land the remaining must-haves, then stop adding features. This is
the last sprint where new feature work is allowed at all — the descope
trigger below is not a suggestion.

| Owner | Work items |
| --- | --- |
| M1 | Capacity permitting: spike the custom Moodle plugin exposing rubric fills as a web service (`python/README.md`'s stretch option 2) — the most trade-show-impressive deliverable if there's room. Otherwise: support extraction bugs surfaced by others. |
| M2 | Refine cross-subject aggregation based on real usage from the Sprint 3 review. |
| M3 | **Adaptive quiz generation**: grounded in identified gaps, aligned to SILOs, validated against the mapping table so generated questions only target SILOs the student is actually weak in. **Study-strategy recommendations**: evidence-based, tied to gap classification (isolated vs persistent), citing the SILO and the evidence (subjects/assessments) behind each suggestion — never a bare assertion with no traceable source. |
| M4 | Surface quizzes and study strategies in the dashboard. UX polish pass only — no redesigns this late. |
| M5 | Full regression pass across everything shipped so far. Security pass 2 against `docs/compliance-checklist.md` — close every item or explicitly defer with a written reason. Start the handover document skeleton. |

**Descope trigger (non-negotiable):** at the Sprint 4 review, if quiz
generation or study-strategy recommendations are not genuinely working end
to end, **cut the feature and say so at the review** — do not carry
unfinished feature work into Sprint 5. Sprint 5 has zero feature-development
capacity by design (see §8).

## 7. Sprint 5 — Feature Freeze, Hardening, Documentation, Handover (2026-10-05 – 2026-10-18)

**Goal:** no new features, full stop. Bug fixes, documentation, final
security/compliance sign-off, demo rehearsal, handover package.

| Owner | Work items |
| --- | --- |
| M1–M4 | Bug bash against the full must-have list — each owner fixes bugs in their own component only, cross-component bugs get a named owner at standup. Rewrite every bundle README's forward-looking language ("what it is going to become") as past tense ("what it is") — the root README's architecture section in particular. |
| M5 | Finalise the compliance checklist sign-off. Write the handover document: architecture overview, the competency-mechanism decision and rationale, the rubric-fills-via-database caveat stated plainly (this is not API-mediated and the handover has to say so), known limitations, a "not yet built" list for the nice-to-haves, and a runbook for re-seeding and redeploying from scratch. Coordinate a demo rehearsal against the actual running system — not slides. Refresh the trade-show deck from the real dashboard. |

**Sprint 5 Definition of Done:** the system runs cleanly from a fresh
`bootstrap.sh` → `seed.sh` → (backup restore if applicable), demoed live
end-to-end, every README current, compliance checklist signed off, handover
document complete.

## 8. Descope policy

If the schedule slips, cut whole features in this pre-agreed order — do not
thin out the pipeline to keep every feature nominally present:

1. **Adaptive quiz generation** — cut first. Highest complexity-to-value
   ratio of the four AI features, and the one most likely to look
   plausible while quietly not being grounded.
2. **Study-strategy recommendations** — cut second, only if quizzes'
   removal alone doesn't recover enough time.
3. **Personalised learning plans** — cut only as a last resort; this is
   the feature closest to the project's stated purpose (turning feedback
   into actionable improvement).

**Never cut, under any schedule pressure:** secure Moodle integration, the
parsing engine, the competency model, gap detection, and the dashboard. These
are the walking skeleton from Sprint 2 — by Sprint 3 every other feature
depends on them, and a working dashboard with honest gap detection is a
defensible MVP on its own even if every AI feature above it is cut.

## 9. Cross-sprint artefacts (living documents, not one-off deliverables)

| Artefact | Created | Maintained until |
| --- | --- | --- |
| GitHub Issues / Project board | Sprint 1 | Every sprint |
| Competency-mechanism ADR (in `sql/README.md`) | Sprint 1 | Amend if evidence changes |
| Dashboard-stack ADR (in `python/README.md` or `docs/`) | Sprint 1 | — |
| `docs/compliance-checklist.md` | Sprint 1 (draft) | Sprint 5 (signed off) |
| Handover document | Sprint 4 (skeleton) | Sprint 5 (complete) |
| Trade-show deck (`docs/TradeShow/`) | Existing draft | Refreshed Sprint 5 |

## 10. Assumptions to confirm before Sprint 1 planning

- Actual sprint start date and the real submission/trade-show deadline —
  this plan assumes 2026-08-10 start and roughly two weeks of buffer after
  2026-10-18.
- M1–M5 → real team member names.
- The dashboard stack recommendation in Sprint 1 (FastAPI + Jinja2 +
  Chart.js) — confirm or override at the Sprint 1 spike, not later.
- Whether Docker-in-CI is viable for Moodle integration tests, or whether
  that tier stays a manual pre-PR check for the whole project.
