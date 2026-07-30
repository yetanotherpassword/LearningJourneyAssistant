#!/usr/bin/env bash
# Shared moodle-docker configuration for the LJA team.
#
# Source this before running any bin/moodle-docker-* command:
#     source env.sh
#
# Keep this file in version control so all six of us run the same stack.
# Machine-specific overrides go in a gitignored local.yml, not here.

export MOODLE_DOCKER_WWWROOT=./moodle   # path to the Moodle codebase
export MOODLE_DOCKER_DB=pgsql           # pgsql recommended for development
export MOODLE_DOCKER_WEB_PORT=8000      # http://localhost:8000

# Uncomment if port 8000 or 5432 clashes with something already running:
# export MOODLE_DOCKER_DB_PORT=15432
