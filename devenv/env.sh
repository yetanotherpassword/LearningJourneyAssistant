#!/usr/bin/env bash
# Shared moodle-docker configuration for the LJA team.
#
# Sourced by bootstrap.sh and seed.sh. To run bin/moodle-docker-* commands by
# hand, source it yourself first:
#
#     source ~/CSE5IDP/LJA/LearningJourneyAssistant/devenv/env.sh
#     cd "$MOODLE_DOCKER_WORKDIR"
#     bin/moodle-docker-compose ps
#
# Keep this file in version control so all six of us run the same stack.
# Machine-specific overrides go in a gitignored local.yml, not here.

# Where the moodle-docker tooling and the Moodle codebase live. Single source
# of truth: bootstrap.sh and seed.sh both read it from here rather than each
# hardcoding their own copy of the path.
export MOODLE_DOCKER_WORKDIR="${MOODLE_DOCKER_WORKDIR:-${HOME}/dev/moodle-docker}"

# Absolute, not relative. Docker resolves bind-mount sources relative to the
# compose file rather than your shell, so a relative "./moodle" silently mounts
# the wrong thing depending on where you happen to be standing.
export MOODLE_DOCKER_WWWROOT="${MOODLE_DOCKER_WORKDIR}/moodle"

export MOODLE_DOCKER_DB=pgsql

# 8000 is taken on this machine by WebODM. Overridable so the rest of the team
# is not forced onto a port they do not need.
export MOODLE_DOCKER_WEB_PORT="${MOODLE_DOCKER_WEB_PORT:-8081}"

# Uncomment if port 5432 clashes with a Postgres already running on the host:
# export MOODLE_DOCKER_DB_PORT=15432

# Moodle branch to build against. Verify a branch exists before pinning it:
#     git ls-remote --heads https://github.com/moodle/moodle.git 'MOODLE_5*_STABLE'
export MOODLE_BRANCH="${MOODLE_BRANCH:-MOODLE_502_STABLE}"

# Development admin password. Overridable from the environment so no literal
# credential has to live in version control:
#     MOODLE_ADMIN_PASS='...' ./bootstrap.sh
export MOODLE_ADMIN_PASS="${MOODLE_ADMIN_PASS:-Devpass1!}"
