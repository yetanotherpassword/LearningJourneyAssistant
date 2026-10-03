# Sprint 5 Grounding Audit — IOLG-121

## Purpose

This audit evaluates whether AI-generated student learning plans remain grounded in the evidence supplied to the Learning Journey Assistant.

The audit addresses Tender Requirement 6 and the Sprint 5 requirement to inspect a fixed set of ten learning plans using both automated grounding validation and independent human review.

## Audit setup

| Item | Value |
|---|---|
| Work item | IOLG-121 |
| Dataset | `data-fixtures/CSE_results_150_students_3_Subjects.xlsx` |
| Clustering | `data-fixtures/reference-run/silo_clustering.json` |
| Staff review file | `data-fixtures/reference-run/silo_clustering.review.json` |
| LLM provider | Anthropic |
| Model | `claude-opus-4-8` |
| Maximum generation attempts | 3 |
| Students audited | 10 |

The fixed audit set was selected to cover different competency profiles rather than ten identical cases. It includes persistent gaps detected through both relative-position and absolute-floor rules, as well as students with isolated gaps, developing profiles, and fully proficient profiles.

## Fixed student set

| Student | Profile included in the audit |
|---|---|
| STU0003 | Persistent gap — relative position |
| STU0004 | Persistent gap — absolute floor |
| STU0022 | Persistent gap — relative position |
| STU0054 | Persistent gap — absolute floor |
| STU0055 | Persistent gap — relative position |
| STU0067 | Persistent gap — absolute floor |
| STU0075 | Persistent gap — relative position |
| STU0001 | No persistent gap; multiple isolated gaps |
| STU0005 | All competencies proficient |
| STU0007 | All competencies developing |

## Automated grounding checks

Each generated plan is checked against the exact evidence supplied for that student.

The validator checks that the plan does not introduce unknown:

- student identifiers;
- competency labels;
- SILO keys;
- subject codes;
- assessment references.

Competency priorities are also checked for duplicate references.

Free-text plan fields are scanned for subject codes and SILO references so that unsupported references embedded in prose are also detected.

If a grounding check fails, the plan-generation process may retry up to three times with the validation error supplied back to the model. A plan that remains ungrounded is not returned as a successful result.

## Machine audit results

| Student | Attempts | Failed attempts | Failed grounding checks | Final result |
|---|---:|---:|---|---|
| STU0003 | 1 | 0 | None | PASS |
| STU0004 | 1 | 0 | None | PASS |
| STU0022 | 1 | 0 | None | PASS |
| STU0054 | 1 | 0 | None | PASS |
| STU0055 | 1 | 0 | None | PASS |
| STU0067 | 1 | 0 | None | PASS |
| STU0075 | 1 | 0 | None | PASS |
| STU0001 | 1 | 0 | None | PASS |
| STU0005 | 1 | 0 | None | PASS |
| STU0007 | 1 | 0 | None | PASS |

### Machine-audit summary

- Plans audited: **10**
- Plans passing final grounding validation: **10/10 (100%)**
- Plans requiring a retry: **0**
- Failed grounding attempts: **0**
- Plans rejected after all attempts: **0**

The audit therefore found no unsupported structured references or detectable unsupported SILO/subject references in the ten generated plans.

This result demonstrates that the automated grounding controls operated successfully on this fixed audit set. It does not establish that every natural-language statement in every plan is factually correct; that broader question is checked separately through human review.

## Generation evidence

The audit generated a separate evidence context and final plan for every student.

Files are stored under:

`docs/sprints/sprint-5/grounding-audit/`

Important artefacts:

- `machine-audit.csv` — machine grounding results;
- `metadata.json` — audit configuration and model metadata;
- `plans/` — the ten generated learning plans;
- `evidence/` — the evidence context supplied for each corresponding student.

These plan/evidence pairs are provided to Anup for the independent human review.

## LLM usage

Across the ten audited plans:

- Anthropic calls: **10**
- Input tokens: **45,513**
- Output tokens: **15,798**
- Total model time: **190.5 seconds**
- Estimated total API cost: **$0.6225**

All ten plans passed on the first attempt.

## Independent human review

The human review checks a broader question than the automated validator: whether the recommendations and factual claims made in each plan are actually supported by the supplied student evidence.

An [AI-assisted pre-review dated 28 September](sprints/sprint-5/grounding-audit/assisted-review.md)
compares all ten saved plans with their evidence and provides the six columns
requested in Anup's Sprint 5 brief. It identifies specific prose concerns in
eight plans, including an incorrect persistent-gap count and feedback
attributed to the wrong assessment. These are proposed review findings, not
Anup's independent human sign-off. The table below records the human decisions
Anup has subsequently confirmed; unreviewed rows remain Pending.

Anup confirmed personally reviewing the STU0003 plan and its paired evidence
on **3 October 2026**, against source revision
`b4ccebd098e6be8ec0cab336e1e65f7575706b6a`. Human review is complete for
**1 of 10** pairs. The remaining nine pairs still require Anup's verdicts.

| Student | Claims supported by evidence? | Scores/evidence represented correctly? | Unsupported or invented claim? | Human result | Reviewer notes |
|---|---|---|---|---|---|
| STU0003 | Partly | Partly — marks match; some feedback and learning-outcome attributions do not. | Yes — assessment-to-feedback attributions described below. | NEEDS CORRECTION | Anup, 2026-10-03: verdict on the original plan; confirmed G01 and an additional OO Test feedback mismatch. A corrected revision is available below, pending human recheck. |
| STU0004 | Pending | Pending | Pending | Pending | |
| STU0022 | Pending | Pending | Pending | Pending | |
| STU0054 | Pending | Pending | Pending | Pending | |
| STU0055 | Pending | Pending | Pending | Pending | |
| STU0067 | Pending | Pending | Pending | Pending | |
| STU0075 | Pending | Pending | Pending | Pending | |
| STU0001 | Pending | Pending | Pending | Pending | |
| STU0005 | Pending | Pending | Pending | Pending | |
| STU0007 | Pending | Pending | Pending | Pending | |

### STU0003 — human adjudication

**Reviewer:** Anup. **Review date:** 2026-10-03.
**Decision:** Confirmed the proposed review; **NEEDS CORRECTION**.

- **G01 confirmed:** Section 2 attaches algorithm-comparison feedback
  (CSE2ALG:SILO4) to both the assignment and examination. The examination
  evidence lists SILO1, SILO2, SILO3 and SILO5; only the ALG assignment lists
  SILO4. The same exam attribution appears in the study actions. The marks
  63%, 64% and 66% match.
- **Additional source mismatch confirmed:** Section 1 says both the OO Test
  and exam markers noted real-life program design. The Test lists only
  CSE1OOF:SILO1 and SILO2; real-life program design is SILO4 and occurs in the
  exam feedback. Narrow the attribution to the relevant assessment.

Sources: [STU0003 plan](sprints/sprint-5/grounding-audit/plans/learning_plan_STU0003.md)
and [paired evidence](sprints/sprint-5/grounding-audit/evidence/evidence_STU0003.json).
This verdict adjudicates the saved plan; it does not establish that the
identified issues have been corrected or that a revised plan has passed review.

### STU0003 — corrected revision

A [corrected plan dated 3 October 2026](sprints/sprint-5/grounding-audit/revisions/2026-10-03/learning_plan_STU0003.md)
addresses both confirmed attribution issues:

- **Algorithm comparison:** Section 2 attributes CSE2ALG:SILO4 feedback to
  the assignment. The exam is linked to Java implementation (SILO3) and
  performance evaluation (SILO5). The comparison action is now a new practice
  exercise guided by assignment feedback, rather than a claim about unseen
  exam questions.
- **Real-life OO design:** Section 1 attributes CSE1OOF:SILO4 feedback to the
  exam. The statement shared by the Test and exam is limited to SILO1.

The [revised JSON](sprints/sprint-5/grounding-audit/revisions/2026-10-03/learning_plan_STU0003.json)
passes `validate_plan()` against the original paired evidence, and
`render_markdown()` reproduces the revised Markdown exactly. The
[verification record](sprints/sprint-5/grounding-audit/revisions/2026-10-03/STU0003-verification.json)
records the source revision, changed fields, and file hashes. The original
generated plan, evidence, machine results, and generation metadata remain
available for the audit trail. No regeneration or new LLM API call was made.

**Correction status:** Both confirmed attribution issues have been corrected
in the dated revision. **Independent human review of that revision: Pending.**
The human verdict above continues to describe the original plan and is not
automatically changed to PASS by the structured-reference check.

### Assisted review of all ten pairs — 3 October 2026

The [full comparison and correction register](sprints/sprint-5/grounding-audit/revisions/2026-10-03/review.md)
now covers all ten students. Eight plans have dated corrected versions;
STU0075 and STU0001 retain their original versions because no concern was
identified in the assisted comparison. The register links the current plan
for each student and describes each correction.

All ten selected versions pass structured grounding and rendering checks
against their saved evidence. The
[verification record](sprints/sprint-5/grounding-audit/revisions/2026-10-03/review-verification.json)
also checks the competency/subject/assessment relationships and confirms that
the original audit artifacts are unchanged. These assisted results do not
replace the independent human verdicts in the table above.

## Current conclusion

The automated portion of IOLG-121 passed for all ten fixed students with no retries or grounding failures.

Human review of the original audit set has recorded **one plan requiring
correction**, **zero human-approved passes**, and **nine pending verdicts**.
The assisted review of all ten pairs is complete, with corrected versions for
eight students and no change proposed for two. Human review of these current
versions remains pending, so IOLG-121's independent human review remains
incomplete.

The assisted pre-review demonstrates why the 10/10 structured-reference pass
must not be read as a 10/10 factual-prose pass. Complete the remaining human
adjudications and retain the recorded corrections as outstanding until there
is evidence that they have been resolved.
