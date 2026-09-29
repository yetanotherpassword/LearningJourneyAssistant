# Security evidence — IOLG-111

Recorded 28 September 2026 against `main` revision
`502f26b119b9ca010e36987c24b984a7874c7f36`. For review by
Anup (T4) and Ayesha (T2, IOLG-128). Scope: the six checks in the Sprint 5
brief, supporting Tender Requirements 1 and 9.

**Status: all six checks observed.** Checks 1–5 were run against the seeded
development Moodle instance (Docker: PostgreSQL 17.11, Moodle 5.2.2 (Build:
20260810), table prefix `m_`); check 6 records the completed main-branch
scanner run. Passwords and the Web Services token are kept out of this record.
The `lja_reader` password was supplied from `python/.env` (gitignored).

## Results for the compliance checklist

These six checks support the original **Security and risk** items in
`docs/compliance-checklist.md`: checks 1–5 support SE-4; check 6 supplies
current scanner evidence for SE-1. All 40 original checklist rows are retained
without adding these six as new requirements. SE-1 stays Open because this
current scan does not establish its original before-first-push criterion.
SE-4's runtime read-only enforcement is now evidenced by checks 1–4.
T2/T4 are the current security-check partners; original checklist owners are
preserved separately.

| Item | Owner (T1–T5) | Status (Done / Open / Deferred) | Evidence (file path, PR number, Jira key, or “pending IOLG-111”) |
| --- | --- | --- | --- |
| 1. Create the dedicated `lja_reader` role and SELECT grants | T2 + T4 | Done | 2026-09-28, as superuser `moodle` on the seeded dev instance: the five statements from `sql/README.md` all succeeded — psql echoed `CREATE ROLE`, `GRANT`, `GRANT`, `GRANT`, `ALTER DEFAULT PRIVILEGES` (CONNECT, USAGE on `public`, SELECT on all tables, and default SELECT on future tables). Role password supplied from `python/.env`, redacted here. |
| 2. Confirm that the reader cannot update `m_user` | T2 + T4 | Done | 2026-09-28, reconnected as `lja_reader`: `UPDATE m_user SET city = 'x' WHERE id = 2;` returned verbatim `ERROR:  permission denied for table m_user`. The read-only grant is enforced by the database, not merely declared in code. |
| 3. Read the rubric fillings fixture | T2 + T4 | Done | 2026-09-28, as `lja_reader`: `SELECT count(*) FROM m_gradingform_rubric_fillings;` returned `15`, matching the expected seeded-fixture count. |
| 4. Verify that the Moodle pipeline leaves database data unchanged | T2 + T4 | Done | 2026-09-28, dev instance quiesced (app containers stopped): `pg_dump -U moodle --data-only moodle \| md5sum` before and after `python -m lja.cli --source moodle` (connecting as `lja_reader` on `localhost:15432`, exit `0`) gave identical normalised checksums `6717a309e41d8abb185a3768754688e5`. Raw dumps differed **only** in pg_dump 17's per-invocation `\restrict`/`\unrestrict` anti-injection nonce (line 5 and the final line); all 21,554 data lines were byte-identical (confirmed by `diff`). Two consecutive baseline dumps showed the same nonce-only difference, so the checksum is reproducible and no data change was normalised away. |
| 5. Verify the Web Services token's authorised functions | T2 + T4 | Done | 2026-09-28, `python moodle_probe.py` against `http://localhost:8081` with a token for the built-in `moodle_mobile_app` service reported `Authorised functions: 429`. The probe uses only four functions (`core_webservice_get_site_info`, `core_course_get_courses`, `core_enrol_get_enrolled_users`, `gradereport_user_get_grade_items`), so the mobile-app token authorises far more than needed and is **not least-privilege**. The production extraction path does **not** use Web Services — it reads Moodle over a direct read-only PostgreSQL connection as `lja_reader` (checks 2 and 4); `moodle_probe.py` is a Sprint-1 connectivity spike. Recommendation: if a WS extraction path is ever adopted, define a purpose-built external service limited to those four functions. Token value kept out of this record. |
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

## How checks 1–5 were collected

Environment: the `moodle-docker` development stack (`devenv/env.sh`), PostgreSQL
17.11 server and `pg_dump`/`psql` 17.11 clients, Moodle 5.2.2 (Build: 20260810),
table prefix `m_`, reader role `lja_reader`. The database port was published to
the host (`MOODLE_DOCKER_DB_PORT=15432`) so the pipeline could connect as the
reader. These results reflect the seeded dev instance, not a production Moodle.

- **Denied-write (check 2):** the complete `permission denied` line was captured
  verbatim, not paraphrased or copied from the brief.
- **Dump comparison (check 4):** the instance was quiesced (app containers
  stopped) and the same client/options were used for both snapshots. Baseline
  reproducibility was established first — two back-to-back dumps differed only in
  pg_dump 17's random `\restrict`/`\unrestrict` nonce. That nonce is a psql
  meta-command guard, not data; it is excluded from the checksum, and the
  underlying `diff` showing byte-identical data rows is the primary evidence.
- **Web Services allowlist (check 5):** the observed authorised-function count
  (429, the `moodle_mobile_app` service) is recorded against the four functions
  the probe actually needs. This is the "extra functions" finding the check asks
  for, and it distinguishes the WS spike from the read-only DB path the
  extraction layer uses in production.

Enabling Web Services and minting the probe token were one-off changes to the
dev instance only. Anup and Ayesha should review these rows before IOLG-111 is
moved to Done; the underlying commands and outputs are reproducible from the
environment above.
