#!/usr/bin/env bash
#
# reload_fixture.sh — IOLG-56
#
# Replays the rubric-fills fixture into the running devenv Moodle: a rubric on
# CSE1IOI's "Assignment 1", marked for five students with per-criterion remarks.
# This is the reproducible reload the ticket's step 4 asks for — a replay script
# rather than a committed pg_dump, so the fixture stays readable and diffable in
# version control instead of a multi-hundred-MB binary dump of the whole DB.
#
# Order, from a fresh machine:
#     ./bootstrap.sh          # install Moodle 5.2  (devenv/)
#     ./seed.sh               # generate CSE1IOI etc. with enrolled students
#     ./fixtures/reload_fixture.sh
#
# Idempotent: the rubric is defined once and re-runs only re-grade. Safe to run
# again after seed.sh without duplicating the rubric.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# env.sh lives one level up, in devenv/.
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"

cd "$MOODLE_DOCKER_WORKDIR"

# Resolve the webserver container id from compose rather than hardcoding a name.
WEBSERVER="$(bin/moodle-docker-compose ps -q webserver)"
if [ -z "$WEBSERVER" ]; then
    echo "Webserver container is not running. Start the stack first:" >&2
    echo "  source ${SCRIPT_DIR}/../env.sh && cd \"\$MOODLE_DOCKER_WORKDIR\" && bin/moodle-docker-compose up -d" >&2
    exit 1
fi

echo "==> Copying marking script into the webserver container"
docker cp "${SCRIPT_DIR}/mark_rubric_fixture.php" "${WEBSERVER}:/tmp/mark_rubric_fixture.php"

echo "==> Running the rubric marking"
bin/moodle-docker-compose exec -T webserver php /tmp/mark_rubric_fixture.php

echo
echo "Fixture loaded. Verify with SQL Query 2 (remember the devenv prefix is m_, not mdl_):"
echo "  sql/moodle_attainment_extraction.sql — Query 2 should return 5 students x 3 criteria with remarks."
