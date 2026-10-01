# IOLG-124: Staff review of the AI competency clusters

Reviewer: Sui Lung Tang.   Date reviewed: 26/9/2026.   Source: data-fixtures/reference-run/clusters.csv and silo_clustering.json (the reference run, generated with the local model qwen3-vl:30b).

## What you are doing

The AI read the 13 learning outcomes (SILOs) from the three subjects and put them into five groups, each with a name and a one-sentence reason. For each group, ask one question: would a lecturer say these outcomes describe the same skill? Then fill in the three grey columns.

- Agree: every outcome in the group belongs there.

- Disagree: at least one outcome clearly belongs somewhere else. Say which one and where.

- Unsure: you cannot tell from the wording.

Write one sentence of reasoning per group, and either a better group name or the word "keep".

| # | Competency label (AI) | Member SILOs | Member SILO texts (from the workbook) | AI's reason for the group | Your verdict<br>Agree / Disagree / Unsure | Why (one sentence) | Better label, or "keep" |
|---|---|---|---|---|---|---|---|
| 1 | Data Structures and Algorithms | CSE1OOF:SILO2, CSE2ALG:SILO1, CSE2ALG:SILO2, CSE2ALG:SILO3, CSE2ALG:SILO4, CSE2ALG:SILO5 | CSE1OOF:SILO2: abstract data types and encapsulation to localise and minimise change<br>CSE2ALG:SILO1: overall objectives of Algorithms and Data Structures<br>CSE2ALG:SILO2: identifying data structures and searching and sorting algorithms in computing contexts<br>CSE2ALG:SILO3: implementing data structures and searching and sorting algorithms in Java<br>CSE2ALG:SILO4: comparing algorithms and data structures and applying suitable choices to problems<br>CSE2ALG:SILO5: designing, implementing, and evaluating Java solutions using appropriate performance measures | Includes identifying, implementing, comparing, and evaluating data structures and algorithms (e.g., CSE1OOF SILO2 on abstract data types; CSE2ALG SILO2-5 on identifying, implementing, and applying algorithms), spanning CSE1OOF and CSE2ALG. | Agree | N/A |  |
| 2 | Object-Oriented Design and Implementation | CSE1OOF:SILO1, CSE1OOF:SILO3, CSE1OOF:SILO4 | CSE1OOF:SILO1: analysis/design/implementation compared with object-oriented modelling using objects that combine data structure and behaviour<br>CSE1OOF:SILO3: code sharing and reuse through object-oriented techniques to reduce development time<br>CSE1OOF:SILO4: object-oriented design and implementation of computer programs for real-life problems | No equivalent outcome found in the other subjects; includes analysis, design, and implementation of object-oriented systems (e.g., CSE1OOF SILO1, 3, 4 on OOP modelling and code reuse). | Disagree | The code exists but does not work. |  |
| 3 | Technical Communication and Documentation | CSE3CAP:SILO3, CSE3CAP:SILO4 | CSE3CAP:SILO3: reporting project outcomes to technical and non-technical audiences and reflecting on feedback<br>CSE3CAP:SILO4: professional system documentation and advanced technical reporting to industry standards | No equivalent outcome found in the other subjects; includes reporting outcomes to diverse audiences and professional system documentation (e.g., CSE3CAP SILO3 and SILO4). | Agree | The course that student is undertaking does not have a clear learning outcome on whether the student will attain what type of skill after undertaking this course. |  |
| 4 | Project Management | CSE3CAP:SILO1 | CSE3CAP:SILO1: advanced project management during substantive development implementation | No equivalent outcome found in the other subjects; includes advanced project management during substantive development implementation (CSE3CAP SILO1). | Agree | N/A |  |
| 5 | Industry Standards Application | CSE3CAP:SILO2 | CSE3CAP:SILO2: industry standard technical solutions in software or cybersecurity practice | No equivalent outcome found in the other subjects; includes applying industry standards to technical solutions (CSE3CAP SILO2). | Agree | 'industry standard technical solutions' names no action and no standard |  |

## SILOs the AI flagged as poorly worded

The AI could place these but said the wording is vague. Do you agree it is hard to place?

| SILO | Text | AI's reason for flagging | Agree it is vague? (yes/no) | Your comment |
|---|---|---|---|---|
| CSE2ALG:SILO1 | overall objectives of Algorithms and Data Structures | vague, does not specify a specific skill or knowledge area | Agree | N/A |
| CSE3CAP:SILO2 | industry standard technical solutions in software or cybersecurity practice | vague, lacks specific assessment criteria | Agree | Lack assessment criteria |

## Repository handling

The staff verdicts are recorded separately in `data-fixtures/reference-run/silo_clustering.review.sui-lung.json`.

The normal reference-run file `data-fixtures/reference-run/silo_clustering.review.json` remains all-confirmed so the offline quick-start continues to work.
