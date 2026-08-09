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
| `seed.sh` | Generates synthetic courses and students via `tool_generator`. |

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

## Bulk import paths worth knowing

- Users: Site administration → Users → Upload users (CSV)
- Courses: Site administration → Courses → Upload courses (CSV)
- Competency frameworks: Site administration → Competencies → Import competency
  framework (CSV) — see the data-fixtures bundle
