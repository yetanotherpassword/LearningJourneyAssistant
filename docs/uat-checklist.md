# System and CLI acceptance checklist — IOLG-130

Prepared 28 September 2026 for Anup (T4), Sui Lung (T5), and Ayesha (T2,
IOLG-129). These are the six system rows, in the order required by the
Sprint 5 brief. Sui Lung's dashboard rows can be added to the same document.

**Result and Tester below are reserved for the live sprint review.** Local
checks are preliminary evidence, not a claim that Anup attended or
signed off the review. Use Pass, Fail, Blocked, or Not available in Result
at the review and add the tester's name/date. Failed expectations remain
findings even when a documented workaround succeeds.

Run commands from `python/` with the project's environment activated.
`<xlsx>` means `../data-fixtures/CSE_results_150_students_3_Subjects.xlsx`.
Keep the dataset, clustering cache, and review file together and record the
revision and chosen paths. Learning-plan generation additionally requires a
configured LLM; the reference cache removes the clustering call only.

| # | User story | Steps | Expected | Result | Tester | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Run the pipeline on the supplied workbook | Follow root README Quick start step 3: `python -m lja.cli <xlsx> --clustering-cache ../data-fixtures/reference-run/silo_clustering.json`. | `output/gap_report.csv` is written without error. | Not run at live review | Pending | Local check passed: 750 gap rows, 150 students, 24 persistent-gap rows; byte-identical to the committed reference report. |
| S2 | Run the pipeline on Moodle | Complete the read-only role, connection, mapping and seeded fixture prerequisites in the Python/SQL READMEs; run `python -m lja.cli --source moodle`. | A gap report is generated for the seeded subject. | Not run at live review | Pending | Local runtime check blocked: Docker daemon stopped and no configured Moodle instance supplied. The offline suite skips the live Moodle integration test. |
| S3 | Generate one student's learning plan | Run `python -m lja.plan <xlsx> STU0003`; when following S1's reference run, explicitly add `--clustering-cache ../data-fixtures/reference-run/silo_clustering.json` and configure the LLM. | `output/plans/learning_plan_STU0003.json` and `.md` are written; grounding checks pass. | Not run at live review | Pending | As written after S1, the brief's command exits 2 because `output/silo_clustering.json` does not exist. No new live-model generation was attempted without a configured provider. Validation of the ten existing saved plans passes; that does not replace this generation test. See UAT-01. |
| S4 | Export the results | Run `python -m lja.export <xlsx> --out output/export`; for S1's reference run, add `--clustering-cache ../data-fixtures/reference-run/silo_clustering.json`. Open/run `docs/export-sample.ipynb` from `docs/`. | `students.csv`, `competencies.csv`, `cohort.csv`, and `manifest.json` are written; the sample notebook reads its export and renders the chart. | Not run at live review | Pending | Export is available on this revision. The literal command exits 2 after S1; with the explicit cache it passes (150/750/5 CSV rows). All three notebook cells executed and the chart rendered. See UAT-01. |
| S5 | Staff review changes the warning | Have Istiaque start the dashboard on the demo cache and its adjacent review JSON after Sui Lung's decisions; reload the page. Record the rejected labels. Do not modify the all-confirmed reference fixture. | The AI-review banner appears and names the rejected clusters. | Not run at live review | Pending | Local disposable fixture showed the banner, but only a count: `1 AI-generated SILO cluster(s) have been rejected by staff.` It did not name Data Structures and Algorithms. Full expected behavior fails; see UAT-02. Repeat with the real demo review file. |
| S6 | Tests pass | Run `python -m pytest -q`. | Tests report passed with zero failures; report skips separately. | Not run at live review | Pending | Local full run: 258 passed, 1 skipped, 1 warning. Includes the seven IOLG-110 validation profiles. Live Moodle test is skipped unless explicitly enabled; this does not establish S2. |

## Preliminary execution record

- Date: 28 September 2026. Local preliminary execution; live tester pending.
- Base: `ffa53d54c65946d252e4e1f987c294da2e59da23`, plus IOLG-110's seven
  validation tests. No application code was changed.
- Platform: macOS arm64, Python 3.12.14, isolated virtual environment.
- Dependency deviation: local installation used `psycopg2-binary==2.9.12`
  because building the pinned `psycopg2==2.9.12` required an unavailable
  `pg_config`. Repository requirements remain unchanged. This is not the
  clean Ubuntu/Conda rebuild required by IOLG-118.
- Evidence: [selected command output and observations](sprints/sprint-5/uat/local-checks-2026-09-28.txt).
- Dashboard reference view opened in a browser with 150 students and 24
  students with a persistent gap. Its confirmed current clusters produced
  no review warning. The disposable rejected fixture produced the warning
  recorded above. Historical pending review entries for old clusters did
  not affect the current-cluster banner.

## UAT-01 — Default cache differs from Quick start's cache

Quick start successfully reads the committed reference cache but does not
copy it to `output/silo_clustering.json`. The later learning-plan and export
examples default to that missing path and exit 2. Preserve the explicit
`--clustering-cache ../data-fixtures/reference-run/silo_clustering.json`
argument when composing the steps. Export then works without a model call.
Learning-plan generation still needs an LLM. This is a documentation/setup
finding to reconcile with IOLG-114, not a reason to alter the reference fixture.

## UAT-02 — Review banner omits rejected cluster names

A temporary copy of the reference cache/review pair was used. Current
cluster `3cc7cf957629` (Data Structures and Algorithms) was moved from
confirmed to pending, then rejected using `lja.review`, with a note identifying
it as a local test. Starting the dashboard on that pair showed the warning
count but no cluster label. The CLI still blocked gap generation on the
rejected cluster. Thus the protection behavior and the banner's naming
requirement have different outcomes. Retest after the banner is amended or
the team explicitly changes the acceptance criterion.

## Live-review completion

Have Anup perform S1–S6 at the review, recording actual results and artifact
paths. Keep S2/S3 blocked until their runtime prerequisites exist. Combine
these rows with Sui Lung's dashboard cases and record defects before
submitting the combined IOLG-129 document for non-author review.
