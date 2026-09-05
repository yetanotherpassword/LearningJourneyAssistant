# LJA — Documents bundle

Project documents that are not code: slides, reports, and (as they accumulate)
sprint artefacts.

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
| [Pipeline architecture diagram](https://claude.ai/code/artifact/3c9d410a-f89e-4bdb-bfe5-38acb3cf6c9a) ([PDF](<LJA — Data & Algorithm Pipeline.pdf>)) | Six-stage data-flow diagram (Moodle/Excel → extraction → mapping → gap detection → LLM layer → dashboard) plus a field-level "zoom" showing exactly which Moodle/Excel fields feed `lja_criterion_score`. |
| [UML use case & sequence diagrams](https://claude.ai/code/artifact/1e066a27-42dc-45dc-9e5d-22a6e1f9b1ec) ([PDF](<LJA — UML Use Case & Sequence Diagrams.pdf>)) | Who interacts with the system (built vs. planned use cases, visually distinguished) and two sequence diagrams for code that actually runs: the CLI pipeline, and the SILO coverage-validation failure it was built to catch. |

**On the two diagram entries above:** the live link is a Claude Artifact — private by default, use its share menu if the whole team needs access without going through whoever generated it, and it stays interactive/re-renderable. The PDF alongside each is a static export committed to this folder, so the repo has a copy that doesn't depend on claude.ai access. If they go stale relative to the code, regenerate rather than hand-edit either one — a hand-edited PDF has no source to keep in sync.

## Conventions

- Binary documents (`.pptx`, `.docx`, `.pdf`) are committed as-is; export a PDF
  alongside any deck that will be presented, so reviewers do not need
  PowerPoint.
- Keep decision records in the bundle READMEs next to the code they affect
  (that is where the architecture reasoning currently lives — devenv, python,
  sql, data-fixtures). This folder is for outward-facing documents.
  **Pending change:** WP2 (S3-6) is briefed to create `docs/adr/` for the
  relative-gap-detection decision, which cuts against this convention. Either
  ADRs become the home for cross-cutting algorithm decisions and this bullet is
  narrowed to bundle-local ones, or WP2's record belongs in `python/README.md`.
  Decide when WP2 lands rather than ending up with both.

## Expected additions

- Sprint review notes and the backlog snapshot per sprint.
- The filled-in project compliance checklist from the proposal (privacy,
  security risk, testing protocols) — cheap to complete now, and the
  DevSecOps evidence the project owner flagged as a differentiator.
- Final handover document, including the plainly-stated caveat that rubric
  fills are read directly from the database because the Web Services API does
  not expose them.
