# Learning Journey Assistant — User Document

| | |
|---|---|
| **Status** | DRAFT 0.1 — for team review. Chapter 1 is a summary; the page-by-page walkthrough in Chapter 5 is marked ⚠ *TO FILL*. |
| **Date** | 29 September 2026 |
| **Describes** | `main` at `049b9ed` (29 Sep 2026), which includes every dashboard page except the priority groups, run page and glossary from open pull request #43 |
| **Audience** | Subject coordinators and course staff who read the dashboard; the project owner; anyone assessing what the numbers mean |
| **Project** | CSE5IDP Industry Development Project, Semester 2 2026, La Trobe University, Group 3 (Jira project IOLG) |
| **Project owner** | Dr Scott Mann |
| **Repository** | https://github.com/yetanotherpassword/LearningJourneyAssistant |
| **Companion documents** | The System Maintenance Document (`docs/handover/system-maintenance-document.md`, for whoever runs or changes the system; its Appendix B defines every metric formally), the learning-plan traceability note (`docs/handover/learning-plan-traceability.md`), the repository `README.md` |

---

## How to read this document

This document is for people who use the Learning Journey Assistant (LJA) rather than maintain it. It assumes nothing about the code. Where the System Maintenance Document (SMD) gives a formula, this document gives the reasoning and a worked example with real records.

Chapters 2 and 3 are the heart of it: how a subject's learning outcomes become cross-subject competencies, and how a student's marks become a place in one of three priority groups. Read them once and every number on the dashboard has a meaning. Chapter 4 walks one real student from each group through the rules.

Every threshold quoted here is the code default in force on the date above. They are proposals with measurements behind them, not ratified values; the open decision is action A-01 in `docs/meetings/actions.md`. The dashboard's "This run" page prints the values a particular run actually used.

---

## 1. What the dashboard is for

LJA reads the marks a cohort earned on their assessments, reads the learning outcomes those assessments were written against, and answers one question per student: *which competencies, if any, is this student weak in, and how sure can we be?*

Two processes sit behind every number on the dashboard:

1. **Clustering.** The learning outcomes written by each subject coordinator are grouped into cross-subject *competencies*. A language model proposes the grouping; staff confirm or reject each group before it is used.
2. **Classification.** Each student's assessment marks are read through those competencies, and each student is placed in one of three priority groups, or none. This part is plain arithmetic with no language model involved.

The dashboard then shows the cohort (who to look at first), each student (what exactly is weak, and the marks behind it), and the outcomes themselves (which learning outcomes are vague, isolated or never assessed).

---

## 2. How subject outcomes become competencies

A SILO is a Subject Intended Learning Outcome: one sentence a subject promises its students will be able to do. The identifiers restart in every subject, so `CSE2ALG SILO2` and `CSE1OOF SILO2` have nothing in common except the number. Only the wording matters.

The language model reads every SILO in the suite and groups those that describe the same underlying skill, wherever they sit in the degree. Staff then confirm or reject each group before any student is classified against it.

![Figure 1: How SILOs become competencies](diagrams/11-silo-clustering-flow.png)

*Figure 1: The instructions the model works under, in order. Grouping by subject is the one thing it must not do; a single-subject group is allowed only after every other subject has been checked. The dashed loop is the machine check that catches a dropped or doubled SILO. Numbered badges match the steps below. Amber LLM CALL marks a judgement made by the language model; steps 2 to 5 are produced in one structured response to a single prompt, not one call per SILO. The completeness check is plain code and the review is human.*

The worked example below uses the three-subject fixture in the repository (CSE1OOF, CSE2ALG, CSE3CAP: thirteen SILOs) and the model's actual output on it.

### Step 1. Start from the wording *(code)*

Thirteen SILOs across a first-year, a second-year and a capstone subject, read straight from the workbook. No model is involved yet. Two of them, from different subjects and different years:

| SILO | Wording |
|---|---|
| `CSE1OOF SILO2` | abstract data types and encapsulation to localise and minimise change |
| `CSE2ALG SILO4` | comparing algorithms and data structures and applying suitable choices to problems |

### Step 2. Compare across subjects, not within *(LLM decides)*

This is the language model's judgement, made from the wording alone under the instructions in Figure 1. The two sentences share almost no words. The question is whether a student who is weak at one would be weak at the other. Choosing an abstract data type and choosing a data structure for a problem are the same judgement at two points in the degree, so they match.

By contrast, the capstone's "reporting to technical and non-technical audiences" is communication, a different skill, so it is not pulled in even though it mentions technical work.

### Step 3. Name the group and justify it *(LLM decides)*

> **Data Structures and Algorithms**
>
> "Includes identifying, implementing, comparing, and evaluating data structures and algorithms (CSE1OOF SILO2 on abstract data types; CSE2ALG SILO2 to 5 on identifying, implementing, comparing and evaluating them)."
>
> Members: `CSE1OOF SILO2`, `CSE2ALG SILO1`, `CSE2ALG SILO2`, `CSE2ALG SILO3`, `CSE2ALG SILO4`, `CSE2ALG SILO5`

The label is a few words a coordinator would recognise. The rationale points at the SILO text and names the subjects spanned, so a reviewer can check it without re-reading the whole suite.

### Step 4. Single-subject groups are a last resort, and say so *(LLM decides)*

> **Technical Communication and Documentation**
>
> "No equivalent outcome found in the other subjects; includes reporting outcomes to diverse audiences and professional system documentation."
>
> Members: `CSE3CAP SILO3`, `CSE3CAP SILO4`

### Step 5. Flag vague wording, but still place it *(LLM decides)*

| SILO | Wording | Flag |
|---|---|---|
| `CSE2ALG SILO1` | overall objectives of Algorithms and Data Structures | does not name a specific skill |

The flag is feedback for the coordinator who wrote it, not a judgement on any student. The SILO still sits in the group above, because every SILO must land somewhere or a student's marks against it would silently vanish.

### Step 6. Check, then hand to staff *(code check, then staff decide)*

The completeness check is ordinary code, not a model: it confirms all 13 SILOs appear exactly once and none were invented. If the model dropped one, a fresh LLM call is made with the missing SILO named, up to three times in total.

The five resulting groups then sit as **pending** until staff mark each **confirmed** or **rejected** with a note. Gap detection will not run on a rejected group, and warns on pending ones. The dashboard carries the same warning on every page while any group used in the run is still pending.

---

## 3. How a student's marks become a priority group

Every assessment result carries a score, a weight, and the SILOs it assessed. Through the confirmed groups, each SILO points to one competency. A student's marks are pooled per competency into a single attainment figure, each figure is classified against both fixed cut-offs and the student's own profile, and the classifications decide the group.

**No language model is involved anywhere in this part.** Every step is arithmetic on the marks and the confirmed groups, so the same input always gives the same answer.

![Figure 2: How a student's marks become a priority group](diagrams/12-classification-flow.png)

*Figure 2: Deterministic code throughout, no LLM call. The order of the tests is deliberate. A student weak everywhere has a flat profile, so a relative test alone would call every competency "developing"; the 50% floor is checked first so that student still surfaces. The groups add no new threshold: they only combine labels already given.*

### 3.1 The steps

1. **Pool each student's marks per competency.** Attainment is the weighted mean of every score whose SILOs map to that competency. The number of different subjects that supplied evidence is counted at the same time.
2. **Describe the student's own profile.** Take the median of their competency attainments, and the MAD: the median distance of those attainments from that median.
3. **Classify each competency, fixed cut-offs first.** Below the 50% floor is a gap whatever the profile looks like. At or above the 75% ceiling is proficient whatever the profile looks like. The absolute guards go first because a flat profile can hide them.
4. **Otherwise, use the relative position:** (attainment − median) ÷ MAD. At or below −1 MAD is a gap relative to the student's own median; at or above +1 MAD is proficient; between is developing, neither gap nor strength. The relative test needs at least 4 competencies and a MAD of at least 1; with less profile than that, a plain 65% split is used instead and the basis says so.
5. **For each gap, count the subjects that evidenced it.** Two or more makes it a *persistent gap*; just one makes it an *isolated gap*. A gap that recurs across subjects is a habit; one seen once may be a bad day. The data cannot tell them apart, so the label carries the distinction.
6. **Place the student. The first rule that fires wins.**
   - **1st priority:** any gap classified by the absolute floor.
   - **2nd priority:** no floor breach, but at least one persistent gap.
   - **3rd priority:** isolated gaps only.
   - No gap at all: no group.

### 3.2 The numbers in play

| Rule | Value | What it does |
|---|---|---|
| Absolute floor | 50% | Below this a competency is a gap regardless of the profile. |
| Absolute ceiling | 75% | At or above this it is proficient regardless of the profile. |
| Relative gap cut-off | −1.0 MAD | At or below this many MADs under the median, a gap. |
| Relative strong cut-off | +1.0 MAD | At or above this, proficient. |
| Minimum competencies | 4 | Fewer than this and the profile is too thin to reason relatively. |
| Minimum spread | 1.0 | MAD under this is a flat profile; fall back to a plain 65% split. |
| Persistent needs | 2 subjects | A gap evidenced by two or more subjects is persistent. |

MAD is the median absolute deviation, unscaled. If a student's attainments are 62, 58, 66, 61 and 70, the median is 62, the distances from it are 0, 4, 4, 1 and 8, and the MAD is 4. A mark of 58 then sits at −1.0 MAD: on the line, and a gap.

**Why relative at all?** Two students can both score 58 in a competency. For one it is their usual level, for the other it is far below everything else they do. The second student has something specific to fix, and a fixed threshold cannot see that.

**The catch.** By construction roughly a quarter of every student's competencies fall below −1 MAD, so the relative rule alone flags almost everyone. On the 5,000-student run, 4,195 students had a persistent gap but only 1,145 of them had any mark under 50. The priority groups exist to separate those two cases.

---

## 4. One real student from each group

Each plot is that student's competency profile from the 100-subject, 5,000-student synthetic run. Every dot is one competency's attainment. The shaded band is the student's median ±1 MAD; the two dashed vertical rules are the fixed 50% floor and 75% ceiling. The filled coloured dot is the competency that decided the group: red for a gap by the floor, amber for a persistent gap found relatively, blue for an isolated gap found relatively. Hollow dots are competencies that are not gaps.

### 4.1 1st group: STU2009

At least one competency below the 50% floor. A gap whatever the rest of the profile looks like.

STU2009 · 12 competencies · median 62.0 · MAD 3.75

![Figure 3: STU2009's competency profile](diagrams/13-profile-p1-STU2009.png)

**Why 1st.** *Applying analytical and computational methods* is 48.9%, pooled from 3 assessments in 2 subjects.

1. 48.9 is below the 50 floor, so it is a gap on the absolute rule before any profile arithmetic.
2. Two subjects evidenced it, so the gap is **persistent**.
3. A floor-based gap exists, so the student is in the 1st group. Their second gap (56.8, at −1.38 MAD, also persistent) does not change that.

### 4.2 2nd group: STU0794

No mark under the floor, but at least one persistent gap. Flagged only relative to the student's own median.

STU0794 · 10 competencies · median 83.8 · MAD 6.05

![Figure 4: STU0794's competency profile](diagrams/13-profile-p2-STU0794.png)

**Why 2nd.** *Understanding biochemical processes* is 74.6%, pooled from 10 assessments in 3 subjects.

1. 74.6 is above the floor and just under the 75 ceiling, so the relative test applies: (74.6 − 83.8) ÷ 6.05 = **−1.53 MAD**, past the −1 cut-off. A gap.
2. Three subjects evidenced it, so it is **persistent**.
3. Nothing breached the floor, so this is the 2nd group. A strong student with one recurring soft spot: 74.6% would be a pass anywhere else on this page.

### 4.3 3rd group: STU0772

Isolated gaps only: every gap was evidenced by a single subject. Could be real, could be one bad assessment.

STU0772 · 11 competencies · median 83.0 · MAD 4.30

![Figure 5: STU0772's competency profile](diagrams/13-profile-p3-STU0772.png)

**Why 3rd.** *Conducting laboratory experiments* is 69.7%, pooled from 3 assessments in 1 subject.

1. Above the floor, below the ceiling, so relative: (69.7 − 83.0) ÷ 4.30 = **−3.06 MAD**. A deep gap for this student.
2. Only one subject evidenced it, so it is **isolated**, however deep.
3. No floor breach and no persistent gap, so the 3rd group. The depth is why it still appears; the single source is why it ranks last.

### 4.4 The profiles behind the plots

| Student | Competency | Attainment | Classification |
|---|---|---|---|
| STU2009 | Applying analytical and computational methods | 48.9 | gap, absolute floor |
| STU2009 | Applying biological knowledge to environmental challenges | 56.8 | persistent gap, relative |
| STU2009 | Conducting laboratory experiments | 58.3 | |
| STU2009 | Analysing agricultural systems | 61.0 | |
| STU2009 | Applying microbiological techniques in diagnostics | 61.4 | |
| STU2009 | Understanding biochemical processes | 62.0 | |
| STU2009 | Applying mathematical models to real-world phenomena | 62.0 | |
| STU2009 | Adapting scientific communication | 64.3 | |
| STU2009 | Applying experimental methods to scientific investigation | 65.8 | |
| STU2009 | Formulating evidence-based arguments | 65.9 | |
| STU2009 | Critical analysis of literary texts | 66.3 | |
| STU2009 | Analyzing literary works and genres | 69.8 | |
| STU0794 | Understanding biochemical processes | 74.6 | persistent gap, relative |
| STU0794 | Applying biological knowledge to environmental challenges | 77.6 | |
| STU0794 | Conducting laboratory experiments | 77.7 | |
| STU0794 | Applying analytical and computational methods | 77.8 | |
| STU0794 | Applying experimental methods to scientific investigation | 79.6 | |
| STU0794 | Analysing agricultural systems | 88.0 | |
| STU0794 | Critical analysis of literary texts | 88.2 | |
| STU0794 | Adapting scientific communication | 89.1 | |
| STU0794 | Analyzing literary works and genres | 90.0 | |
| STU0794 | Formulating evidence-based arguments | 90.2 | |
| STU0772 | Conducting laboratory experiments | 69.7 | isolated gap, relative |
| STU0772 | Applying technical and business skills | 76.0 | |
| STU0772 | Applying biological knowledge to environmental challenges | 78.7 | |
| STU0772 | Analyzing literary works and genres | 79.8 | |
| STU0772 | Formulating evidence-based arguments | 82.1 | |
| STU0772 | Critical analysis of literary texts | 83.0 | |
| STU0772 | Applying analytical and computational methods | 84.1 | |
| STU0772 | Adapting scientific communication | 86.3 | |
| STU0772 | Understanding biochemical processes | 87.5 | |
| STU0772 | Analysing agricultural systems | 89.0 | |
| STU0772 | Applying experimental methods to scientific investigation | 89.8 | |

---

## 5. Page-by-page walkthrough ⚠ *TO FILL*

This chapter will walk each dashboard page in the order a coordinator meets them, with a screenshot and what every tile, column and badge means. Planned sections, matching the navigation bar:

- 5.1 Students: the cohort statistics, the two summary charts, the severity chart, the three priority groups and the full table (search, sort, expand).
- 5.2 A student's page: strengths, progress across subjects, competency gaps with their evidence, recommended next actions.
- 5.3 Outcome quality: SILO wording flags, competency progression, subject coverage.
- 5.4 Competency clusters: the confirmed groups and their members.
- 5.5 This run: the thresholds and data files behind the numbers on screen.
- 5.6 Glossary: every term with a `?` link.
- 5.7 The learning plan and study-strategy commands, for staff who run them.

---

## Appendix A. Sources and status of the numbers

**Sources.** Chapter 2 follows the system prompt the clustering model runs under and the staff review states in the review tool; the example groups are the model's own output on the 3-subject fixture (CSE1OOF, CSE2ALG, CSE3CAP). Chapters 3 and 4 follow the classification routine and the priority rule in the dashboard; the three students are real rows from the 100-subject, 5,000-student synthetic catalogue run, with attainments and positions as computed there.

**Status of the numbers.** The seven thresholds in §3.2 are the code defaults, configurable per run and shown on the dashboard's "This run" page. They are proposals with measurements behind them, not ratified values; ratifying or replacing them is open action A-01. The formal definition of every metric, with its formula and where it is calculated and shown, is Appendix B of the System Maintenance Document.

**Figures.** Figures 1 to 5 are rendered from the explainer page "From SILOs to Priority Groups" (29 Sep 2026); the PNGs are under `docs/handover/diagrams/` as files 11 to 13.

## Appendix B. Change log

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 29 Sep 2026 | Allan Campton (drafted with Claude Code) | First draft: Chapters 1 to 4 from the "From SILOs to Priority Groups" explainer; Chapter 5 outlined. |
