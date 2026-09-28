#!/usr/bin/env bash
#
# reload_catalogue_fixture.sh — IOLG-113
#
# Replays a catalogue-generated rubric marking plan into the running devenv
# Moodle. The plan is the rubric_fixture.json that
#     python -m lja.data.catalogue_generator ... --moodle-out <dir>
# writes; the courses it names must already exist:
#     ./bootstrap.sh
#     ./seed.sh --from-file <dir>/seed_subjects.txt
#     ./fixtures/reload_catalogue_fixture.sh <dir>/rubric_fixture.json
#
# Idempotent for the same reasons as reload_fixture.sh (IOLG-56): rubrics are
# defined once, re-runs only re-grade. Missing courses/assignments and rubrics
# with different criteria are reported and skipped, not fatal.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_JSON="${1:-${SCRIPT_DIR}/../../data-fixtures/moodle-generated/rubric_fixture.json}"

if [ ! -r "$FIXTURE_JSON" ]; then
    echo "Fixture not found: $FIXTURE_JSON" >&2
    echo "Generate it with: python -m lja.data.catalogue_generator <catalogue.yaml> --out <x.xlsx> --moodle-out <dir>" >&2
    exit 1
fi

# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"
cd "$MOODLE_DOCKER_WORKDIR"

WEBSERVER="$(bin/moodle-docker-compose ps -q webserver)"
if [ -z "$WEBSERVER" ]; then
    echo "Webserver container is not running. Start the stack first:" >&2
    echo "  source ${SCRIPT_DIR}/../env.sh && cd \"\$MOODLE_DOCKER_WORKDIR\" && bin/moodle-docker-compose up -d" >&2
    exit 1
fi

echo "==> Copying marking script and fixture into the webserver container"
docker cp "${SCRIPT_DIR}/mark_rubric_from_json.php" "${WEBSERVER}:/tmp/mark_rubric_from_json.php"
docker cp "${FIXTURE_JSON}" "${WEBSERVER}:/tmp/rubric_fixture.json"

echo "==> Running the rubric marking"
bin/moodle-docker-compose exec -T webserver php /tmp/mark_rubric_from_json.php /tmp/rubric_fixture.json

echo
echo "Verify with SQL Query 2 (devenv prefix is m_, not mdl_) — one row per active (student, criterion)."
