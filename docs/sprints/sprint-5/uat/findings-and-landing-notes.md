# UAT findings & IOLG-129 landing notes

Working note for the 4/5 October review. Prepared 28 September 2026 by
Ayesha (T2). The two findings below were observed while verifying Anup's
UAT execution (PR #40, merged to `main`). Both are already recorded in
`docs/uat-checklist.md`; this note restates them in a Jira-ready form and
routes each to the right ticket, and pre-stages the IOLG-129 landing so
the combined checklist can be committed quickly on Thursday 2 October.

## Finding UAT-01 — documented bare commands exit 2 (route to IOLG-114)

The Quick start reads the committed reference cache via `--clustering-cache`
but never copies it to `output/silo_clustering.json`. Consequently the
documented bare commands

```
python -m lja.plan <xlsx> STU0003
python -m lja.export <xlsx>
```

exit `2` with `No clustering cache at output/silo_clustering.json`.
Reproduced 28 Sep.

- **Impact:** documentation/setup only, not a code defect.
- **Fix options:** (a) have the Quick start persist the default cache to
  `output/silo_clustering.json`, or (b) update the plan/export examples to
  carry the explicit
  `--clustering-cache data-fixtures/reference-run/silo_clustering.json`.
- **Do not** alter the committed reference fixture to work around this.
- **Owner:** Allan (T1), IOLG-114 (handover / Quick start docs).

## Finding UAT-02 — review banner omits rejected-cluster name (route to dashboard)

S5 expects the AI-review banner to *name* the rejected clusters. Observed:
the banner shows only a count —
`1 AI-generated SILO cluster(s) have been rejected by staff.` — and omits
the name (`Data Structures and Algorithms [3cc7cf957629]`), even though the
CLI *does* name it when blocking gap generation (exit 2). Reproduced 28 Sep
on a disposable rejected fixture.

- **Impact:** the S5 "names the rejected cluster" acceptance criterion is
  currently **FAIL** on the dashboard banner (the CLI path passes).
- **Fix options:** (a) amend the banner to name rejected clusters, or
  (b) the team explicitly revises the S5 criterion.
- **Owner:** dashboard team (banner is IOLG-116-adjacent); raise for the
  4/5 Oct review.

## IOLG-129 — combined UAT checklist landing (ready for Thu 2 Oct)

Sui Lung sends the merged Word doc (Anup's system rows S1–S6 + her
dashboard rows). Land it as `docs/uat-checklist.md`, overwriting the
current Anup-only file. Verified co-author identities are baked into the
commit below.

```bash
# from repo root, once the merged doc is at ~/Downloads/uat-checklist.docx
git checkout main && git pull
git checkout -b IOLG-129/uat-checklist
pandoc ~/Downloads/uat-checklist.docx -t gfm -o docs/uat-checklist.md
# review it: 7-col table (# · User story · Steps · Expected · Result · Tester · Notes);
# fix any pandoc-mangled tables; confirm BOTH halves are present before committing.
git add docs/uat-checklist.md
git commit -m "IOLG-129: land the combined system + dashboard UAT checklist" \
  -m "Refs IOLG-129" \
  -m "Co-authored-by: Anup Tumbalam Gooty <tganup17@gmail.com>" \
  -m "Co-authored-by: Sui Lung Tang <147133049+davetang25@users.noreply.github.com>" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push -u origin IOLG-129/uat-checklist
# then (hold for Ayesha's go-ahead per the hold-PR rule):
gh pr create --repo yetanotherpassword/LearningJourneyAssistant \
  --reviewer Anup-TG,davetang25,yetanotherpassword \
  --title "IOLG-129: combined UAT checklist" --body "…"
```

Watch-outs for Thursday:
- Confirm Sui Lung's doc contains **both** halves before running pandoc —
  it overwrites Anup's now-merged file.
- Hold before `gh pr create` and confirm with Ayesha (hold-PR-until-asked).

Verified GitHub identities: Anup = `Anup-TG <tganup17@gmail.com>`;
Sui Lung = `davetang25 <147133049+davetang25@users.noreply.github.com>`.
