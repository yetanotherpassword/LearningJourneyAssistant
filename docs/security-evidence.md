# Security evidence — IOLG-111

Recorded 28 September 2026 against `main` revision
`ffa53d54c65946d252e4e1f987c294da2e59da23`. For review by
Anup (T4) and Ayesha (T2, IOLG-128). Scope: the six checks in the Sprint 5
brief, supporting Tender Requirements 1 and 9.

**Status: partial evidence; IOLG-111 remains open.** The GitHub scanner
results below were retrieved from the completed main-branch run. No Moodle
role, database, token, or checksum test has been performed in this session.
The local Docker daemon is stopped, and Ayesha's test environment and probe
output are not available. A source-code declaration of read-only access is
not proof of database enforcement.

## Results for the compliance checklist

These six checks support the original **Security and risk** items in
`docs/compliance-checklist.md`: checks 1–5 support SE-4; check 6 supplies
current scanner evidence for SE-1. All 40 original checklist rows are retained
without adding these six as new requirements. SE-1 stays Open because this
current scan does not establish its original before-first-push criterion.
SE-4 stays Open until its runtime evidence is collected. T2/T4 are the current
security-check partners; original checklist owners are preserved separately.

| Item | Owner (T1–T5) | Status (Done / Open / Deferred) | Evidence (file path, PR number, Jira key, or “pending IOLG-111”) |
| --- | --- | --- | --- |
| 1. Create the dedicated `lja_reader` role and SELECT grants | T2 + T4 | Open | 2026-09-28: pending IOLG-111. Capture the five statements' actual success output and date from the seeded development database; setup instructions are in `sql/README.md`, not execution evidence. |
| 2. Confirm that the reader cannot update `m_user` | T2 + T4 | Open | 2026-09-28: pending IOLG-111. No permission-denied line has been observed. Record the connected role and complete database error from the attempted update. |
| 3. Read the rubric fillings fixture | T2 + T4 | Open | 2026-09-28: pending IOLG-111. Record `SELECT count(*) FROM m_gradingform_rubric_fillings;` as `lja_reader`. The brief expects 15 after the fixture; 15 is an expected value, not an observed count. |
| 4. Verify that the Moodle pipeline leaves database data unchanged | T2 + T4 | Open | 2026-09-28: pending IOLG-111. Before/after dump hashes, pipeline exit status, and database/client version have not been collected. |
| 5. Verify the Web Services token's authorised functions | T2 + T4 | Open | 2026-09-28: pending IOLG-111. No configured Moodle service/token was available. Record the probe's `Authorised functions: N` line and full function list, then compare with `python/README.md`. |
| 6. Record gitleaks and pip-audit results from the latest main run | T2 + T4 | Done | 2026-09-28: [Security scanning job 108787324090](https://github.com/yetanotherpassword/LearningJourneyAssistant/actions/runs/36377877271/job/108787324090): `67 commits scanned.`, `no leaks found`, and `No known vulnerabilities found`. See the timestamped [log excerpt](sprints/sprint-5/security-evidence/ci-scanners-2026-09-28.txt). This row records that run only. |

## Scanner provenance

- [CI run 36377877271](https://github.com/yetanotherpassword/LearningJourneyAssistant/actions/runs/36377877271)
  was triggered by a push to `main` at 2026-09-28 04:28:44 UTC, on the revision above.
- Lint, tests, and Security scanning completed successfully.
- Gitleaks scanned Git history with redaction enabled; its log reports 67
  commits scanned. This number is the scanner's output, not a count of all
  GitHub history entries.
- The dependency-audit step itself succeeded and reported no known
  vulnerabilities. This is stronger evidence than the job's green status:
  `.github/workflows/ci.yml` sets `continue-on-error: true` for pip-audit.
- Recommendation for action A-12: **make pip-audit blocking**, subject to the
  team's triage decision. The workflow and Jira ticket have not been changed.

The scan findings are bounded by the tools, dependency feed, and timestamp.
They do not establish that the application is vulnerability-free.

## Collecting the remaining evidence

Use the seeded development instance with Ayesha. Record the source revision,
date/time, database and client versions, table prefix, and actual role. Keep
passwords and Web Services tokens out of the transcript. The secret-bearing
role creation command in `sql/README.md` should be redacted in evidence.

For the denied-write check, use a transaction and roll it back even if the
write unexpectedly succeeds; an unexpected success is a failed control.
Do not try this on a production Moodle database. Capture the complete
permission-denied error, not a paraphrase or the expected error copied from
this brief.

For the before/after data-only dump comparison, keep the seeded environment
quiet, use the same dump options and client for both snapshots, and capture
both checksums plus `python -m lja.cli --source moodle`'s exit status.
First establish that two baseline dumps are reproducible: dump metadata or
concurrent Moodle jobs can otherwise make hashes differ without a pipeline
write. Investigate a mismatch; do not normalise away data changes. Matching
snapshots support this one execution and complement the permission test.

The Web Services allowlist comparison must distinguish an **extra function**
from a function the small probe does not need. The root README's macOS
walkthrough configures four probe functions; the Python README lists a
broader planned extraction set. Record the actual list and any discrepancies
instead of assuming the token has either set.

Append the observed outputs and dates to these rows, copy or link them from
the compliance checklist, and have Anup/Ayesha review them before closing
IOLG-111. The evidence currently supports completion of check 6 only.
