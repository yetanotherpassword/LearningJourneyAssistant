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

cd "${HOME}/dev/moodle-docker"
# shellcheck source=/dev/null
source "$(dirname "$(readlink -f "$0")")/env.sh"

# tool_generator creates a course populated with users S1..Sn plus activities
# and content. Sizes run XS through XL; S is enough for development.
# --fixeddataset makes the output reproducible across team members.
for SUBJECT in CSE1IOI CSE2CWA CSE1PES; do
    echo "==> Generating ${SUBJECT}"
    bin/moodle-docker-compose exec webserver \
        php admin/tool/generator/cli/maketestcourse.php \
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
