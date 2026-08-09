#!/usr/bin/env bash
#
# seed.sh — generate synthetic courses and students for development.
#
# No real student data is used anywhere in this project. The project owner will
# supply an anonymised, modelled dataset for three or four subjects; this script
# produces additional data so we can build and test edge cases before and
# alongside that.
#
set -euo pipefail

# Same fix as bootstrap.sh: resolve the script's own directory before any cd,
# because readlink -f on a relative $0 follows the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./env.sh
source "${SCRIPT_DIR}/env.sh"

# The working directory now comes from env.sh rather than being hardcoded here,
# so bootstrap.sh and seed.sh cannot drift apart.
cd "$MOODLE_DOCKER_WORKDIR"

# tool_generator creates a course populated with users S1..Sn plus activities
# and content. Sizes run XS through XL; S is enough for development.
# --fixeddataset makes the output reproducible across team members.
#
# Path note: Moodle 5.x moved the web-served codebase into public/, splitting
# it from config.php and friends which stay at the repo root for security.
# A handful of core CLI scripts (install_database.php, cron.php, ...) kept a
# compatibility copy at the old top-level admin/cli/ path -- that is why
# bootstrap.sh's install step still works unmodified. Plugin CLI scripts like
# tool_generator's did NOT get that compatibility copy; they only exist under
# public/. Any future admin/tool/* CLI invocation needs the public/ prefix too.
for SUBJECT in CSE1IOI CSE2CWA CSE1PES; do
    echo "==> Generating ${SUBJECT}"
    bin/moodle-docker-compose exec webserver \
        php public/admin/tool/generator/cli/maketestcourse.php \
            --shortname="${SUBJECT}" \
            --size=S \
            --fixeddataset
done

echo
echo "Generated courses with enrolled users and activities."
echo
echo "Still to do by hand or by script:"
echo "  - Attach rubrics to the assignments (Assignment -> Advanced grading)"
echo "  - Populate marks and per-criterion rubric fills"
echo "  - Import the competency framework (see the data-fixtures bundle)"
echo
echo "tool_generator does not produce realistic marks or rubric fills. Drive"
echo "those through the write-side web services (mod_assign_save_grade,"
echo "core_competency_grade_competency) or a CLI script using grade_update()"
echo "from lib/gradelib.php. Never write to the grade tables directly."
