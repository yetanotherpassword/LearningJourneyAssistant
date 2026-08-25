# Sprint 3 Implementation Runbook

**For:** Claude Code, working in `github.com/yetanotherpassword/LearningJourneyAssistant`
**Sprint:** IOLG Sprint 3, 24 Aug – 6 Sep 2026
**Companion:** `LJA_Sprint_Plan_3-6.pdf` (full sprint context, acceptance criteria, ownership)
**Repo state this was written against:** `410abb6`

Drop this file at `docs/sprint-3-implementation-runbook.md` and commit it, so the whole team can see
what was asked for and Claude Code can re-read it in later sessions.

---

## 0. How to start a session

Open Claude Code at the repository root and give it something like:

> Read `docs/sprint-3-implementation-runbook.md`. Work package **WP2** only. Follow the ground rules in
> §2 — branch, TDD, conventional commits, and stop at the escalation points rather than deciding for me.
> Start by reading the files listed under WP2 and telling me your plan before you write anything.

**One work package per session.** They land as separate branches and separate reviews. Asking for all
five at once produces one enormous unreviewable diff, which is the exact failure mode this sprint exists
to correct.

---

## 1. Orientation

Verified from a clean clone on 24 August, not assumed:

| Fact | Detail |
|---|---|
| Package root | `python/lja/` — 22 modules. Tests in `python/tests/` — 9 files. |
| Test suite | **69 tests, all passing.** Run from the `python/` directory. |
| Environment | conda env `lja`, Python 3.12, defined in `python/environment.yml`. Root `requirements.txt` is a full pinned pip freeze — usable directly by CI. |
| Entry points | `python -m lja.cli <workbook.xlsx>` and `python -m lja.dashboard` |
| Module layout | `llm/` (base, factory, anthropic_client, openai_compatible_client) · `data/` (excel_loader, synth_generator) · `model/` (silo_clustering, gap_detection, gap_evidence) · `dashboard/` (app, templates, static) |
| Config | `lja/config.py` — everything reads from `LJA_*` environment variables with defaults. **New settings go here, not inline.** |
| Absent | `.github/workflows/` (no CI at all) · `docs/compliance-checklist.md` |

**Read before writing.** This runbook describes intent; the code is the truth. Every work package below
lists the files to read first. If what you find contradicts this document, say so rather than forcing the
code to match the plan.

**Match the house style.** The existing modules carry substantial design-rationale docstrings — see the
top of `gap_detection.py`, which explains an approximation and flags it for the project owner. That is
the standard. A module docstring that only restates the function names is below the bar for this repo.

---

## 2. Ground rules

**Branching.** One branch per work package: `s3-3/ci-pipeline`, `s3-6/relative-gap-detection`, and so on.
Never commit directly to `main` — that is what went wrong with the initial code landing, and WP1 exists
partly to make it impossible.

**Commits.** Conventional Commits, matching the repo's existing style:

```
type(scope): subject

Body explaining why, not what. Wrap at ~72 chars.

Refs IOLG-<n>
Co-Authored-By: Claude <noreply@anthropic.com>
```

Types in use: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`. Ask for the Jira key if it hasn't
been given — do not invent one, and do not write `IOLG-nn` literally.

**Tests before code.** The subject teaches deriving test cases from acceptance criteria before
implementation, and the acceptance criteria are in the sprint plan. Write the failing tests first, show
them failing, then implement. This is not ceremony here: WP2 changes the meaning of every downstream
feature, and the tests are how that change stays honest.

**Never:**
- commit `.env`, API keys, or anything under `output/`
- reformat or reorganise files you aren't otherwise changing — it destroys the diff for reviewers
- rewrite the `silo_clustering.py` prompt or the coverage validator unless the work package says to
- invent Moodle table or column names; the SQL in `sql/` is the reference and it is annotated
- add an embedding stage — that is a Sprint 4 decision the team hasn't made yet (see §9)

**Docs are part of Done.** If behaviour or setup changed, the relevant `README.md` changes in the same
PR. `python/README.md` currently says 54 tests; it is 69. Fix the count in whichever PR you touch it in.

---

## 3. Order of work

```
WP1  CI pipeline            ── independent, do first (protects everything after it)
WP2  Relative gap detection ── blocks WP4; changes what every downstream feature means
WP3  Confirmation gate      ── independent of WP2, can run in parallel
WP4  Dashboard views        ── needs WP2's threshold config and classification fields
WP5  README truth pass      ── last, once the others have settled
```

WP2 before WP4 is a hard dependency: the strengths view is threshold-driven from WP2's configuration, and
building it against the current absolute thresholds means building it twice.

---

## 4. WP1 — CI pipeline and scanning *(Jira S3-3, owner Ayesha)*

**Read first:** `requirements.txt`, `python/environment.yml`, `python/tests/`

**Goal.** Every pull request to `main` is linted, tested, and scanned before it can merge.

Create `.github/workflows/ci.yml` with three jobs:

1. **lint** — `ruff check` over `python/`. Add a `[tool.ruff]` section to a `pyproject.toml` at `python/`
   if none exists; keep the rule set modest to start (`E`, `F`, `I`) so the first run doesn't produce
   four hundred findings nobody reads.
2. **test** — Python 3.12, `pip install -r requirements.txt`, `pytest` from `python/` with coverage
   reporting. **Report coverage; do not enforce a threshold yet.** The tender commits to 80% on core
   mapping and gap logic, but that is Sprint 5 work — a gate that fails on day one gets switched off by
   day three.
3. **security** — secret scanning across full history (gitleaks or trufflehog) and dependency scanning
   (`pip-audit`). Tender requirement 9 is Mandatory and names both. A clean history scan was confirmed
   on 24 August, so this should pass immediately; the point is that it keeps passing.

Add a status badge to the root `README.md`.

**Verification:** open a throwaway PR containing a deliberately failing test and confirm the merge is
blocked. Then close it.

> **Human step, not code.** Branch protection on `main` — no direct pushes, one approving review, CI must
> pass — is a GitHub repository setting. Claude Code cannot apply it. Say so explicitly when the workflow
> lands, and don't mark the ticket Done without it.

---

## 5. WP2 — Relative gap detection *(Jira S3-6, owner Allan)*

**Read first:** `python/lja/model/gap_detection.py` (all of it, including the docstring),
`python/tests/test_gap_detection.py`, `sql/moodle_attainment_extraction.sql` Query 6

**Why this exists.** The lodged tender, requirement 4, promises gap detection based on *variability
within an individual student's profile* — explicitly "rather than raw pass or fail thresholds."
`gap_detection.py` classifies against `DEFAULT_LOW_THRESHOLD = 50.0` and `DEFAULT_HIGH_THRESHOLD = 65.0`,
which is precisely the mechanism excluded. This is a direct contradiction with a document already
submitted, not a refinement.

### The design problem

Pure relative classification has two degenerate cases, and both produce output that is worse than the
current absolute logic. Handle them explicitly or the feature is a regression:

**Uniformly weak student.** Every competency sits around 35%. There is almost no within-profile
variance, so relative logic finds no outliers and reports *no gaps* — to a student who is failing
everything. Unacceptable.

**Uniformly strong student.** Every competency sits around 90% except one at 85%. Relative logic flags
the 85% as a gap. Also unacceptable, and worse than useless — it teaches students to distrust the tool.

**Too few competencies.** A student evidenced against two or three competencies has no meaningful spread
to reason about. Whatever the statistic, it is noise at that n.

### Proposed approach — implement this, but see §9

Keep `compute_gaps()`'s existing weighted-attainment calculation untouched. It is sound and the
approximation it makes is already documented. Replace only `_classify()`.

1. Group each student's competency attainments into their own profile.
2. Compute a robust centre and spread across that profile. **Prefer median and median absolute deviation
   over mean and standard deviation** — students have roughly 4–8 competencies, and at that n a single
   catastrophic result drags the mean far enough to hide everything else.
3. Compute each competency's position relative to that centre, normalised by spread.
4. Classify by relative position, then apply two absolute guards:
   - **Floor:** any competency below the floor is a gap regardless of relative position. Catches the
     uniformly weak student.
   - **Ceiling:** any competency above the ceiling is never a gap regardless of relative position.
     Catches the uniformly strong student.
5. When spread is near zero, or the student has fewer than a minimum number of competencies, fall back to
   absolute classification and **record that you did**.

**Preserve the persistent-versus-isolated distinction.** `subjects_evidencing >= 2` currently separates
a gap that recurs across subjects from one confined to a single subject. That distinction survives the
change — it is orthogonal to how the gap was detected, and Sprint 5's study-strategy generation depends
on it.

### Record the basis, not just the verdict

Add a field to `CompetencyGap` capturing *how* each classification was reached — relative position,
absolute floor, absolute ceiling, or insufficient data. Two reasons this is not optional:

- Tender requirement 5 promises every displayed figure is traceable to a source record. "You have a gap
  here" with no visible basis is not traceable.
- Sprint 5's feedback evidence panel renders exactly this.

`CompetencyGap` is a frozen dataclass consumed by `dashboard/app.py`, the templates, and
`gap_evidence.py`. Adding fields will ripple; follow the ripple rather than working around it.

### Configuration

All tunables into `lja/config.py` as `LJA_*` environment variables with defaults, one source of truth.
No literal threshold anywhere in `gap_detection.py`.

`sql/moodle_attainment_extraction.sql` Query 6 carries the same 50/65 values. **Do not port the new
logic to SQL this sprint** — the Moodle path isn't wired until Sprint 4. Update Query 6's comment block
to record that classification semantics now live in Python, that the SQL thresholds are legacy, and that
reconciling them is a Sprint 4 task. An annotated divergence is fine; a silent one is not.

### Tests

`test_gap_detection.py` will break. **Re-express those tests against the new semantics — do not delete
them.** Then add cases for: uniformly weak, uniformly strong, single catastrophic result among strong
ones, near-zero spread, below-minimum competency count, and the persistent/isolated split surviving the
change. Hand-calculate the expected values and put the arithmetic in the test docstring; Anup's
validation harness in Sprint 4 (S4-8) builds directly on these.

### Write the ADR

`docs/adr/` — create it if absent. Record the problem, the algorithm, the chosen defaults, the degenerate
cases and how they're guarded, and the fact that Scott has confirmed there is no institutional "at risk"
number to match, so this is the team's decision to defend. The implementation report will draw on this
directly.

---

## 6. WP3 — Staff confirmation gate *(Jira S3-5, owner Istiaque)*

**Read first:** `python/lja/model/silo_clustering.py`, `python/lja/cli.py`,
`python/tests/test_silo_clustering.py`, `python/README.md` on `--refresh-clustering` and
`--extra-instructions`

**Goal.** Every competency cluster carries a review state, and no gap report is produced from
unreviewed LLM output without saying so.

**Three states:** `pending`, `confirmed`, `rejected`.

**Storage — the important design decision.** Review state persists *alongside*
`output/silo_clustering.json`, never inside it. The clustering file is a regenerable cache; the review
decisions are human judgements that cost staff time. Use a sibling file such as
`output/silo_clustering.review.json`.

**Fingerprint the clustering.** Store a hash of the clustering the reviews were made against. When the
clustering is regenerated and the hash no longer matches, reviews **do not carry over** — they revert to
pending, and the superseded review file is preserved rather than overwritten. Without this, a staff
member confirms cluster set A, someone re-runs `--refresh-clustering`, and cluster set B silently
inherits the approval. That is the failure this whole gate exists to prevent, so it cannot be the thing
the gate does.

**Review CLI:** `python -m lja.review` — list clusters with their SILO members and current state, set a
state, attach a note. Record who reviewed and when.

**Gate in `lja.cli`:** warn loudly when a gap report is driven by `pending` clustering. Provide
`--allow-unconfirmed` so scripted runs remain possible. **Warn, don't block** — a hard block on a tool
nobody has reviewed yet makes the system unusable during development, and the CLI is currently the only
way to see anything.

**Rejected must lead somewhere.** A rejected cluster routes to the documented rework path
(`--extra-instructions` plus `--refresh-clustering`, both of which already exist). A state that leaves
the user stuck is worse than no state.

**Tests:** one per transition, plus the fingerprint-invalidation case, plus the CLI warning appearing and
`--allow-unconfirmed` suppressing it.

---

## 7. WP4 — Dashboard views *(Jira S3-7 and S3-13, owner Sui Lung, paired with Allan)*

**Depends on WP2.** Do not start until relative gap detection is merged.

**Read first:** `python/lja/dashboard/app.py`, `templates/base.html`, `templates/student.html`,
`static/style.css`, `python/tests/test_dashboard.py`

Two of the four views tender requirement 5 promises:

**S3-7 — current understanding level.** Per-student mastery across *all* competencies, not only the
gaps. The data already exists in `compute_gaps()` output; this is a presentation change, not a pipeline
stage.

**S3-13 — strengths.** High-attainment competencies as a first-class view. Threshold-driven from WP2's
configuration — no second hardcoded number, and no reimplementation of the classification logic in the
template.

**Constraints.**

- `create_app()` already receives `dataset`, `gaps` and `clustering`. Build view models in `app.py`; keep
  logic out of Jinja templates.
- Reuse the semantic colour palette already in `style.css`. If a chart colour and a badge colour for the
  same classification can drift apart, they will.
- Surface WP2's classification basis where a figure is shown, so the traceability requirement holds.
- Extend `test_dashboard.py` using the existing in-memory fixtures. No new fixture framework.

**This is Sui Lung's entry point into the codebase** and the pairing with Allan is deliberate. Explain
what you're doing and why in the PR description, at a level someone new to the codebase can follow.
Terse commits here are a failure of the work package, not efficiency.

---

## 8. WP5 — README truth pass *(fallout from Jira S3-4, owner Anup)*

Anup's clean-machine rebuild will produce a list of places the documentation is wrong or insufficient.
Work from that list, not from guesses.

Known already: `python/README.md` says 54 tests; there are 69. Also correct `devenv/env.sh`, which says
"all six of us" — the team is five (T1–T5), and the tender's §10 is the authority.

Rewrite forward-looking language into what is now true. The pattern that caused the original problem was
documentation asserting things about code nobody had verified; the fix is describing only what has been
run.

---

## 9. Stop and ask — do not decide these alone

| Decision | Why it isn't yours |
|---|---|
| The actual threshold values in WP2 — relative cut-off, floor, ceiling, minimum competency count | Implement them as configuration and propose defaults with reasoning. The numbers are a team decision that gets defended in the implementation report and sensitivity-tested in Sprint 5. |
| Whether to add an embedding pre-pass | Tender requirement 2 promises embeddings with LLM adjudication; there is no embedding stage. The team decides at planning whether to build it in Sprint 4 or document the deviation. **Not Sprint 3, either way.** |
| Anything touching Moodle extraction, the SQL beyond comments, or `devenv/` | Sprint 4, owned by Ayesha. |
| Changing what `compute_gaps()` computes, as opposed to how it classifies | The weighted-attainment approximation is documented and was flagged to the project owner. Changing it silently invalidates that conversation. |
| Descoping anything | The descope order is in the sprint plan and descopes are declared out loud at the review. |

If you hit one of these mid-task, stop and report rather than picking the reasonable-looking option.
A blocked task with a clear question is a better outcome than a merged assumption.

---

## 10. Before opening any PR

```bash
cd python
pytest -q                     # 69 + your new tests, all green
ruff check .                  # once WP1 has landed
git log --oneline origin/main..HEAD    # commits conventional, Jira key present
git diff origin/main --stat            # only files this work package should touch
```

Then check against the Definition of Done:

- Merged via PR reviewed by someone other than the author — the review is the point, not the merge
- New logic carries unit tests; existing tests re-expressed rather than deleted
- Relevant README updated in the same PR
- No secrets; `.env.example` updated if new configuration was added
- Demoable — reachable from the dashboard or a documented CLI entry point
- Acceptance evidence attached to the Jira issue, as the tender's §3 governance clause promises
- Jira ticket moved as the work completes, not the night before the sprint review

The sprint review demo is driven by Anup from his own clean clone. If it only runs on the machine it was
written on, the work package isn't finished.
