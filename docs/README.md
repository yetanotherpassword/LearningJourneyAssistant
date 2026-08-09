# LJA — Documents bundle

Project documents that are not code: slides, reports, and (as they accumulate)
sprint artefacts.

## Contents

| Path | Purpose |
| --- | --- |
| `sprint-plan.md` | Active specification for Sprints 1–5: workload allocation, per-sprint engineering/documentation requirements, descope policy. Update it as sprints close, don't let it go stale. |
| `TradeShow/Learning_Journey_Assistant_-_Trade_Show_Deck.pptx` | Trade show booth deck. Draft — needs more content, and should be re-cut from the live demo once the walking skeleton runs. |

## Conventions

- Binary documents (`.pptx`, `.docx`, `.pdf`) are committed as-is; export a PDF
  alongside any deck that will be presented, so reviewers do not need
  PowerPoint.
- Keep decision records in the bundle READMEs next to the code they affect
  (that is where the architecture reasoning currently lives — devenv, python,
  sql, data-fixtures). This folder is for outward-facing documents.

## Expected additions

- Sprint review notes and the backlog snapshot per sprint.
- The filled-in project compliance checklist from the proposal (privacy,
  security risk, testing protocols) — cheap to complete now, and the
  DevSecOps evidence the project owner flagged as a differentiator.
- Final handover document, including the plainly-stated caveat that rubric
  fills are read directly from the database because the Web Services API does
  not expose them.
