// Builds learning-plan-traceability.docx. Needs the npm 'docx' package (v9): npm install docx, then node build_trace_doc.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, Header, Footer, PageNumber, PageBreak, LevelFormat,
  TableLayoutType, VerticalAlign,
} = require("docx");

const ROOT = "/home/acampton/CSE5IDP/LJA/LearningJourneyAssistant/docs/handover";
const DIAG = path.join(ROOT, "diagrams");
const OUT = path.join(ROOT, "learning-plan-traceability.docx");

const NAVY = "1F3864", BLUE = "2A78D6", INK2 = "52514E", LINE = "D0D4DB", FILL = "F2F5FA", NOTE = "FFF6E9", NOTE_EDGE = "C07520";
const CONTENT_DXA = 9412; // A4 width 11906 minus two 1247 DXA margins
const FONT = "Calibri";

// ---------- inline text: **bold**, *italic*, `code` ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 19, color: "3A3A3A", ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text, opts.run || {}), spacing: { after: 140, line: 288 }, ...opts.para });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true });
const H1keep = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const bullet = (t, level = 0) => new Paragraph({ numbering: { reference: "bullets", level }, children: runs(t), spacing: { after: 80, line: 276 } });
let listN = 0;
const numbered = (items) => { const ref = `num${listN++}`; return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 90, line: 276 } })); };

// ---------- figures ----------
let figN = 0;
function figure(file, widthPx, caption, alt, breakBefore = false) {
  const png = fs.readFileSync(path.join(DIAG, file));
  const w = png.readUInt32BE(16), h = png.readUInt32BE(20);
  const height = Math.round((widthPx * h) / w);
  figN += 1;
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, keepNext: true, pageBreakBefore: breakBefore, spacing: { before: 160, after: 80 },
      children: [new ImageRun({ type: "png", data: png, transformation: { width: widthPx, height }, altText: { title: `Figure ${figN}`, description: alt, name: file } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 240 },
      children: [new TextRun({ text: `Figure ${figN}. `, bold: true, size: 19, color: NAVY }), ...runs(caption, { size: 19, color: INK2 })],
    }),
  ];
}

// ---------- tables ----------
const border = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const borders = { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border };
let tabN = 0;
function table(caption, headers, rows, fractions) {
  const widths = fractions.map((f) => Math.round(CONTENT_DXA * f));
  widths[widths.length - 1] += CONTENT_DXA - widths.reduce((a, b) => a + b, 0);
  tabN += 1;
  const cell = (text, i, head, shade) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { type: ShadingType.CLEAR, fill: NAVY, color: "auto" } : shade ? { type: ShadingType.CLEAR, fill: FILL, color: "auto" } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    verticalAlign: VerticalAlign.TOP,
    children: String(text).split("\n").map((line) => new Paragraph({ spacing: { after: 30, line: 252 }, children: runs(line, head ? { bold: true, color: "FFFFFF", size: 19 } : { size: 19 }) })),
  });
  return [
    new Paragraph({ keepNext: true, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: `Table ${tabN}. `, bold: true, size: 19, color: NAVY }), ...runs(caption, { size: 19, color: INK2 })] }),
    new Table({
      width: { size: CONTENT_DXA, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED, borders,
      rows: [
        new TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, ri % 2 === 1)) })),
      ],
    }),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}

// ---------- callout and code ----------
function callout(title, lines, fill = FILL, edge = BLUE) {
  const e = { style: BorderStyle.SINGLE, size: 24, color: edge }, none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  return [
    new Table({
      width: { size: CONTENT_DXA, type: WidthType.DXA }, columnWidths: [CONTENT_DXA],
      borders: { top: none, bottom: none, right: none, left: e, insideHorizontal: none, insideVertical: none },
      rows: [new TableRow({ children: [new TableCell({
        width: { size: CONTENT_DXA, type: WidthType.DXA }, shading: { type: ShadingType.CLEAR, fill, color: "auto" },
        margins: { top: 120, bottom: 120, left: 220, right: 200 },
        children: [
          new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: title, bold: true, color: NAVY })] }),
          ...lines.map((l) => new Paragraph({ spacing: { after: 60, line: 276 }, children: runs(l) })),
        ],
      })] })],
    }),
    new Paragraph({ spacing: { after: 160 }, children: [] }),
  ];
}
function code(lines) {
  return lines.map((l, i) => new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: "F3F3F1", color: "auto" },
    spacing: { before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 200 : 0, line: 240 },
    indent: { left: 120, right: 120 },
    children: [new TextRun({ text: l || " ", font: "Consolas", size: 17, color: l.trim().startsWith("#") ? "6A6A6A" : "1B1B1B" })],
  }));
}

// ================= CONTENT =================
const title = [
  new Paragraph({ spacing: { before: 2600, after: 120 }, children: [new TextRun({ text: "LEARNING JOURNEY ASSISTANT  ·  HANDOVER", size: 20, color: BLUE, bold: true, characterSpacing: 40 })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "Learning Plans: The Evidence Behind Every Recommendation", size: 52, bold: true, color: NAVY })] }),
  new Paragraph({ spacing: { after: 480 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: BLUE, space: 12 } },
    children: [new TextRun({ text: "How each statement in a student's learning plan traces back to marked work, and why that traceability matters educationally", size: 28, color: INK2 })] }),
  ...table("Document details", ["Item", "Detail"], [
    ["Project", "CSE5IDP Industry Project: Learning Journey Assistant (LJA)"],
    ["Document", "Learning plan traceability, companion to the System Maintenance Document"],
    ["Version and date", "1.0, 27 September 2026"],
    ["Audience", "Project owner, project assessors, and the team that maintains the system next"],
    ["Evidence base", "Committed reference run in `data-fixtures/reference-run/` (qwen3-vl:30b, 25 Sep 2026); every figure re-checkable without an LLM call"],
  ], [0.24, 0.76]),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Contents")] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '1. Summary', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '2. What we built: the evidence lineage', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '3. A worked trace: one claim, back to the marks', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 60 }, indent: { left: 460 }, children: [new TextRun({ text: '3.1 The marks · 3.2 The outcomes and the competency · 3.3 The attainment figure', bold: false, size: 19, color: INK2 })] }),
  new Paragraph({ spacing: { after: 60 }, indent: { left: 460 }, children: [new TextRun({ text: '3.4 The verdict · 3.5 The plan and its grounding check · 3.6 Re-checking it yourself', bold: false, size: 19, color: INK2 })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '4. Why this matters educationally', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 60 }, indent: { left: 460 }, children: [new TextRun({ text: '4.1 Alignment · 4.2 Feedback · 4.3 Relative judgement · 4.4 Contestability · 4.5 Curriculum signal · 4.6 Tender requirements', bold: false, size: 19, color: INK2 })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '5. What the trace exposed', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: '6. Limits of what traceability proves', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: 'References', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: 'Appendix A. Files referred to', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { after: 100 }, indent: { left: 0 }, children: [new TextRun({ text: 'Appendix B. Glossary', bold: true, size: 23, color: NAVY })] }),
  new Paragraph({ spacing: { before: 360 }, children: runs("*Figures:* 1 Evidence lineage · 2 Worked trace for STU0003 · 3 The seven marks behind the claim · 4 STU0003's competency profile", { size: 19, color: INK2 }) }),
];

const s1 = [
  H1("1. Summary"),
  P("A learning plan tells a student which competencies to work on and what to do next. It is only useful if the student and their tutor can ask *why does it say that?* and get an answer they can check. The Learning Journey Assistant is built so that every stage of its pipeline leaves a file behind, and each file is the input to the next. A statement in a plan therefore has an unbroken chain back to specific marks, in specific assessments, against specific intended learning outcomes."),
  ...callout("The chain from marks to plan", [
    "**1. What was assessed.** The student's marks and marker feedback, and which subject intended learning outcomes (SILOs) each assessment covers.",
    "**2. What it is evidence of.** Which cross-subject competency each SILO belongs to, with the reason, after staff review.",
    "**3. Where the student stands.** Attainment in each competency, whether it is a gap, and the basis for that verdict.",
    "**4. What the model is shown.** Only this student's own evidence from stages 1 to 3.",
    "**5. What the student reads.** A plan whose every named competency, SILO, subject and assessment has been checked against stage 4.",
  ]),
  P("Checks sit between the stages, so a broken link stops the pipeline instead of passing silently. This document shows the chain (Section 2), walks one real claim back to the marks (Section 3), explains why this matters educationally (Section 4), and reports what the trace exposed (Section 5)."),
  H2("Key points"),
  bullet("**Every claim is traceable.** Section 3 follows STU0003's Data Structures gap from the plan back to seven marks in two subjects, and every number re-computes exactly."),
  bullet("**The model cannot invent.** Any competency, SILO, subject or assessment not in the student's own evidence makes the plan fail, and nothing is written."),
  bullet("**The educational case is alignment, actionable feedback and contestability.** Advice is tied to the outcomes the subject intended to teach, answers the three questions good feedback answers, and can be challenged link by link."),
  bullet("**The trace also exposed weaknesses.** The plan narrowed a two-subject gap to one subject, and on the supplied data the gap is only 1.3 marks. Both are reported, with responses."),
];

const s2 = [
  H1("2. What we built: the evidence lineage"),
  P("Figure 1 shows the five stages. Blue boxes are files a reader can open. Orange shapes are checks that stop the pipeline when they fail. The file at each stage is what makes the chain traceable: a reader does not have to trust the system's account of itself, because each link is written down."),
  ...figure("07-evidence-lineage.png", 540, "Evidence lineage of a learning plan: the file each stage leaves behind and the check between stages.", "Flowchart of five stages from workbook to learning plan, with coverage, staff review and grounding checks between them."),
  ...table("What each stage records, and the check before the next stage", ["Stage", "File a reader can open", "What it records", "Check before the next stage"], [
    ["1. What was assessed", "The workbook: `Results` and `Assessment Map` sheets", "Score, weight and marker feedback per assessment; the SILOs each assessment covers; SILO wording", "None. This is the source."],
    ["2. What it is evidence of", "`silo_clustering.json`\n`silo_clustering.review.json`", "Each SILO's competency and the model's rationale; the staff decision on each cluster", "**Coverage:** every SILO in exactly one competency, or the clustering is retried.\n**Review:** a rejected cluster stops everything downstream."],
    ["3. Where the student stands", "`gap_report.csv`", "Attainment per competency, subjects evidencing it, classification, **the basis for it**, relative position", "Thresholds are configuration recorded with the run, not hidden in code."],
    ["4. What the model is shown", "Rendered into the prompt", "This student's gaps, per-subject figures and trend, SILO wording, own scores and feedback. No other student's data.", "The vocabulary allowed in stage 5 is built from exactly this."],
    ["5. What the student reads", "`learning_plan_<id>.json` and `.md`", "Priorities naming competencies, SILOs, subjects and assessments, with evidence and actions; the evidence table the plan was grounded in", "**Grounding:** eight checks, including a scan of the prose for codes. Retry with the errors quoted back; after three failures, exit 1 and write nothing."],
  ], [0.17, 0.23, 0.32, 0.28]),
  H2("Two design choices that make the chain hold"),
  bullet("**The plan carries references, not just prose.** Each priority has separate fields for its competency, SILO keys, subject codes and assessment keys, so the validator has something concrete to check. The prose is scanned too, so \"revise CSE9XYZ\" inside a sentence is caught."),
  bullet("**Every verdict records how it was reached.** A gap row says whether it came from the student's relative position, an absolute floor or ceiling, or too little data. A reader never has to guess why a competency was called a gap."),
  P("The process view of the same steps, with the retry loop and exit codes, is Figure 5 in the System Maintenance Document."),
];

const s3 = [
  H1("3. A worked trace: one claim, back to the marks"),
  P("The claim traced here is priority 2 of the committed plan for student STU0003, in `data-fixtures/reference-run/plans/learning_plan_STU0003.json`."),
  ...callout("The claim", [
    "**Data Structures and Algorithms is a persistent gap for STU0003.**",
    "*Evidence as written in the plan:* \"CSE2ALG:Assignment (63.0%) and Central examination (64.0%) both cite 'consolidating underlying concepts' and 'applying them more consistently'…\"",
  ]),
  P("Figure 2 shows the whole trace on one page, with the real values at each step. The subsections that follow take each link in turn, from the source upwards."),
  ...figure("08-trace-stu0003.png", 520, "Tracing one learning-plan claim for STU0003 back to the workbook. Every value is taken from the committed reference run.", "Flowchart from workbook marks and SILOs through the cluster, attainment, relative position and gap report to the learning plan and its grounding check.", true),
  H2("3.1 The marks"),
  P("Seven of STU0003's eleven assessments cover at least one SILO in this competency: four in CSE1OOF and three in CSE2ALG. Figure 3 plots them. The two the plan quotes, the CSE2ALG Assignment and Central examination, are also the two heaviest-weighted assessments in CSE2ALG."),
  ...figure("10-stu0003-marks.png", 620, "The seven marks behind the claim. Dot area shows each assessment's weight within its subject; the dashed line is the competency attainment they produce.", "Dot plot of seven assessment scores between 60 and 66, coloured by subject, with a dashed line at 63.7 percent."),
  H2("3.2 The outcomes and the competency"),
  P("The clustering grouped six SILOs into one competency, *Data Structures and Algorithms*, and recorded its reason: the outcomes span \"identifying, implementing, comparing, and evaluating data structures and algorithms\" across CSE1OOF and CSE2ALG. The cluster is marked confirmed in the review file."),
  ...table("The SILOs in the competency, as worded in the Assessment Map", ["SILO", "Wording"], [
    ["CSE1OOF:SILO2", "abstract data types and encapsulation to localise and minimise change"],
    ["CSE2ALG:SILO1", "overall objectives of Algorithms and Data Structures"],
    ["CSE2ALG:SILO2", "identifying data structures and searching and sorting algorithms in computing contexts"],
    ["CSE2ALG:SILO3", "implementing data structures and searching and sorting algorithms in Java"],
    ["CSE2ALG:SILO4", "comparing algorithms and data structures and applying suitable choices to problems"],
    ["CSE2ALG:SILO5", "designing, implementing, and evaluating Java solutions using appropriate performance measures"],
  ], [0.22, 0.78]),
  H2("3.3 The attainment figure"),
  P("Each SILO an assessment covers counts as one observation, weighted by the assessment's weight. Table 3 shows the calculation in full; anyone can repeat it from the workbook."),
  ...table("How 63.7% is calculated from the seven marks", ["Assessment", "Score", "Weight", "SILOs in this competency", "Weight × SILOs", "Score × weight × SILOs"], [
    ["CSE1OOF Test", "60", "0.15", "SILO2 (1)", "0.15", "9.00"],
    ["CSE1OOF Practical demonstration", "63", "0.20", "SILO2 (1)", "0.20", "12.60"],
    ["CSE1OOF Assignment", "65", "0.25", "SILO2 (1)", "0.25", "16.25"],
    ["CSE1OOF Central examination", "62", "0.40", "SILO2 (1)", "0.40", "24.80"],
    ["CSE2ALG Test", "66", "0.20", "SILO1, 2, 3 (3)", "0.60", "39.60"],
    ["CSE2ALG Assignment", "63", "0.30", "SILO2, 3, 4, 5 (4)", "1.20", "75.60"],
    ["CSE2ALG Central examination", "64", "0.50", "SILO1, 2, 3, 5 (4)", "2.00", "128.00"],
    ["**Total: 15 observations**", "", "", "", "**4.80**", "**305.85**"],
  ], [0.27, 0.08, 0.10, 0.19, 0.14, 0.22]),
  P("305.85 ÷ 4.80 = **63.7%**, exactly the figure in the gap report."),
  H2("3.4 The verdict"),
  P("A competency is judged against the student's own profile, not a pass mark. STU0003's five competencies sit between 62.7% and 66.0%. Their median is 65.0 and their median absolute deviation (MAD) is 1.0. Data Structures sits (63.7 − 65.0) ÷ 1.0 ≈ −1.3 MADs from the median, recorded as −1.28 from the unrounded figures. That is past the −1.0 cutoff, so it is a gap. Because it shows in two subjects, it is a **persistent** gap. Figure 4 shows the profile."),
  ...figure("09-stu0003-profile.png", 620, "STU0003's competency profile. Blue dots fall below the cutoff of one MAD under the student's own median, and are classified as gaps.", "Dot plot of five competencies between 62.7 and 66.0 percent with the median at 65.0 and a cutoff at 64.0."),
  P("The gap report records all of this on one row: 63.7%, 2 subjects, *persistent gap*, basis *relative position*, −1.28."),
  H2("3.5 The plan and its grounding check"),
  P("The model was shown only STU0003's own evidence. Its priority names CSE2ALG:SILO2 to SILO5 and two CSE2ALG assessments, and quotes their scores. The grounding check found every name in the context, and the plan passed on its first attempt. The plan's Markdown file ends with the evidence table it was grounded in, so a reader holding only the plan can already check the figures."),
  H2("3.6 Re-checking it yourself"),
  P("From the `python/` folder on the main branch, with no LLM call:"),
  ...code([
    "R=../data-fixtures/reference-run",
    "python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx \\",
    "    --clustering-cache $R/silo_clustering.json",
    "grep STU0003 output/gap_report.csv                     # the verdict and its basis",
    "grep -A3 '\"Data Structures and Algorithms\"' \\",
    "    $R/silo_clustering.json                           # the cluster and rationale",
    "cat $R/plans/learning_plan_STU0003.md                  # the plan and evidence table",
  ]),
  P("The pipeline reproduces the committed `gap_report.csv` exactly, so the verdict is not a one-off."),
];

const s4 = [
  H1("4. Why this matters educationally"),
  H2("4.1 Advice stays aligned with what the subject intends to teach"),
  P("Constructive alignment (Biggs, 1996) holds that intended outcomes, teaching activities and assessment should all point at the same thing. The plan is built along that alignment in reverse: from marks, through the assessments that produced them, to the intended outcomes those assessments were designed to test. A recommendation is therefore about a named outcome the student was meant to achieve, not generic advice to study harder. A student told to work on CSE2ALG:SILO4 can open the subject guide and read exactly what that outcome asks of them."),
  H2("4.2 It answers the questions good feedback answers"),
  P("Hattie and Timperley (2007) frame effective feedback as answering three questions. Table 4 shows where each answer comes from in a plan, and why traceability matters for each."),
  ...table("The three feedback questions and how a traceable plan answers them", ["Feedback question", "What answers it in the plan", "Traced back to"], [
    ["*Where am I going?*", "The SILOs named in each priority, with their wording", "The Assessment Map: the outcomes the subject intends"],
    ["*How am I going?*", "The evidence text: the student's own figures and marker comments", "The Results sheet and the gap report, row by row"],
    ["*Where to next?*", "The actions, tied to named assessments and SILOs", "The gap classification and its basis"],
  ], [0.22, 0.42, 0.36]),
  P("Nicol and Macfarlane-Dick (2006) argue that feedback should help students regulate their own learning: clarify what good performance is, and give information they can act on. A claim the student can follow back to a specific assessment is one they can act on. A claim they cannot trace is one they can only accept or ignore."),
  H2("4.3 It judges students against themselves, not a pass mark"),
  P("The verdict in Section 3.4 compares a competency with the student's own profile. It is a formative signal about where this student's relative weakness lies, not a ranking against others. That is what the tender asked for: relative detection \"rather than raw pass or fail thresholds\". Because every verdict records its basis, a student at 65% is never quietly told the same thing as a student at 35%, and a reader can see which kind of statement they are looking at."),
  H2("4.4 Students and staff can question it"),
  P("Learning analytics raises questions of transparency, consent and student agency (Slade and Prinsloo, 2013). Students should be able to understand what is inferred about them, and challenge it. A traceable plan is a contestable plan: a student or tutor who disagrees with a claim can find the exact mark, outcome, competency grouping and threshold behind it, and point to the link they think is wrong."),
  P("This matters more when a language model writes the text, not less. The grounding check guarantees the model named nothing that was not in the student's own evidence, and the files let a person verify that guarantee rather than take it on trust."),
  H2("4.5 It gives staff a curriculum signal"),
  P("A persistent gap spans subjects. When many students share one, the trace leads to the SILOs and assessments involved across subject boundaries. That is evidence for a conversation about how an outcome is taught or assessed, which no single subject's results can show. The outcome-quality views in the dashboard build on the same links."),
  H2("4.6 It is what the tender promised"),
  ...table("Tender requirements met by the evidence lineage", ["Requirement", "What it asks", "How it is met", "Evidence"], [
    ["4: Relative gap detection", "Gaps judged against the student's own profile, not raw pass or fail thresholds", "Relative position in MAD units, with absolute guards; the basis recorded on every row", "Section 3.4, Figure 4, `gap_report.csv`"],
    ["5: Traceability", "A displayed figure can be traced to its source", "Each stage writes a file; the plan ends with its evidence table", "Figures 1 and 2, Section 3.6"],
    ["6: Grounded generation", "Generated content names only SILOs, subjects, assessments and competencies in the input; otherwise the build fails", "Eight grounding checks; retry with errors; exit 1 and nothing written", "Section 3.5; `tests/test_learning_plan.py`"],
  ], [0.2, 0.28, 0.3, 0.22]),
];

const s5 = [
  H1("5. What the trace exposed"),
  P("Tracing a real claim end to end surfaced four things a summary would hide. Reporting them is part of the point: a traceable system is one whose weaknesses can be found."),
  ...table("Findings from the worked trace", ["Finding", "Why it matters", "Response"], [
    ["**The plan narrowed a persistent gap to one subject.** The gap engine found Data Structures weak in CSE1OOF and CSE2ALG; the plan names only CSE2ALG.", "Grounding proves every name is real, not that the argument is complete. The student is not told the gap spans subjects.", "Study strategies (IOLG-123, PR #26) now require a persistent-gap entry to name at least two evidencing subjects. The same rule can be added to plans."],
    ["**On the supplied data the gap is tiny.** STU0003's whole profile spans 62.7% to 66.0%; the gap is 1.3 marks below the median.", "The trace proves the mechanism, not that this gap matters educationally.", "This is the flat-profile finding in ADR 0001. The 5000-student synthetic cohort has real spread, and there the same chain separates planted gaps from noise."],
    ["**\"Confirmed\" in the reference run is not a staff decision.** Clusters were confirmed in bulk so the pipeline runs offline.", "The review file records the state faithfully, but the decision behind it was mechanical.", "A real deployment needs staff review of each cluster (IOLG-124)."],
    ["**Marker feedback in the supplied data is templated.** Most of STU0003's comments share one sentence.", "The plan quotes it accurately, but it adds little to the student's understanding.", "With real marker feedback this link in the chain carries far more weight."],
  ], [0.36, 0.3, 0.34]),
  ...callout("A note for maintainers", [
    "Overall attainment counts one observation per SILO; the per-subject breakdown counts one per assessment. For STU0003 in CSE2ALG this gives 64.1% in the breakdown against 64.0% counted per SILO. Neither changes the verdict, but the two should be made consistent.",
  ], NOTE, NOTE_EDGE),
];

const s6 = [
  H1keep("6. Limits of what traceability proves"),
  bullet("**Existence, not correctness.** Grounding shows every name came from the evidence. It cannot show that the reasoning is sound or the tone is right. The human audit of ten plans (IOLG-121) covers that."),
  bullet("**The competency grouping is a judgement.** A model proposes it and staff confirm it. Traceability makes the grouping visible and reviewable; it does not make it right."),
  bullet("**One claim was traced by hand.** The files make any claim traceable, but this document walks through one. Generating a trace table automatically beside every plan would be a small extension."),
];

const refs = [
  H1("References"),
  ...[
    "Biggs, J. (1996). Enhancing teaching through constructive alignment. *Higher Education*, 32(3), 347–364.",
    "Hattie, J., & Timperley, H. (2007). The power of feedback. *Review of Educational Research*, 77(1), 81–112.",
    "Nicol, D. J., & Macfarlane-Dick, D. (2006). Formative assessment and self-regulated learning: a model and seven principles of good feedback practice. *Studies in Higher Education*, 31(2), 199–218.",
    "Slade, S., & Prinsloo, P. (2013). Learning analytics: ethical issues and dilemmas. *American Behavioral Scientist*, 57(10), 1510–1529.",
  ].map((t) => new Paragraph({ children: runs(t), spacing: { after: 140, line: 276 }, indent: { left: 567, hanging: 567 } })),
  H1keep("Appendix A. Files referred to"),
  ...table("Where each piece of evidence lives in the repository", ["File", "What it is"], [
    ["`data-fixtures/CSE_results_150_students_3_Subjects.xlsx`", "The supplied workbook: Results, Assessment Map and Student Summary sheets"],
    ["`data-fixtures/reference-run/silo_clustering.json`", "The committed clustering: five competencies with rationales"],
    ["`data-fixtures/reference-run/silo_clustering.review.json`", "Review decisions for each cluster"],
    ["`data-fixtures/reference-run/gap_report.csv`", "750 gap rows, one per student and competency, with basis and relative position"],
    ["`data-fixtures/reference-run/plans/learning_plan_STU0003.json` and `.md`", "The plan traced in Section 3"],
    ["`python/lja/model/learning_plan.py`", "Plan context, schema, grounding checks and generation loop"],
    ["`python/tests/test_learning_plan.py`", "The grounding test suite: one test per kind of invented name"],
    ["`docs/handover/diagrams/07-…` to `10-…`", "Sources for Figures 1 to 4 (Mermaid and PNG)"],
  ], [0.5, 0.5]),
  H1("Appendix B. Glossary"),
  ...table("Terms used in this document", ["Term", "Meaning"], [
    ["SILO", "Subject intended learning outcome: what a subject says a student should be able to do, written as `SUBJECT:SILOn`"],
    ["Competency", "A cross-subject skill formed by grouping related SILOs from different subjects"],
    ["Attainment", "A student's weighted mean score over the assessments that cover a competency's SILOs"],
    ["MAD", "Median absolute deviation: the median distance of a student's competency attainments from their own median; a robust measure of spread"],
    ["Relative position", "How many MADs a competency sits above or below the student's own median"],
    ["Persistent gap", "A gap evidenced in two or more subjects"],
    ["Isolated gap", "A gap evidenced in one subject only"],
    ["Grounding", "Checking that every name in generated text appears in the input the model was given"],
  ], [0.22, 0.78]),
];

// ================= DOCUMENT =================
const numberingConfig = [
  { reference: "bullets", levels: [
    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 280 } } } },
    { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 900, hanging: 280 } } } },
  ] },
];
for (let i = 0; i < 10; i++) numberingConfig.push({ reference: `num${i}`, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 320 } } } }] });

const doc = new Document({
  creator: "LJA project team",
  title: "Learning Plans: The Evidence Behind Every Recommendation",
  description: "Learning plan traceability, companion to the LJA System Maintenance Document",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: "1B1B1B" } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 34, bold: true, color: NAVY, font: FONT }, paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: BLUE, font: FONT }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: numberingConfig },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1247, bottom: 1247, left: 1247, right: 1247, header: 600, footer: 600 } }, titlePage: true },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: LINE, space: 4 } },
        children: [new TextRun({ text: "Learning plan traceability  ·  LJA handover", size: 17, color: INK2 })] })] }),
      first: new Header({ children: [new Paragraph({ children: [] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], size: 17, color: INK2 })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
    },
    children: [...title, ...s1, ...s2, ...s3, ...s4, ...s5, ...s6, ...refs],
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT, buf.length); });
