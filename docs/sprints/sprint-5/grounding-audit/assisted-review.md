# Assisted review of the ten learning plans — IOLG-121

Prepared 28 September 2026 for Anup and Istiaque, against repository
revision `ffa53d54c65946d252e4e1f987c294da2e59da23`.
**Human review and sign-off are pending.** This is an AI-assisted comparison,
not evidence that Anup personally reviewed or approved these plans.

## Method

Read each saved Markdown plan against its paired evidence JSON: competency
attainment and classification, per-subject values, assessment marks, SILO
membership, feedback, and the distinction between recommendations and claims
about what already happened. Specific assessment questions, missing report
sections, and individual marking reasons are not supplied by these records.

For all ten students, the saved evidence was also compared with a fresh
`build_plan_context()` from the workbook and committed reference clustering.
All ten matched. `validate_plan()` accepted all saved JSON plans, and
`render_markdown()` reproduced all saved Markdown plans. No new LLM call was
made. These checks verify source correspondence and known references, not
the truth of natural-language claims. The reference clustering's bulk
confirmation is a demo convenience, as its README explains; this review
does not independently approve that clustering.

## Proposed entries for the brief's review table

Y in the first two columns means the named entities exist; it does not mean
every relationship or assertion about them is correct. The fourth column
records unsupported factual statements as well as misattributed feedback.
Suggested study activities are acceptable when presented as recommendations,
without pretending that an unseen assessment or comment contained them.

| student_id | every competency named in the plan exists in the gap rows? (Y/N) | every subject/assessment named exists? (Y/N) | any mark, grade or feedback quoted that is not in the records? (list, or none) | tone: does it tell the student what to do, not just what is wrong? (Y/N) | one-line comment |
| --- | --- | --- | --- | --- | --- |
| STU0003 | Y | Y | G01: the algorithm-comparison feedback is attributed jointly to the assignment and exam, but the exam evidence excludes SILO4. | Y | Marks agree; narrow the assessment-to-feedback attribution. |
| STU0004 | Y | Y | G02: “making steady progress” is not supported by a measured improvement over time. | Y | Marks and gap labels agree; describe the current profile without inventing progress. |
| STU0022 | Y | Y | G03: says gaps arise largely because of marker feedback; G04: misidentifies the two weakest OO assessments. | Y | Explain the score-based relative signal and correct the assessment ordering. |
| STU0054 | Y | Y | G05: says all three OO assessments flagged combining data and behaviour, which only the exam evidence names. | Y | Marks agree; separate the shared themes from the exam-only theme. |
| STU0055 | Y | Y | G06: attributes “tighter links between decisions and implementation” to Sprint reports; that phrase occurs in other assessments' feedback. | Y | Use the Sprint reports' actual request for reasoning, precision, and testing/reflection. |
| STU0067 | Y | Y | G07: summary says “two persistent computing gaps”; only Data Structures and Algorithms is persistent. | Y | Correct the summary to one persistent and one isolated computing gap. |
| STU0075 | Y | Y | none identified in this assisted comparison | Y | 72.0% isolated OO and 73.4% persistent algorithms match; suggested practice is actionable. |
| STU0001 | Y | Y | none identified in this assisted comparison | Y | Three capstone isolated gaps and 50.7% developing algorithms match the records. |
| STU0005 | Y | Y | G08: says the exam and test contain SILO4 questions; G09: converts improvement feedback into claims of missing testing. | Y | All competencies are proficient; correct unsupported details in the actions. |
| STU0007 | Y | Y | G10: asserts missing report sections and specific missing audience/reflection points that the generic feedback does not identify. | Y | Keep the proposed revision activities and remove unobserved omissions. |

## Findings with source references

These are review findings to confirm or adjudicate with Anup. They do not
silently rewrite the original generated plans or the recorded machine audit.

### G01 — STU0003: feedback attached to the wrong assessment

[Plan](plans/learning_plan_STU0003.md), section 2 Evidence, says the assignment
and examination were flagged for comparing algorithms (CSE2ALG:SILO4).
The [evidence](evidence/evidence_STU0003.json), `assessments` entry
`CSE2ALG:Central examination`, lists SILO1, SILO2, SILO3, and SILO5 and does not
mention comparison in its feedback. SILO4 belongs to the assignment evidence.
Refer to the assignment for comparison and the exam for implementation and
evaluation. The marks 63.0%, 64.0%, and 66.0% themselves match.

### G02 — STU0004: unsupported progress claim

The [plan](plans/learning_plan_STU0004.md) opens with “making steady progress”.
The [evidence](evidence/evidence_STU0004.json) supplies a current profile;
the only cross-subject trend is `stable` for Data Structures and Algorithms,
while other competencies say `insufficient evidence`. It provides no dated
improvement series. This is an unsupported inference, not a proven decline.
Replace it with a neutral description of the current results. The 48.9%
persistent algorithms gap and assessment marks are supported.

### G03–G04 — STU0022: cause of gaps and weakest assessments

The [plan](plans/learning_plan_STU0022.md) summary says the gaps appear
“largely because of a recurring theme in marker feedback”.
[Gap detection](../../../../python/lja/model/gap_detection.py) uses weighted
scores and profile thresholds, not feedback text. Feedback informs the
study suggestions; it does not cause the gap classification.

Section 2 calls the practical demonstration (71.0%) and exam (73.0%) the
weakest OO results. The [evidence](evidence/evidence_STU0022.json) also has
the Test at 72.0%, below the exam and mapped to CSE1OOF:SILO1. The two lowest
OO assessments are therefore the practical demonstration and Test. Keep
73.0% as the correct exam mark, but correct its ranking.

### G05 — STU0054: a shared-feedback claim is too broad

Section 4 of the [plan](plans/learning_plan_STU0054.md) says the exam,
assignment, and practical demonstration “all flagged” combining data and
behaviour. In the [evidence](evidence/evidence_STU0054.json), that SILO1
theme appears in the exam, while the assignment and practical demonstration
have SILO2, SILO3, and SILO4. Split the statement: all three support reuse
and design concerns; the exam supports the SILO1 concern. The 47.6%
competency value and the 48.0%, 49.0%, and 44.0% marks agree.

### G06 — STU0055: a marker request is misattributed

Section 3 of the [plan](plans/learning_plan_STU0055.md) attributes
“tighter links between decisions and implementation” to the Sprint reports.
The [evidence](evidence/evidence_STU0055.json) for
`CSE3CAP:Assignment: Sprint Project management reports` actually asks for
clearer reasoning, technical precision, and more complete testing or
reflection. The quoted theme belongs to the stronger-result feedback on
the final written report and ALG Test. It is a reasonable study suggestion
but should not be described as this marker's comment.

### G07 — STU0067: persistent-gap count contradicts the evidence

The [plan](plans/learning_plan_STU0067.md) summary says “two persistent
computing gaps”. The [evidence](evidence/evidence_STU0067.json) classifies
Data Structures and Algorithms at 40.2% as persistent and Object-Oriented
Design and Implementation at 42.6% as isolated. The plan's detailed
sections already use those correct labels. Correct the summary to one
persistent algorithms gap and one isolated OO gap.

### G08–G09 — STU0005: unseen question content and missing-work claims

Section 3 Actions in the [plan](plans/learning_plan_STU0005.md) says the
ALG exam and Test contain questions covering CSE2ALG:SILO4. Neither
assessment lists SILO4 in the [evidence](evidence/evidence_STU0005.json);
the assignment does. Link comparison practice to the assignment or make it
an explicitly new exercise.

Sections 1 and 2 also say the marker flagged testing as “missing”. The
relevant feedback asks for “more complete testing or reflection”; it does
not establish absent testing. Preserve that weaker, accurate wording.

### G10 — STU0007: invented omissions in submitted work

Section 1 Actions in the [plan](plans/learning_plan_STU0007.md) asks for
“the missing sections it lacked” and specific missing audience/reflection
points. The [evidence](evidence/evidence_STU0007.json) gives general feedback
about consistency, underlying concepts, and stronger design evidence; it
does not identify missing sections or specific omitted points. Recommend
checking the report against a template and expanding reflection without
asserting omissions that have not been observed.

## Human completion

Anup should inspect every pair, confirm or correct this table, and record
the final verdict, name, and date in [the main audit](../../../grounding-audit.md#independent-human-review).
Istiaque can then correct/regenerate the affected plans, preserve the old
audit evidence, rerun grounding checks, and submit the new plans for review.
Two rows with no concern identified here are not human-approved passes.
