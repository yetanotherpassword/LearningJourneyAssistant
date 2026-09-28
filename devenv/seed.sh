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

# tool_generator creates a course populated with users S1..Sn plus activities
# and content. Sizes run XS through XL; S is enough for development and is
# the smallest size that creates more than one assignment.
# --fixeddataset makes the output reproducible across team members.
#
# Path note: Moodle 5.x moved the web-served codebase into public/, splitting
# it from config.php and friends which stay at the repo root for security.
# A handful of core CLI scripts (install_database.php, cron.php, ...) kept a
# compatibility copy at the old top-level admin/cli/ path -- that is why
# bootstrap.sh's install step still works unmodified. Plugin CLI scripts like
# tool_generator's did NOT get that compatibility copy; they only exist under
# public/. Any future admin/tool/* CLI invocation needs the public/ prefix too.
# Which subjects, and how big. Defaults reproduce the original three at size S.
#   ./seed.sh                                    # CSE1IOI CSE2CWA CSE1PES, size S
#   ./seed.sh --size XS CSE2DBF CSE2SEP          # explicit list
#   ./seed.sh --from-file ../data-fixtures/moodle-generated/seed_subjects.txt
# The --from-file form is what the catalogue generator (IOLG-113) writes, so
# the seeded courses match the catalogue's subject codes. Size matters for the
# rubric fixture: XS makes ONE assignment per course, S makes ten, and a
# catalogue subject with four assessments needs "Assignment 1".."Assignment 4"
# to exist.
SIZE="S"
SUBJECTS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --size) SIZE="$2"; shift 2 ;;
        --from-file)
            while IFS= read -r line; do
                line="${line%%#*}"; line="${line//[[:space:]]/}"
                [ -n "$line" ] && SUBJECTS+=("$line")
            done < "$2"
            shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) SUBJECTS+=("$1"); shift ;;
    esac
done
if [ ${#SUBJECTS[@]} -eq 0 ]; then
    SUBJECTS=(CSE1IOI CSE2CWA CSE1PES)
fi

# The working directory comes from env.sh rather than being hardcoded here, so
# bootstrap.sh and seed.sh cannot drift apart. Deliberately AFTER argument
# parsing: a relative --from-file path must resolve against where you ran
# the script, not against the moodle-docker checkout.
cd "$MOODLE_DOCKER_WORKDIR"

for SUBJECT in "${SUBJECTS[@]}"; do
    echo "==> Generating ${SUBJECT} (size ${SIZE})"
    bin/moodle-docker-compose exec webserver \
        php public/admin/tool/generator/cli/maketestcourse.php \
            --shortname="${SUBJECT}" \
            --size="${SIZE}" \
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
