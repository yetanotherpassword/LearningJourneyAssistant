IOLG-125: Project risk register, Sprint 5 re-score

Risk manager: Sui Lung Tang (T5). Re-scored on:
\_\_\_\_\_\_\_\_\_\_\_\_. Previous version: tender document section 3
(23 August 2026); moved to Jira under IOLG-102 (30 August 2026).

How to score (use exactly this)

- Likelihood (L), 1 to 5. 1 = unlikely on this project. 3 = could
  happen. 5 = already happening.

- Impact (I), 1 to 5. 1 = minor rework. 3 = a feature slips a sprint. 5
  = a Mandatory tender requirement fails.

- Level now = L multiplied by I. 1 to 6 is Low, 8 to 12 is Medium, 15 to
  25 is High.

- Residual = the same L x I after the control, as the control is
  actually working today. Write Low, Medium or High.

Rows 1 to 8 are the tender's risks in the tender's order and wording.
Rows 9 to 12 are new since the tender. The column "What actually
happened" is pre-written by Allan from the repository; change it if you
know better. Your job is the four grey columns: L, I, Level now,
Residual, plus an Action if one is needed.

<table>
<colgroup>
<col style="width: 2%" />
<col style="width: 12%" />
<col style="width: 5%" />
<col style="width: 3%" />
<col style="width: 3%" />
<col style="width: 4%" />
<col style="width: 27%" />
<col style="width: 18%" />
<col style="width: 7%" />
<col style="width: 5%" />
<col style="width: 8%" />
</colgroup>
<thead>
<tr class="header">
<th><strong>#</strong></th>
<th><strong>Risk</strong></th>
<th><strong>Tender level</strong></th>
<th><p><strong>L</strong></p>
<p><strong>1-5</strong></p></th>
<th><p><strong>I</strong></p>
<p><strong>1-5</strong></p></th>
<th><p><strong>Level now</strong></p>
<p><strong>L x I</strong></p></th>
<th><strong>What actually happened (Sprints 3 and 4)</strong></th>
<th><strong>Control in place today (file or ticket)</strong></th>
<th><strong>Owner</strong></th>
<th><p><strong>Residual</strong></p>
<p><strong>Low/Med/High</strong></p></th>
<th><strong>Action if any (owner, date)</strong></th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>1</td>
<td>Rubric fills not available through standard Moodle Web Services</td>
<td>High</td>
<td></td>
<td></td>
<td></td>
<td>Confirmed: the API has no function for rubric fills. The team built
the read-only database query (Query 2) instead and proved it on the
development Moodle for one subject, CSE1IOI, 15 fills (IOLG-56,
IOLG-104, merged 20 Sep). The dedicated read-only role
<code>lja_reader</code> has now been created and its read-only
enforcement observed on the dev instance: an <code>UPDATE m_user</code>
as the reader returns &quot;permission denied&quot;, and a
<code>--data-only</code> dump is byte-identical before and after
<code>lja.cli --source moodle</code> (IOLG-111, evidence in
docs/security-evidence.md, PR #44 under review). Not yet applied on a
shared or production instance.</td>
<td>sql/moodle_attainment_extraction.sql Query 2;
lja/data/moodle_loader.py; sql/README.md role DDL</td>
<td>T2 Extraction lead (Ayesha)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>2</td>
<td>Project-owner dataset or decision delays</td>
<td>High</td>
<td></td>
<td></td>
<td></td>
<td>The dataset arrived early (workbook supplied 11 Aug). Decisions are
the problem: the at-risk rule (none, per Scott), gap thresholds
(unratified, action A-01), the export field set (asked 23 Sep, no reply
yet), and consent to use crawled handbook content are all still
open.</td>
<td>Synthetic data (synth_generator, catalogue generator PR #24);
actions register docs/meetings/actions.md; weekly owner slot</td>
<td>T3 Scrum Master (Istiaque)</td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>3</td>
<td>LLM hallucination or unsupported recommendations</td>
<td>Very High</td>
<td></td>
<td></td>
<td></td>
<td>Happened and was caught: a live run returned valid-looking output
that silently dropped 3 of 13 SILOs. The grounding validator now checks
every AI answer against the input (IOLG-85, merged 11 Sep) and learning
plans refuse to save if any name is invented (IOLG-108, merged 20 Sep).
The human audit of ten plans has not been done yet (IOLG-121).</td>
<td>lja/llm/grounding.py; 29 grounding tests in CI; staff review gate
(IOLG-82); dashboard warning banner (IOLG-116)</td>
<td>T1 AI lead (Allan)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>4</td>
<td>Privacy or credential exposure</td>
<td>Very High</td>
<td></td>
<td></td>
<td></td>
<td>No incident. Full-history secret scan has been clean since 24 Aug
and blocks every pull request. Dependency scan runs but does not block
yet. No real student data anywhere. The Anthropic key lives only in the
ignored .env file.</td>
<td>.github/workflows/ci.yml (gitleaks blocking, pip-audit reporting);
.gitignore; branch protection on main since 6 Sep</td>
<td>T4 Security lead (Anup)</td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>5</td>
<td>Scope creep or late feature requests</td>
<td>High</td>
<td></td>
<td></td>
<td></td>
<td>Some. Cohort drill-down arrived mid-sprint in Sprint 3; the clusters
page (IOLG-131) and a competency-lens proposal were added in Sprint 5;
the review banner link was added 26 Sep. Adaptive quizzes were descoped
as pre-agreed. The Mandatory export layer (Req 7) is still not
started.</td>
<td>Pre-agreed descope order (quizzes, strategies, plans); Sprint 5 plan
Rev 6 cut order; feature freeze at the 4/5 Oct review</td>
<td>T2 Product owner proxy (Ayesha)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>6</td>
<td>Single-person technical dependency</td>
<td>Medium</td>
<td></td>
<td></td>
<td></td>
<td>Worse than the tender assumed. In Sprint 4, 41 of the 58 non-merge
commits were Allan's; Istiaque 9, Ayesha 8. Two of five members have no
commits after four sprints. The gap engine, generator, dashboard and
documentation are all Allan's.</td>
<td>Pull-request review by a non-author (enforced); READMEs per bundle;
ADRs 0001 and 0002; this handover document set</td>
<td>T1 Scrum Master (Allan)</td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>7</td>
<td>Integration defects between extraction, analytics and dashboard</td>
<td>High</td>
<td></td>
<td></td>
<td></td>
<td>Better than feared: the Moodle path was added with no change to the
clustering or gap code (the LjaDataset abstraction held). But the
dashboard still reads Excel only, and nine pull requests merged on one
day (20 Sep) after four sat open for a week.</td>
<td>196 offline tests in CI; walking skeleton since Sprint 3;
integration test against live Moodle (env-gated)</td>
<td>T2 QA lead (Ayesha)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>8</td>
<td>Schedule underestimation</td>
<td>High</td>
<td></td>
<td></td>
<td></td>
<td>Sprint 4 committed 57 points; 34 were marked Done in Jira; 22 met
the Definition of Done. Sprint 3 was similar (5 to 10 of 31). Sprint 6,
held as contingency, is now the handover-document sprint, so there is no
contingency left.</td>
<td>Jira burndown; Rev 6 plan with a checkpoint on 28/30 Sep and a named
cut order</td>
<td>T5 Scrum Master (Sui Lung)</td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>9</td>
<td>Definition of Done not applied uniformly (new)</td>
<td>n/a</td>
<td></td>
<td></td>
<td></td>
<td>IOLG-107 and IOLG-112 were marked Done in Sprint 4 with only Word
documents attached and no code; IOLG-99, 101 and 102 are Done with no
evidence in the repository. Rev 6 now says a document is Done only when
merged and the PR is linked.</td>
<td>Rev 6 Definition of Done; Sprint 4 report Part A; this sprint's
partner-lands-it process</td>
<td>T5 (Sui Lung)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>10</td>
<td>Two members with no commits after four sprints (new)</td>
<td>n/a</td>
<td></td>
<td></td>
<td></td>
<td>Anup and Sui Lung have no commits. The compendium is Scott's source
of truth for individual contribution, and GitHub activity is the
evidence he named in Week 6. Sprint 5 gives both members document
deliverables landed with a Co-authored-by line so the work is visible in
git.</td>
<td>Sprint 5 briefs with partner landing; Co-authored-by trailers</td>
<td>T1 (Allan)</td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>11</td>
<td>Gap thresholds unratified, and shown to flag nearly every student
once real variation exists (new)</td>
<td>n/a</td>
<td></td>
<td></td>
<td></td>
<td>On the supplied data the profiles are nearly flat, so few gaps
appear. On 500 generated students with real per-competency variation,
448 had a persistent gap at the default cutoff. The flags are accurate
but too many. No value has been agreed with Scott (action A-01).</td>
<td>ADR 0001; all thresholds are configuration; catalogue_verify
measures recall against planted gaps (PR #24)</td>
<td>T1 (Allan)</td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>12</td>
<td>LLM clustering does not scale past about 13 SILOs in one call
(new)</td>
<td>n/a</td>
<td></td>
<td></td>
<td></td>
<td>At 52 SILOs the 30B local model failed its own coverage check on all
three attempts and was aborted after 7 minutes 43 seconds (20 Sep). The
tender's 30-plus subject vision needs a chunked approach, a stronger
model, or the embedding pre-pass that ADR 0002 set aside.</td>
<td>ADR 0002 review triggers; handbook-crawl branch holds an embedding
tagger; Anthropic backend available</td>
<td>T1 (Allan)</td>
<td></td>
<td></td>
</tr>
</tbody>
</table>

Five sentences: the three highest residual risks and what the team
should do about each before 4 October

1\.
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

2\.
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

3\.
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

4\.
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

5\.
\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

Before you score: 30 minutes with Allan

Book 30 minutes with Allan on Friday 26 or Monday 29 September. Send him
this file first. In the meeting go down the table; his job is to confirm
or correct the "What actually happened" column; yours is to write the L
and I numbers while he talks. Facts he will draw on: the Sprint 4 report
(points committed versus done), the actions register, and the
local-model finding in python/README.md.

When finished

Save and send to Allan on Teams by Tuesday 30 September, 5 pm. He
commits it as docs/risk-register.md with you as co-author and opens the
pull request for you to approve. At the retrospective on 4/5 October you
re-score the same twelve rows with the whole team in 15 minutes and
Allan commits that dated version too. Two dated versions in the
repository is the evidence that the register is "reviewed at every
retrospective", which the tender promised.
