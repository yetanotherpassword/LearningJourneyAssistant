# IOLG-125: Project risk register, Sprint 5 re-score

Risk manager: Sui Lung Tang (T5). Re-scored on: 27/09/2026. Previous version: tender document section 3 (23 August 2026); moved to Jira under IOLG-102 (30 August 2026).

## How to score (use exactly this)

- Likelihood (L), 1 to 5. 1 = unlikely on this project. 3 = could happen. 5 = already happening.

- Impact (I), 1 to 5. 1 = minor rework. 3 = a feature slips a sprint. 5 = a Mandatory tender requirement fails.

- Level now = L multiplied by I. 1 to 6 is Low, 8 to 12 is Medium, 15 to 25 is High.

- Residual = the same L x I after the control, as the control is actually working today. Write Low, Medium or High.

Rows 1 to 8 are the tender's risks in the tender's order and wording. Rows 9 to 12 are new since the tender. The column "What actually happened" is pre-written by Allan from the repository; change it if you know better. Your job is the four grey columns: L, I, Level now, Residual, plus an Action if one is needed.

| # | Risk | Tender level | L (1-5) | I (1-5) | Level (now L x I) | What actually happened (Sprints 3 and 4) | Control in place today (file or ticket) | Owner | Residual (Low/Med/High) | Action if any (owner, date) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Rubric fills not available through standard Moodle Web Services | High | 3 | 2 | 6 | Confirmed: the API has no function for rubric fills. The team built the read-only database query (Query 2) instead and proved it on the development Moodle for one subject, CSE1IOI, 15 fills (IOLG-56, IOLG-104, merged 20 Sep). The dedicated read-only role `lja_reader` has now been created and its read-only enforcement observed on the dev instance: an `UPDATE m_user` as the reader returns "permission denied", and a `--data-only` dump is byte-identical before and after `lja.cli --source moodle` (IOLG-111, evidence in docs/security-evidence.md, PR #44 merged). Not yet applied on a shared or production instance. | sql/moodle_attainment_extraction.sql Query 2; lja/data/moodle_loader.py; sql/README.md role DDL | T2 Extraction lead (Ayesha) | Low |   |
| 2 | Project-owner dataset or decision delays | High | 4 | 2 | 8 | The dataset arrived early (workbook supplied 11 Aug). Decisions are the problem: the at-risk rule (none, per Scott), gap thresholds (unratified, action A-01), the export field set (asked 23 Sep, no reply yet), and consent to use crawled handbook content are all still open. | Synthetic data (synth_generator, catalogue generator PR #24); actions register docs/meetings/actions.md; weekly owner slot | T3 Scrum Master (Istiaque) | Low |   |
| 3 | LLM hallucination or unsupported recommendations | Very High | 3 | 3 | 9 | Happened and was caught: a live run returned valid-looking output that silently dropped 3 of 13 SILOs. The grounding validator now checks every AI answer against the input (IOLG-85, merged 11 Sep) and learning plans refuse to save if any name is invented (IOLG-108, merged 20 Sep). The human audit of ten plans has not been done yet (IOLG-121). | lja/llm/grounding.py; 29 grounding tests in CI; staff review gate (IOLG-82); dashboard warning banner (IOLG-116) | T1 AI lead (Allan) | Med |   |
| 4 | Privacy or credential exposure | Very High | 3 | 2 | 6 | No incident. Full-history secret scan has been clean since 24 Aug and blocks every pull request. Dependency scan runs but does not block yet. No real student data anywhere. The Anthropic key lives only in the ignored .env file. | .github/workflows/ci.yml (gitleaks blocking, pip-audit reporting); .gitignore; branch protection on main since 6 Sep | T4 Security lead (Anup) | Low |   |
| 5 | Scope creep or late feature requests | High | 4 | 3 | 12 | Some. Cohort drill-down arrived mid-sprint in Sprint 3; the clusters page (IOLG-131) and a competency-lens proposal were added in Sprint 5; the review banner link was added 26 Sep. Adaptive quizzes were descoped as pre-agreed. The Mandatory export layer (Req 7) is still not started. | Pre-agreed descope order (quizzes, strategies, plans); Sprint 5 plan Rev 6 cut order; feature freeze at the 4/5 Oct review | T2 Product owner proxy (Ayesha) | Med |   |
| 6 | Single-person technical dependency | Medium | 2 | 2 | 4 | Worse than the tender assumed. In Sprint 4, 41 of the 58 non-merge commits were Allan's; Istiaque 9, Ayesha 8. Two of five members have no commits after four sprints. The gap engine, generator, dashboard and documentation are all Allan's. | Pull-request review by a non-author (enforced); READMEs per bundle; ADRs 0001 and 0002; this handover document set | T1 Scrum Master (Allan) | Low |   |
| 7 | Integration defects between extraction, analytics and dashboard | High | 2 | 3 | 6 | Better than feared: the Moodle path was added with no change to the clustering or gap code (the LjaDataset abstraction held). But the dashboard still reads Excel only, and nine pull requests merged on one day (20 Sep) after four sat open for a week. | 196 offline tests in CI; walking skeleton since Sprint 3; integration test against live Moodle (env-gated) | T2 QA lead (Ayesha) | Low |   |
| 8 | Schedule underestimation | High | 3 | 2 | 6 | Sprint 4 committed 57 points; 34 were marked Done in Jira; 22 met the Definition of Done. Sprint 3 was similar (5 to 10 of 31). Sprint 6, held as contingency, is now the handover-document sprint, so there is no contingency left. | Jira burndown; Rev 6 plan with a checkpoint on 28/30 Sep and a named cut order | T5 Scrum Master (Sui Lung) | Low |   |
| 9 | Definition of Done not applied uniformly (new) | n/a | 3 | 4 | 12 | IOLG-107 and IOLG-112 were marked Done in Sprint 4 with only Word documents attached and no code; IOLG-99, 101 and 102 are Done with no evidence in the repository. Rev 6 now says a document is Done only when merged and the PR is linked. | Rev 6 Definition of Done; Sprint 4 report Part A; this sprint's partner-lands-it process | T5 (Sui Lung) | High |   |
| 10 | Two members with no commits after four sprints (new) | n/a | 3 | 3 | 9 | Anup and Sui Lung have no commits. The compendium is Scott's source of truth for individual contribution, and GitHub activity is the evidence he named in Week 6. Sprint 5 gives both members document deliverables landed with a Co-authored-by line so the work is visible in git. | Sprint 5 briefs with partner landing; Co-authored-by trailers | T1 (Allan) | Med |   |
| 11 | Gap thresholds unratified, and shown to flag nearly every student once real variation exists (new) | n/a | 4 | 4 | 16 | On the supplied data the profiles are nearly flat, so few gaps appear. On 500 generated students with real per-competency variation, 448 had a persistent gap at the default cutoff. The flags are accurate but too many. No value has been agreed with Scott (action A-01). | ADR 0001; all thresholds are configuration; catalogue_verify measures recall against planted gaps (PR #24) | T1 (Allan) | High |   |
| 12 | LLM clustering does not scale past about 13 SILOs in one call (new) | n/a | 4 | 4 | 16 | At 52 SILOs the 30B local model failed its own coverage check on all three attempts and was aborted after 7 minutes 43 seconds (20 Sep). The tender's 30-plus subject vision needs a chunked approach, a stronger model, or the embedding pre-pass that ADR 0002 set aside. | ADR 0002 review triggers; handbook-crawl branch holds an embedding tagger; Anthropic backend available | T1 (Allan) | High |   |


## Five sentences: the three highest residual risks and what the team should do about each before 4 October

1. Definition of Done not applied uniformly. Turn the status to in progress.

2. Gap thresholds unratified, and shown to flag nearly every student once real variation exists. Make it not flat.

3. LLM clustering does not scale past about 13 SILOs in one call. Give less information to AI so it handles smoothly.



## Before you score: 30 minutes with Allan

Book 30 minutes with Allan on Friday 26 or Monday 29 September. Send him this file first. In the meeting go down the table; his job is to confirm or correct the "What actually happened" column; yours is to write the L and I numbers while he talks. Facts he will draw on: the Sprint 4 report (points committed versus done), the actions register, and the local-model finding in python/README.md.

## When finished

Save and send to Allan on Teams by Tuesday 30 September, 5 pm. He commits it as docs/risk-register.md with you as co-author and opens the pull request for you to approve. At the retrospective on 4/5 October you re-score the same twelve rows with the whole team in 15 minutes and Allan commits that dated version too. Two dated versions in the repository is the evidence that the register is "reviewed at every retrospective", which the tender promised.
