# Clean-machine rebuild evidence — IOLG-118

Prepared 28 September 2026 for Anup and Istiaque. Reference revision:
`ffa53d54c65946d252e4e1f987c294da2e59da23`.

**Status: clean Codespace rebuild not performed.** The available environment
is a Mac workspace with an assisted Python virtual environment. It is not
the brand-new Ubuntu Codespace required by the brief, and its successful
tests cannot be submitted as proof of an unassisted human rebuild. No
`rebuild-<date>.log` has been fabricated or attached to Jira.

The GitHub connector is currently signed in as a different account from
Anup-TG, with read-only access to this repository; the browser is signed out.
Anup's Codespace access and the completion of Allan's IOLG-114 README pass
must be established before the requested run. This is an access/prerequisite
blocker, not evidence that Codespaces or the README fail.

## Numbered findings for the README owner

These are preflight observations to verify in the clean run, not a completed
clean-machine transcript. They apply to the revision above.

1. **Quick start, step 2: Ubuntu Conda prerequisite is implicit.** Root
   Quick start and `python/README.md` Setup begin with `conda env create`.
   Neither of those sections installs Conda on Ubuntu or explicitly checks
   that it exists. The root README does contain a separate Apple Silicon
   installation guide. Confirm the fresh Codespace's tooling and document
   the required Ubuntu prerequisite or its installation if missing. Do not
   use the PDF's separate setup block to fill this gap during the test.
2. **Quick start step 3 to learning-plan/export examples: cache-path
   mismatch, reproduced locally.** Quick start uses
   `../data-fixtures/reference-run/silo_clustering.json`. It does not create
   `output/silo_clustering.json`, which the later bare plan/export commands
   expect. Both return `No clustering cache at output/silo_clustering.json.`
   and exit 2 after the successful reference run. Carry the explicit cache
   option into the examples. The adjusted export command was verified.
3. **Python Setup/Dashboard instructions change the model prerequisite.**
   Setup's bare `lja.cli` command needs an LLM when the default cache is
   absent, and Dashboard's `--refresh-clustering` example forces a new
   clustering call. Root Quick start already supports offline operation
   with the reference cache. State clearly which path is intended so a
   rebuild does not unexpectedly require a model service/API configuration.
   This is a source inspection finding; no live generation attempt was made.
4. **Local pip source-build dependency, outside the required Conda path.**
   Installing root `requirements.txt` on this Mac stopped with
   `Error: pg_config executable not found.` Local acceptance testing used
   the same-version binary driver in an isolated environment. This is not
   a demonstrated defect in the documented Conda setup; CI already installs
   libpq headers. Record it only if documenting the pip alternative.

Evidence for the reproduced command failures and successful local checks is
in [the preflight record](sprints/sprint-5/rebuild/local-preflight-2026-09-28.txt).
These observations are ready for Istiaque/Allan's review; no Jira issue or
Teams message was sent by this preparation.

## Record the actual clean run

After the README pass is merged, Anup should create a new Codespace on the
intended revision and start recording with `script rebuild-$(date +%F).log`.
Follow only root README Quick start and Python README Setup, in order.
Record each instruction that fails, is missing, or needs help as a numbered
defect; keep attempted command, full error, exit status, and revision together.
Do not silently repair a prerequisite and label the original step a pass.
Stop the dashboard normally when its browser check is complete, and use
`exit` to finish the recording.

Use the following fields for the run record; all are currently unobserved:

| Field | Actual clean-run value |
| --- | --- |
| Tester and date/time | Pending Anup's run |
| Fresh Codespace identity / OS | Pending |
| Repository revision | Pending; record `git log -1 --oneline` |
| README pass revision or PR | Pending IOLG-114 confirmation |
| Python environment creation | Not run |
| Pipeline result and output path | Not run |
| Test summary, failures, and skips | Not run |
| Dashboard opened through Ports | Not run |
| Transcript filename | Not created |
| Numbered defects | Pending clean run; preflight findings above |
| Jira IOLG-118 attachments | Not uploaded |

Exclude credentials from the recording. If a command would display a secret,
record a redacted version and label the redaction; preserve meaningful errors
and outcomes. Attach the real transcript and defect list to IOLG-118 after
review. Successful README-only setup, pipeline/tests, and browser access by
the independent operator establish the requested rebuild evidence; failures
and gaps are valid findings to send to IOLG-114, not results to conceal.

## Day-one setup and PR review

The local test suite has been exercised, but the brief's task 0 Codespace
test run remains unverified. When reviewing a partner's PR, compare Files
changed with the intended document, check CI, then submit the review as
yourself. GitHub does not let a PR author approve their own PR: work opened
under Anup's account needs a non-author partner to approve it. No approval
or co-author identity is claimed by these prepared documents.
