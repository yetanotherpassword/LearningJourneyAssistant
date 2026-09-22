# LJA — Development environment bundle

Local Dockerised Moodle for development. Local-first is a direct instruction
from the project owner: the tech stack stays under our control, and going
straight to Azure or AWS was described as too experimental. Migration to cloud
later is explicitly fine.

## Contents

| File | Purpose |
| --- | --- |
| `bootstrap.sh` | One-shot setup of a Moodle 5.2 instance on a fresh Ubuntu machine. |
| `env.sh` | Shared moodle-docker configuration. Source before any `bin/moodle-docker-*` command. |
| `seed.sh` | Generates synthetic courses and students via `tool_generator`. Takes a subject list, `--size`, or `--from-file`. |
| `fixtures/mark_rubric_from_json.php` | Defines rubrics and marks students from a catalogue-generated `rubric_fixture.json` (IOLG-113). |
| `fixtures/reload_catalogue_fixture.sh` | Copies that script and fixture into the webserver container and runs it. |

## Quick start

```bash
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"      # log out and back in

./bootstrap.sh                        # ~10 minutes on first run
./seed.sh
```

Moodle then answers on `http://localhost:${MOODLE_DOCKER_WEB_PORT}`, admin
password `Devpass1!`. `env.sh` defaults `MOODLE_DOCKER_WEB_PORT` to `8081`,
not `8000` — 8000 is commonly taken by something else on a dev machine (the
port-clash gotcha below exists precisely because 8000 collides often). Check
`env.sh` for your team's actual default before assuming the port. Development
credentials only — never reuse them anywhere.

## Why moodle-docker

`moodlehq/moodle-docker` is the official development environment used by Moodle
core developers. It supports PostgreSQL, MySQL, MariaDB, MSSQL and Oracle, and
ships Behat and PHPUnit wiring we get for free if we want acceptance tests
later. PostgreSQL is the recommended backend for development.

## Version target

Moodle 5.2 (released 20 April 2026) is current stable, with 5.2.1 the latest
point release. 5.1 is supported until April 2027; 5.0 goes out of support on
5 October 2026. Build against 5.2 — the branch is pinned in `bootstrap.sh`.

Note that Moodle is migrating its UI to React across 2026–27. That is another
reason not to scrape HTML: anything built on the current markup will break.

## Gotchas

**Always run `bin/moodle-docker-wait-for-db`** after bringing containers up and
before the install command. Skipping it is the most common cause of a failed
install, because the database container has not finished initialising.

**Do not hand-edit `config.php`** at setup time. The template reads settings from
container environment variables via `getenv()`.

**Port clashes.** If 8000 or 5432 are taken, override `MOODLE_DOCKER_WEB_PORT`
and `MOODLE_DOCKER_DB_PORT` in `env.sh`.

**Plugin CLI scripts live under `public/`, not `admin/cli/`.** Moodle 5.x
split the codebase: everything Apache actually serves moved into `public/`,
while `config.php` and a handful of core CLI scripts (`install_database.php`,
`cron.php`, `upgrade.php`, ...) kept a compatibility copy at the old top-level
`admin/cli/` path — that split is why `install_database.php` in
`bootstrap.sh` still works unmodified. **Plugin** CLI scripts, such as
`admin/tool/generator/cli/maketestcourse.php` used by `seed.sh`, did **not**
get that compatibility copy. Any `php admin/tool/...` invocation from inside
the webserver container needs a `public/` prefix:
`php public/admin/tool/generator/cli/maketestcourse.php`. This will matter
again the day someone writes a CLI entry point for the custom rubric-fills
plugin (see the python bundle's stretch goal) — check whether the target
script is core (top-level `admin/cli/` works) or a plugin
(`public/admin/...` required) before wiring it up.

**Machine-specific overrides** belong in a gitignored `local.yml`, not in
`env.sh`. `env.sh` is shared so all six of us run an identical stack.

## Synthetic data

No real student data is used anywhere in this project. The project owner will
supply an anonymised, modelled dataset covering three or four subjects with
scores, assessments and subject intended learning outcomes — the same shape as a
real extract, so there is no integration surprise waiting for us later.

`tool_generator` gives us enrolled users, courses and activities, but not
realistic marks or rubric fills. For those, either drive the write-side web
services or run a CLI script using `grade_update()` from `lib/gradelib.php`.
Never write to the grade tables directly.

Generating plausible criterion-level feedback text is a legitimate use of an LLM
here: a few hundred varied remarks give the parsing engine something realistic
to chew on, which is better trade show material than three hand-written samples.

## Restoring supplied course backups (.mbz)

The dataset we requested from the project owner arrives as Moodle course
backups exported without user data (see the data-fixtures README for the full
checklist). Restoring one gives us the real assessments and rubrics in place —
no re-keying.

UI path: Site administration → Courses → Restore course → upload the `.mbz` →
"Restore as a new course". Verify on the restore-settings page that user data
is excluded; the backup should already have been made with "Include enrolled
users" unticked.

After restoring:

1. Run `python/moodle_probe.py` — the restored subjects should appear in the
   course list and the token should reach their grade items.
2. Run SQL Query 1 (rubric definitions) — its output is the vocabulary the
   criterion-to-SILO mapping has to cover.
3. Seed synthetic students into the restored courses (enrolment + marks +
   rubric fills), since the backups deliberately contain none.

## Catalogue-driven fixtures (IOLG-113)

`tool_generator` makes courses, users and assignments but never grades
anything, and it has no concept of a learning outcome. The subject catalogue
(`data-fixtures/subject_catalogue.yaml`, see that bundle's README) fills both
gaps from one definition, and it is the same definition the Excel workbook is
generated from, so the Moodle rows and the Excel rows describe the same
students.

```bash
# 1. generate the workbook AND the Moodle fixtures from the catalogue
cd ../python && conda activate lja
python -m lja.data.catalogue_generator ../data-fixtures/subject_catalogue.yaml \
    --students 300 --out ../data-fixtures/CSE_results_catalogue_300_synthetic.xlsx \
    --moodle-out ../data-fixtures/moodle-generated

# 2. seed the courses the catalogue names (size S: ten assignments per course)
cd ../devenv
./seed.sh --from-file ../data-fixtures/moodle-generated/seed_subjects.txt

# 3. define the rubrics and mark the first N enrolled students per assignment
./fixtures/reload_catalogue_fixture.sh ../data-fixtures/moodle-generated/rubric_fixture.json

# 4. import the competency frameworks by hand
#    Site administration -> Competencies -> Import competency framework
#    one CSV per subject in ../data-fixtures/moodle-generated/
```

What `rubric_fixture.json` carries, per course and assignment: the rubric
criteria (an explicit `rubric:` in the catalogue, or one criterion per SILO
derived from the SILO text), the level ladder, and for each of the first N
generated students the level they reached (from their generated mark for
that assessment) and a remark. Remarks come from a template bank filled
with the criterion text; `--llm-remarks` on the generator has the LLM write
the bank in one call, otherwise built-in templates are used.

Rules, the same as the IOLG-56 fixture: nothing writes to the grade tables
directly (grading controller API + `assign::save_grade()`); re-runs only
re-grade, never redefine; a missing course or assignment, or an existing
rubric with different criteria, is reported and skipped rather than fatal.

At handbook scale (300+ subjects, see the python README) `seed.sh --from-file`
will create 300+ courses; at size S that is 100 users and ten assignments
each, and `tool_generator` takes roughly a minute per course. Trim
`seed_subjects.txt` to the subjects one program actually uses if you only
need a demo instance.

Assignment names: the catalogue maps its i-th assessment to tool_generator's
`Assignment i` unless `moodle_assignment:` overrides it. Size XS creates one
assignment per course, so seed at size S (ten) for catalogue subjects with
three or four assessments.

Verify with SQL Query 2 (devenv prefix `m_`): one row per active
(student, criterion) across every marked assignment, every row with a remark.
`moodle-generated/criterion_silo_map.csv` maps each criterion back to its
`SUBJECT:SILOn` key, which is what makes those rows comparable to the Excel
path.

## Bulk import paths worth knowing

- Users: Site administration → Users → Upload users (CSV)
- Courses: Site administration → Courses → Upload courses (CSV)
- Competency frameworks: Site administration → Competencies → Import competency
  framework (CSV) — see the data-fixtures bundle
