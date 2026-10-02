# Learning Journey Assistant — Requirements Status

| | |
|---|---|
| **Version** | 1.0, 3 October 2026 |
| **Purpose** | Status of every functional and non-functional requirement in `LJA -- Requirements_for_SILO_analysis.pdf` (the team's record of the 11 August 2026 meeting with the project owner) against `main` at `b4ccebd`. That PDF is a source document and is left as written; this page is the trace. |
| **Reading the status** | **Met**: on `main` with evidence. **Partly**: a bounded slice exists; the limit is stated. **Not built**: with the reason. **Superseded**: the requirement was replaced by a recorded decision. |
| **Source** | `docs/design/requirements-status.md`; rebuild with `docs/design/build.sh` |

## Functional requirements

| ID | Requirement (abridged) | Status | Where, and what to know |
|---|---|---|---|
| FR-1.1 | Parse the workbook's three tabs into a normalised model | Met | `lja.data.excel_loader` → `LjaDataset`; a malformed workbook is an error |
| FR-1.2 | Assessment to SILO is one-to-many | Met | `Assessment.silo_ids`; one score counts towards every SILO it covers (documented approximation) |
| FR-1.3 | Idempotent, re-runnable ingestion | Met | Pure in-memory load; no database writes |
| FR-1.4 | Source adapter interface; spreadsheet and Moodle populate the same model | Met | `--source excel\|moodle` on every command; the Moodle loader was added with no change to clustering or gap detection |
| FR-1.5 | Pseudonymise student id at ingest | Partly | Not at ingest: ids stay as supplied (synthetic `STU0001`-style). Pseudonymisation exists at export (`lja.export --anonymise`, keyed HMAC). Before real data touches a cloud provider, pseudonymise at ingest (SMD §3.8) |
| FR-1.6 | Reject malformed rows and report | Met | Loader raises on unmapped criteria and malformed sheets rather than dropping rows; no separate quality report |
| FR-1.7 | Ingest a course map when supplied | Partly | The slot exists: `LJA_SUBJECT_SEQUENCE` orders subjects and `trajectory.py` labels its source. No course map has been supplied, so the default is the three supplied subjects and other subjects fall back to the year digit |
| FR-2.1 | Stable SILO identity plus verbatim text | Met | `Silo(subject_code, silo_local_id, text)`, keyed `SUBJ:SILOn` |
| FR-2.2 | Subject level and provenance | Partly | Year level read from the subject code; the catalogue carries provenance (`source: handbook\|synthetic`) but the workbook path does not |
| FR-2.3 | SILO text immutable, versioned | Not built | No versioning; a re-cluster on changed wording produces new cluster ids (a hash of members), which is the practical safeguard |
| FR-2.4 | 30+ subjects without schema change | Met | The 100-subject, 5,000-student cohort runs through the unchanged pipeline (`data-fixtures/README-handbook-cohort.md`) |
| FR-3.1 | Semantic similarity across SILO pairs via embeddings and/or LLM | Met, by a different route | Direct LLM clustering of the whole suite (ADR 0002), not pairwise scores; the embedding tagger (`competency_tagger`) exists for the catalogue and is the staged route for the pipeline |
| FR-3.2 | No keyword matching in production | Met | None used |
| FR-3.3 | Configurable similarity threshold recorded per map | Superseded | No pairwise threshold exists under ADR 0002; the clustering cache records the model and the gate records decisions |
| FR-3.4 | Every edge stores score, rationale, model, prompt version, timestamp | Partly | Each cluster stores a rationale; the model and prompt version are not written into the cache (debt item 3, A-29) |
| FR-3.5 | Academic can accept, reject or adjust; overrides persist | Met, CLI only | `lja.review`: pending / confirmed / rejected with a note, kept beside the cache, surviving re-clustering for unchanged clusters. No browser UI |
| FR-3.6 | SILO graph exportable for network visualisation | Partly | The dashboard draws the competency-to-subject-to-outcome trace and a chord diagram; `clusters.csv` is the flat export. No node/edge file |
| FR-3.7 | Incremental recomputation | Not built | A new subject re-clusters the suite; the gate's decisions survive |
| FR-4.1 | Cluster linked SILOs into competencies | Met | `silo_clustering`, with coverage validation and retry |
| FR-4.2 | Label and describe each competency | Met | Label and rationale per cluster, reviewed by staff (IOLG-124) |
| FR-4.3 | A SILO may belong to more than one competency | Superseded | Deliberately exactly one, so attainment is not double-counted; the grounding check enforces it |
| FR-4.4 | Each competency resolves to SILOs, subjects, levels, assessments | Met | The competency page's trace: competency → subjects → outcomes → assessments |
| FR-4.5 | Labels editable and lockable | Partly | Rejecting with a note is the edit path; no relabel-in-place |
| FR-5.1 | Per-student competency score aggregated through assessment → SILO → competency | Met | `compute_gaps()`, weighted by assessment weight |
| FR-5.2 | Pluggable aggregation, default unweighted mean | Met, by a different default | Weighted mean; weights of 1.0 reproduce the unweighted case |
| FR-5.3 | Intra-student deficiency relative to the student's own profile | Met | Median and MAD within the profile, with absolute guards (ADR 0001); thresholds unratified (A-01) |
| FR-5.4 | Inter-student deficiency against the cohort | Partly | Cohort statistics and priority groups show where a student sits; no per-competency cohort-relative classification, by decision (SMD D8) |
| FR-5.5 | Track scores across levels 1, 2, 3 to expose trajectory | Met | `trajectory.py`: declared subject sequence, trend with its basis, subjects ahead (IOLG-106) |
| FR-5.6 | Every flagged gap drills down to its assessments, SILOs and scores | Met | The gap card's evidence table and basis line; the Provenance page |
| FR-5.7 | Thresholds configurable | Met | Seven `LJA_GAP_*` variables, CLI flags, shown on the Provenance page |
| FR-5.8 | Reproduce the workbook's at-risk band alongside computed gaps | Met | Performance band on the student list and page; the dashboard's own at-risk cohort is deliberately undefined (D11) |
| FR-6.1 to 6.5 | Feedback comment analysis | Not built | The supplied feedback is 45 templated strings across 1,650 rows; the owner flagged bespoke feedback as a re-identification risk. The synthetic generators (FR-6.4) exist and flag synthetic rows |
| FR-7.1 | Ranked interventions per gap | Met | Learning plan priorities in order |
| FR-7.2 | Three intervention classes: subjects, resources, quizzes/study material | Partly | Study strategies and practice quizzes exist; external resources and subject suggestions do not, and subject advice is excluded by the guardrails (SMD D19) |
| FR-7.3 | Recommendations contextualised to the forward plan and course map | Partly | The trajectory names where a gap is assessed next; the strategy's `prepare_for` names it; no course map yet |
| FR-7.4 | Every recommendation cites its gap and evidence | Met | Grounding by code: every name must exist in the student's own context |
| FR-7.5 | Trigger decoupled from the end-of-semester batch | Met | Each generator is its own command; the dashboard's opt-in button (PR #55) runs it on demand |
| FR-8.1 | Assess SILO clarity, specificity, measurability, isolation | Met | `silo_quality`: flagged, orphan, unassessed, vague wording; the `/silos` page and lists |
| FR-8.2 | Report for coordinators with justification and rewording | Partly | The lists are the report; no suggested rewording |
| FR-9.1 | Export competency map, gaps and intervention log, CSV and JSON | Met, CSV | `lja.export`: three CSVs plus a JSON manifest; `in_plan` records whether a plan targets the competency |
| FR-9.2 | De-identified by default; re-identification audited | Partly | `--anonymise` is an option, not the default; keyed HMAC, salt kept out of git |
| FR-9.3 | Snapshot timestamp and configuration in the export | Met | `manifest.json`: source, commit, cache, thresholds, schema version |

## Non-functional requirements

| ID | Requirement (abridged) | Status | Where, and what to know |
|---|---|---|---|
| NFR-1 | Scale to 30+ subjects; vector retrieval before LLM adjudication; cache embeddings | Partly | Single-call clustering fails at 52 SILOs on the local model; the embedding tagger caches embeddings and scales (1,436 SILOs in 64 s) but is not yet the pipeline's clusterer (ADR 0002 review trigger) |
| NFR-2 | Pseudonymised ids; no identifying text in prompts or logs | Partly | Prompts carry `STU0001`-style ids and marker feedback; real data would need ingest-time pseudonymisation (FR-1.5) |
| NFR-3 | Model, prompt version and thresholds persisted with every artefact; temperature 0 | Partly | Thresholds in the export manifest and on the Provenance page; model in the generation logs, not in the cache (A-29); temperature 0.2 by measured choice |
| NFR-4 | Provider abstraction with an offline stub | Met | `LLMClient` protocol, two providers; the committed reference run is the offline path for the pipeline and dashboard, and tests use fake clients |
| NFR-5 | Token spend bounded and reported | Met | Every command prints calls, tokens and time; the ten-plan audit cost $0.62 on Anthropic |
| NFR-6 | No automated claim without traceable evidence | Met | Classification basis on every row; grounding on every artefact; the quiz states the one thing it cannot verify |
| NFR-7 | Local-first, no institutional network dependency | Met | Dockerised Moodle, local models, localhost dashboard; the chart libraries come from a CDN (debt item 1) |
| NFR-8 | The feedback-cleansing constraint recorded as a limitation | Met | SMD §3.9 item 9; this page |

## Open questions from the August meeting, as of October

| # | Question | Status |
|---|---|---|
| 1 | The rule behind the at-risk band | Confirmed there is none; the dashboard defines no at-risk cohort and the thresholds remain unratified (A-01) |
| 2 | A sanitised extract of bespoke feedback | Not supplied; feedback analysis not built |
| 3 | Course maps for CS, IT and Cyber | Not supplied; `LJA_SUBJECT_SEQUENCE` is ready for them |
| 4 | Preferred or prohibited LLM provider | Open; both providers are built and the choice is configuration |
| 5 | Institutional competency framework | Open; labels are derived from the data and reviewed by staff |
| 6 | Weekly meeting slot | Settled in Sprint 3 |
