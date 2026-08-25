# Meetings

Agendas and the running actions register for team meetings.

| File | Purpose |
| --- | --- |
| `sprint-3-agenda.md` | Items needing a team decision, raised during Sprint 3 implementation. Prepared 2026-08-26; meeting date TBC. |
| `actions.md` | **Running register** across all meetings — one row per action, with an owner and a state. Not per-meeting; actions outlive the meeting that raised them. |

## Convention

- One agenda file per meeting. Once a meeting has a date, name it `YYYY-MM-DD-agenda.md`;
  an agenda drafted before a date exists is named for its topic, as `sprint-3-agenda.md` is.
- **`actions.md` is never per-meeting and never rewritten.** Add rows, change states, and
  record the outcome inline. An action closed in a later meeting keeps its original ID so the
  decision trail survives.
- Every agenda item that produces an outcome gets an action row, even if the outcome is "no
  change" — otherwise the next meeting re-litigates it from scratch.
- Decisions with an engineering consequence also belong in the code or its README, not only
  here. This folder records *that* a decision was made; the code records *what* it means.

## Why this exists

Sprint 3 implementation surfaced a set of contradictions between the runbook, `sprint-plan.md`
and the tender — plus several thresholds that the runbook explicitly marks as team decisions
rather than implementer decisions. They were deliberately left unresolved in the code, with
the reasoning recorded next to where each one bites. This folder is where they get settled.
