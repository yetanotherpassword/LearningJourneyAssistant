# LJA — Documents bundle

Project documents that are not code: the handover set, design pages, Sprint 5
evidence, sprint plans and meeting records. Refreshed 3 October 2026.

## Start here

| Path | Purpose |
| --- | --- |
| [`handover/system-maintenance-document.md`](handover/system-maintenance-document.md) (+ `.docx`, `.pdf`) | **The reference.** Architecture, design decisions, deployment, maintenance, testing, validation results, future work, and Appendix B defining every metric. Rebuild with `handover/scripts/build_smd.sh`. |
| [`handover/user-document.md`](handover/user-document.md) (+ `.docx`, `.pdf`) | For people who use the dashboard: how outcomes become competencies and marks become priority groups, how to produce the data, and every page with a screenshot. Rebuild with `handover/scripts/build_user_doc.sh`. |
| [`handover/learning-plan-traceability.md`](handover/learning-plan-traceability.md) | One real claim from a learning plan traced back to the workbook, and why that matters. |
| [`handover/diagrams/`](handover/diagrams/) | Mermaid sources (`*.mmd`) and their PNG/SVG renders for every architecture, class, sequence and lineage figure, plus the dashboard screenshots. Edit the `.mmd`, then `design/build.sh` re-renders. |
| [`design/`](design/) | Sources for the three design pages below and the requirements status; `design/build.sh` builds their PDF and Word copies into this folder. |
| `adr/` | 0001 relative gap detection (thresholds unratified, A-01); 0002 no-embedding clustering (its review trigger has been hit; see SMD §8.2). |

## Sprint 5 evidence

| Path | Ticket | What it records |
| --- | --- | --- |
| `validation-worksheet.md` | IOLG-110 | Seven hand-worked gap-detection profiles, also pinned as a test |
| `grounding-audit.md`, `sprints/sprint-5/grounding-audit/` | IOLG-121 | Ten plans: machine audit 10/10, assisted prose review, human sign-off pending |
| `security-evidence.md`, `sprints/sprint-5/security-evidence/` | IOLG-111 | The six security checks, observed on the dev instance |
| `compliance-checklist.md` | IOLG-117 | All 40 tender items with evidence |
| `rebuild-check.md`, `sprints/sprint-5/rebuild/` | IOLG-118 | Why the clean rebuild has not run, and four preflight findings |
| `uat-checklist.md`, `sprints/sprint-5/uat/` | IOLG-130, IOLG-129 | S1–S6 preliminary results, findings UAT-01 and UAT-02 |
| `risk-register.md` | IOLG-125 | Twelve risks re-scored |
| `cluster-review-sprint5.md` | IOLG-124, IOLG-133 | Staff verdicts on the five reference-run clusters |
| `export-schema.md`, `export-sample.ipynb` | IOLG-120 | Every export column; a notebook that reads one |

## Contents

| Path | Purpose |
| --- | --- |
| `sprint-plan.md` | Active specification for Sprints 1–5: workload allocation, per-sprint engineering/documentation requirements, descope policy. Update it as sprints close, don't let it go stale. **Its Sprint 3 dates disagree with the runbooks below — see r2 §A.2; unresolved.** |
| `sprint-3-implementation-runbook.md` | **r1, superseded but retained.** The original Sprint 3 brief: five work packages, ground rules, escalation points. Kept as the record of what was asked for, unedited. |
| `sprint-3-implementation-runbook-r2.md` | **Current.** Revises r1 against what was actually built: WP1 and WP4-part-1 landed, decisions taken and why, facts r1 got wrong about the repo, and four contradictions found between r1, `sprint-plan.md` and the tender. Start here. |
| `LJA_Sprint_Plan_3-6_rev5.pdf` | **The binding sprint plan.** Rev 5, 24 Aug, verified against `410abb6`: Sprint 3 items S3-1…S3-13 with owners, points and acceptance criteria; Sprints 4–6 indicative; what was cut and why; DoR/DoD; `Refs IOLG-nn` convention. Supersedes `sprint-plan.md` §4–§7. Committed 5 Sep after living only in a Downloads folder. |
| `LJA_Sprint_Plan_A-C_rev3.pdf` | Rev 3 of the same plan under its earlier A/B/C naming. Kept for its §1 Jira terminology mapping and §4 **seven-epic structure** (E1–E7), which the board does not currently follow — see action A-34. |
| [`meetings/`](meetings/) | Meeting agendas and the **running actions register**. `meetings/sprint-3-agenda.md` collects everything from Sprint 3 implementation that needs a team decision; `meetings/actions.md` tracks the outcomes and outlives any single meeting. |
| `TradeShow/Learning_Journey_Assistant_-_Trade_Show_Deck.pptx` | Trade show booth deck. Draft — needs more content, and should be re-cut from the live demo once the walking skeleton runs. |
| `LJA — Data & Algorithm Pipeline.pdf` / `.docx` | **Version 2.0, 3 Oct 2026**, built from `design/data-and-algorithm-pipeline.md`. Seven stages with owning code and status, what the gap engine does, where the Moodle score comes from, trust boundaries, and what changed since the 11 August page. |
| `LJA -- Pipeline.pdf` / `.docx` | **Version 2.0, 3 Oct 2026**, from `design/cli-pipeline.md`. What one `lja.cli` run does, the commands that read what it wrote, and timings. |
| `LJA — UML Use Case & Sequence Diagrams.pdf` / `.docx` | **Version 2.0, 3 Oct 2026**, from `design/uml-use-case-and-sequence.md`. Actors and use cases as built, the class view, and three sequence diagrams: the pipeline, the artefact family, generating from the dashboard. |
| `LJA -- Requirements_for_SILO_analysis.pdf` | The team's record of the 11 August 2026 meeting with the project owner: FR-1 to FR-9, NFR-1 to NFR-8, open questions. **A source document, left as written.** |
| `LJA -- Requirements_status.pdf` / `.docx` | **New, 3 Oct 2026**, from `design/requirements-status.md`: every FR and NFR above with its status on `main` and where to look. |

**On the three design pages:** the August 2026 versions were Claude Artifacts printed to PDF, with no source in the repository; their links are retired. The 2.0 versions have Markdown sources under `design/` and embed the handover diagrams, so a change to a `.mmd` file flows into the SMD, the User Document and these pages from one place. Regenerate with `design/build.sh`; do not hand-edit the PDF or Word copies.

## Conventions

- Binary documents (`.pptx`, `.docx`, `.pdf`) are committed as-is; export a PDF
  alongside any deck that will be presented, so reviewers do not need
  PowerPoint.
- Keep decision records in the bundle READMEs next to the code they affect
  (that is where the architecture reasoning currently lives — devenv, python,
  sql, data-fixtures). This folder is for outward-facing documents.
  Cross-cutting algorithm decisions live in `docs/adr/` (0001, 0002); the
  numbered design decisions D1 to D20 are in the SMD §3.7. Bundle READMEs keep
  the bundle-local reasoning.

## Still expected

- The live UAT results from the 4/5 October review (into `uat-checklist.md`
  and SMD §7.3), and the re-scored risk register from the retrospective.
- The clean-machine rebuild transcript (IOLG-118).
- Anup's human sign-off on the ten-plan grounding audit (IOLG-121).

Done since this list was written: the compliance checklist (`compliance-checklist.md`),
the handover documents (`handover/`), and the plainly stated rubric-fills caveat (SMD §3.7 D3 and §5.8).
