# Large test cohort: 100 real La Trobe subjects, 5000 synthetic students

This page explains how the project's large test dataset was built, why it was built that way, and how
to rebuild or change it. The dataset has **100 real La Trobe subjects** with their published learning
outcomes (SILOs) and **5000 synthetic students** enrolled across **eight degree programs**. It exists
because the workbook Scott supplied (150 students, 3 subjects) is too small to show the product
working the way it will in production, where value appears "across 30-plus subjects".

The generated files are **not in git** (see [Where the files are](#where-the-files-are)). Anyone can
rebuild them in about ten minutes from the commands below.

---

## At a glance

| | |
| --- | --- |
| Subjects | 100, taken from the La Trobe 2026 handbook |
| SILOs | 448, verbatim from the handbook (3 to 7 per subject) |
| Competencies | 40, found by grouping SILOs by meaning (38 span two or more subjects) |
| Assessments | 349, synthetic (the handbook does not publish them in a crawlable form) |
| Programs | 8, hand-written enrolment rules |
| Students | 5000, synthetic |
| Result rows | 310,861 (12 to 21 subjects per student, mean 17.8) |
| Time to rebuild | about 8 minutes tagging (local LLM), 23 s generating, 19 s gap analysis |

Subjects by discipline (the subject-code prefix) and year level:

| AGR | BCH | BIO | CHE | CSE | ELE | ENG | ENV | GEN | MAT | MIC | PHY | SCI | STA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 3 | 5 | 8 | 30 | 3 | 7 | 2 | 2 | 10 | 5 | 7 | 7 | 4 |

34 first-year, 48 second-year and 18 third-year subjects.

---

## Why real subjects from the La Trobe handbook

**Made-up SILOs would test the wrong thing.** The product's job is to read a university's own
learning outcomes, group them into competencies, and find students who are weak in a competency
across several subjects. If an LLM invents the SILOs, they come out tidy, uniformly worded and
suspiciously well aligned, so the clustering and the SILO-quality checks look better than they will on
real data. Real SILOs are uneven: some are precise, some are vague ("understand", "appreciate"), some
subjects overlap heavily and some share nothing. That unevenness is what we need to test against.
On the full 314-subject crawl, 366 of 1,436 real SILOs use a verb that cannot be observed in a
student's work, which is exactly the kind of finding the outcome-quality page exists to surface.

**La Trobe is the client.** Scott's workbook SILOs turned out to be shortened versions of the
published handbook SILOs (compare CSE1OOF SILO1 in both), so the handbook is the real source for the
data the product will eventually see.

**The handbook is public and allows crawling.** `handbook.latrobe.edu.au` needs no login. Its
`robots.txt` allows everything, and its sitemap lists every subject page for the year (about 2,260
for 2026). Each subject page embeds the subject as structured JSON, including an ordered list of
learning outcomes with their codes. So the crawler reads data, not scraped HTML layout, and no LLM is
involved in getting the SILOs.

**Why not use our student logins, or the University of Queensland handbook.** Student accounts give
access to LMS content under terms of use that do not cover bulk collection, and the handbook already
has everything public. UQ was considered and rejected. Its subjects are another university's
copyright, its outcomes are published per offering rather than per subject, and its codes do not
match La Trobe's scheme.

**How the crawl behaves.** One request per second, a User-Agent that names the project, and a disk
cache so a page is never fetched twice. The first crawl of 314 subjects took about five minutes.
Every rebuild since then has read the cache and made no network requests.

**What the handbook does not give us.** The assessment map (weights, hurdles, which assessment covers
which SILO) is loaded per teaching period by JavaScript in the browser, from an endpoint that is not
in the page data. So assessments are **synthetic**. Each subject gets a realistic pattern for its
discipline (for example, lab reports plus mid-semester test plus exam for a lab science, or two
assignments plus exam for computing). The pattern is seeded by subject code, so the same subject
always gets the same assessments, and every SILO is covered by at least one assessment. Every
subject is marked `assessments_synthetic: true` in the catalogue. If Scott can export real assessment
maps, they can replace these without changing anything else.

**Licensing.** The handbook content is La Trobe's. It is kept out of the repository (the whole
`data-fixtures/handbook/` folder is gitignored) until the project owner says it may be committed.
The code that fetches it is in the repository. Anyone can regenerate the data.

---

## How the pipeline works

```text
La Trobe handbook ──crawl──▶ catalogue_100_raw.yaml ──tag──▶ catalogue_100_tagged.yaml ──add programs──▶ catalogue_100.yaml
   (public pages)              100 subjects, 448 SILOs         + 40 competencies               + 8 programs
                               synthetic assessments           + trait loadings
                                                                                                    │
                                                                                                generate
                                                                                                    ▼
                                    gap report, dashboard  ◀──analyse──  CSE_results_catalogue_100subj_5000.xlsx
                                    scored against truth                 + truth.json + clustering.json
```

### Step 1. Crawl (handbook.py)

Reads the subject codes to fetch, loads each page from the cache or the handbook, extracts code,
title, year level, credit points, school and SILOs, and adds synthetic assessments. SILO text is
lightly normalised so the rest of the pipeline can read it: tags removed, semicolons turned into
commas (the workbook loader splits on `;`), the trailing full stop dropped and the first letter
lower-cased.

### Step 2. Group SILOs into competencies (competency_tagger.py)

The product's own LLM clustering asks a chat model to partition every SILO in one call. That fails
its coverage check at 52 SILOs on the local 30B model, so it cannot handle 448. Grouping sentences by
meaning is what embeddings are for, so the tagger:

1. Embeds every SILO with `nomic-embed-text` (through Ollama).
2. Groups them with spherical k-means (k-means on cosine similarity, 4 restarts), here into k = 40
   clusters.
3. Asks the chat model only to **name** each cluster, 20 clusters per call. With no LLM available it
   falls back to keyword labels.
4. Runs a principal component analysis (PCA) of the cluster centres to give each competency a
   `traits` loading on 5 latent "aptitude" axes. Competencies that mean similar things get similar
   loadings, which is what lets the generator make related abilities move together (see below).

These competencies are the dataset's **ground truth by construction**: the generator makes students
consistent with them. They need to be coherent and reviewable, not the one true competency map of
La Trobe.

### Step 3. Programs

`catalogue_100.yaml` is the tagged catalogue plus a `programs:` block. Each program has an intake
share and ordered rules of the form "take N subjects matching these code patterns". A **core** rule
takes the first N matches, and an **elective** rule samples N at random. `take: -1` means all
matches.

| Program | Intake share | Students | Shape |
| --- | --- | --- | --- |
| BCS Computer Science | 3.0 | 1,354 | CSE core each year, maths/stats electives |
| BSC-BIO Biological Sciences | 2.0 | 867 | BIO, then GEN/MIC/BCH core, env/agri electives |
| BSC-CHE Chemistry and Biochemistry | 1.5 | 670 | CHE then CHE/BCH core, BCH/SCI/MIC year 3 |
| BSC-MATH Mathematics and Statistics | 1.0 | 521 | MAT/STA core, physics/computing electives |
| BENG-ELE Engineering (Electronic) | 1.0 | 447 | ELE/MAT/PHY core, computing electives |
| BSC-PHY Physics | 1.0 | 445 | PHY/MAT core, SCI/ELE electives |
| BAGSCI Agricultural Science | 1.0 | 434 | AGR core, BIO/CHE/ENV electives |
| BA-ENG English with a science minor | 0.5 | 262 | ENG core, SCI/ENV electives |

Note that **ENG at La Trobe is English literature, not engineering**, hence the BA program.
Because only 18 third-year subjects are in the 100, year-3 rules draw from whatever the subset has.

### Step 4. Generate students (catalogue_generator.py)

Described in full in the next section. Output is a workbook in exactly the shape of Scott's
(`Results`, `Student Summary`, `Assessment Map` sheets, plus a `Program` column), so everything
downstream loads it unchanged. Beside it the generator writes:

- `truth.json`: every student's program, hidden abilities, and planted gap, if any.
- `clustering.json`: the catalogue's competencies in the same format as the LLM clustering cache, so
  the gap pipeline uses the ground-truth grouping instead of calling the LLM.
- `clustering.review.json`: a review file with every cluster auto-confirmed, so the pipeline's staff
  review gate lets it through. On this dataset "confirmed" means generated, not reviewed by staff.

### Step 5. Analyse and score

`lja.cli` runs gap detection exactly as on real data. `catalogue_verify` then compares the gap report
with `truth.json`: did we find the gaps we planted, and how many students were flagged who had no
planted gap.

---

## How student marks are generated (the Gaussian part)

Yes, the marks are Gaussian, built up from four layers. Every random draw below is from a normal
(Gaussian) distribution except the planted-gap depth, which is uniform.

**1. Overall ability (baseline).** Each student gets one number for how strong they are overall:

```text
baseline ~ Normal(mean 68, sd 11), clipped to 20..99
```

68 and 11 match the mean and spread of the supplied workbook.

**2. Aptitudes (latent traits).** Each student gets 5 trait scores. A program shifts the centre of
its students' traits towards what its core subjects reward, by 0.6 standard deviations
(`--program-selection`). Engineering students lean quantitative, biology students lean laboratory,
and so on:

```text
trait_k ~ Normal(program_mean_k, 1)
```

**3. Ability per competency.** This is the term Scott's workbook lacks (see
`docs/adr/0001-relative-gap-detection.md`: without it every student's profile is flat and there is
nothing for relative gap detection to find). 70% of the variation comes from the student's traits
through the competency's loadings (`--latent-share 0.7`), and 30% is independent:

```text
ability_c = 7 × ( √0.7 × (loadings_c · traits) + √0.3 × Normal(0, 1) )
```

So a student strong in one quantitative competency tends to be strong in the others, but not
perfectly. The 7 is `--competency-sd`: roughly how many marks a student's competencies differ by.

**4. Marks.** Each assessment covers one or more SILOs, each SILO belongs to a competency, and the mark is:

```text
score = round( clip( baseline + mean(ability over the assessment's competencies) + Normal(0, 4), 1, 100 ) )
```

The final Normal(0, 4) is marking noise, a bad day or a generous marker (`--noise-sd`).

**Planted gaps (the answer key).** 8% of students (`--planted-gap-fraction`) are given one
deliberately weak competency. The chosen competency must be assessed at least twice across that
student's own subjects, otherwise it could not show up as a *persistent* gap. Its ability is set to
`min(ability, 0) − Uniform(18, 30)`, so the student is clearly below their own median there however
strong they are overall. 371 students carry one in this run.

**Why this gives a bell curve.** Each mark is a sum of several independent normal effects, and sums
of normals are normal. The only departures are the clip at 100, which caps 1% of marks, and the
planted gaps, which add a thin lower tail.

| Measured on the 5000-student run | Value |
| --- | --- |
| Assessment marks: mean, standard deviation | 69.1, 13.2 |
| Skew (0 = symmetric) | −0.12 |
| 5th / 25th / 50th / 75th / 95th percentile | 47 / 60 / 69 / 78 / 91 |
| Marks capped at 100 | 3,182 of 310,861 |
| Student average mark: mean, standard deviation | 69.2, 11.3 |

Distribution of assessment marks, in bands of 10:

| 0s | 10s | 20s | 30s | 40s | 50s | 60s | 70s | 80s | 90s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 25 | 69 | 534 | 3,713 | 17,454 | 49,986 | 85,325 | 85,820 | 48,945 | 18,990 |

Performance bands in the Student Summary sheet: 875 HD/D, 1,527 D, 1,538 C, 828 P, 232 at risk.

---

## Results of the run

Gap detection against the ground truth, at three settings of the relative gap cutoff (how far below
the student's own median, in median absolute deviations, a competency must fall to count as a gap):

| Cutoff | Planted gaps found as persistent (of 371) | Students with no planted gap flagged anyway (of 4,629) | of whom the flag is in their genuinely weakest third |
| --- | --- | --- | --- |
| −1.0 (default) | 336 (91%) | 3,844 | 3,493 |
| −1.5 | 330 (89%) | 3,148 | 2,863 |
| −2.0 | 303 (82%) | 2,426 | 2,228 |

**What this means.** The detector is accurate about *which* competency is a student's weakest: about
nine in ten unplanted flags are in the student's true bottom third. But at the default cutoff it
flags most students, because once competencies genuinely vary, everyone has a weakest one. Tightening
the cutoff trades a little recall on real gaps for many fewer flagged students. Choosing the cutoff is
a team decision (action A-01). This table is the evidence for it. It is not a generator bug.

Two other expected results on this data:

- **Year-on-year trends are flat.** The generator has no drift between year levels, so the
  competency progression pages correctly report "stable".
- **No SILOs are flagged by the clustering.** Flags come only from an LLM clustering run. This dataset
  uses the ground-truth grouping instead, because the LLM clustering cannot handle 448 SILOs in one call.

---

## How to run it

### What you need

- The code: branch `feature/silo-quality-views` on GitHub has everything (`handbook.py`,
  `competency_tagger.py`, the generator and the dashboard pages). PR #24 (IOLG-113) carries the
  generator only. The crawler and tagger follow in a second PR once #24 is merged.
- Python environment: the project's conda environment (`conda activate lja`), or
  `pip install -r python/requirements.txt`.
- For step 2 only: [Ollama](https://ollama.com) running locally with the embedding model and a chat
  model. `python/.env` must point at it (see `python/.env.example`):

  ```bash
  ollama pull nomic-embed-text
  ollama pull qwen3-vl:30b        # or any chat model; LJA_OPENAI_MODEL in python/.env
  ```

  Without a chat model, add `--no-llm-labels` to step 2 and competencies get keyword names.

### Commands

Run from the `python/` directory.

```bash
cd python
H=../data-fixtures/handbook

# 1. Choose the 100 subjects: every cached year-1 and year-2 subject plus 18 year-3 ones.
#    (Needs the page cache from an earlier crawl. On a fresh clone, first crawl the prefixes:
#     python -m lja.data.handbook --year 2026 --prefix CSE PHY CHE MAT STA BIO BCH MIC GEN ENG ELE CIV EEE ENV AGR SCI \
#         --out $H/catalogue_raw.yaml       # ~5 minutes, one request per second)
ls $H/cache/2026 | sed 's/\.html$//' > /tmp/all.txt
grep -E '^[A-Z]{3}[12]' /tmp/all.txt > /tmp/y12.txt
grep -E '^[A-Z]{3}3' /tmp/all.txt | grep -Ev '^(AGR|CIV|ENV|EEE)' | shuf -n 18 --random-source=<(yes) > /tmp/y3.txt
sort /tmp/y12.txt /tmp/y3.txt > $H/codes_100.txt

# 2. Build the catalogue from those codes. --prefix is required AND still filters the codes file,
#    so pass every prefix that appears in it.
python -m lja.data.handbook --year 2026 --prefix $(cut -c1-3 $H/codes_100.txt | sort -u) \
    --codes-file $H/codes_100.txt --out $H/catalogue_100_raw.yaml

# 3. Group SILOs into competencies (about 8 minutes with qwen3-vl:30b, seconds with --no-llm-labels).
python -m lja.data.competency_tagger $H/catalogue_100_raw.yaml \
    --out $H/catalogue_100_tagged.yaml --k 40 --traits 5

# 4. Add programs: copy the tagged file and append the programs: block
#    (the one used is at the end of $H/catalogue_100.yaml; copy it from there or from this page's table).
cp $H/catalogue_100_tagged.yaml $H/catalogue_100.yaml   # then append programs:

# 5. Generate 5000 students.
D=$H/CSE_results_catalogue_100subj_5000
python -m lja.data.catalogue_generator $H/catalogue_100.yaml \
    --students 5000 --no-llm-feedback --seed 11 --out $D.xlsx

# 6. Run gap detection and score it against the answer key.
python -m lja.cli $D.xlsx --clustering-cache $D.clustering.json \
    --review-file $D.clustering.review.json --gaps-out $D.gaps.csv --clusters-out $D.clusters.csv
python -m lja.data.catalogue_verify $D.truth.json --gaps $D.gaps.csv

# 7. Look at it.
python -m lja.dashboard --excel-path $D.xlsx --clustering-cache $D.clustering.json --port 8765
#    then open http://localhost:8765/  (students), /silos (outcome quality), /clusters (if IOLG-131 is merged)
```

To try another cutoff, add `--relative-gap-cutoff=-1.5` to step 6 (the `=` matters because the value
is negative), then re-run the verify command.

If the dashboard exits with a segmentation fault on start-up while Ollama is busy, it is memory
pressure. Start it again, or stop Ollama first.

### Changing the dataset

| To change | Do this |
| --- | --- |
| Number of students | `--students` in step 5. Generation is linear, about 5 s per 1000 students. |
| Same students again | Keep `--seed`. A different seed gives a different cohort from the same catalogue. |
| How spread out marks are | `--baseline-mean`, `--baseline-sd` (overall), `--competency-sd` (within a student), `--noise-sd` (per assessment) |
| Flat profiles like Scott's data | `--competency-sd 0` |
| How much related abilities move together | `--latent-share` (0 = independent, 1 = fully driven by traits) |
| How different programs' students are | `--program-selection` (0 = no difference) |
| How many planted gaps, and how deep | `--planted-gap-fraction`, `--planted-gap-depth 18,30` |
| Which or how many subjects | Edit `codes_100.txt` and re-run from step 2. Every program rule must still match at least one subject, or the generator stops with an error naming the rule. |
| Number of competencies | `--k` in step 3. Re-run with a different k if a cluster is obviously two things. |
| Realistic feedback text | Drop `--no-llm-feedback` (one LLM call for about 24 comment templates) |
| Moodle import files | Add `--moodle-out $H/moodle-generated` in step 5 |

---

## Where the files are

Everything generated is in `data-fixtures/handbook/`, which is gitignored.

| File | What it is |
| --- | --- |
| `cache/2026/*.html` | The 314 handbook pages as fetched. Re-runs read from here. |
| `codes_100.txt` | The 100 subject codes used |
| `catalogue_100_raw.yaml` | Subjects, real SILOs, synthetic assessments. Easiest file to browse. |
| `catalogue_100_tagged.yaml` | The same plus the 40 competencies and trait loadings |
| `catalogue_100.yaml` | The same plus the 8 programs. The generator reads this one. |
| `CSE_results_catalogue_100subj_5000.xlsx` | The 5000-student workbook (35 MB) |
| `…_5000.clusters.csv` | One row per SILO with subject, text and competency. Opens in Excel. |
| `…_5000.gaps.csv` | The gap report |
| `…_5000.truth.json` | Answer key: programs, hidden abilities, planted gaps |
| `…_5000.clustering.json`, `…clustering.review.json` | Ground-truth competency grouping and its auto-confirmed review file |
| `catalogue_raw.yaml`, `catalogue_tagged.yaml`, `catalogue.yaml` | The earlier full 314-subject version (1,436 SILOs, 48 competencies) |

## Known limits

- **Assessments are synthetic.** Real SILO text, invented assessment structure.
- **Competencies are ours.** The 40 groupings come from embeddings and an LLM naming step, not from
  La Trobe. The tagger also produced a few near-duplicates, marked with an `-x` suffix (for example two
  "scientific communication" competencies). They are left as they are because they are harmless to
  the tests, but a staff review would merge them.
- **No year-to-year change.** A student's ability does not grow or drift between years.
- **Year 3 is thin.** 18 subjects, so later-year electives have small pools.
- **Not real students.** Nothing here is or derives from any real student's results.
