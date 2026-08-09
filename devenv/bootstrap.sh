#!/usr/bin/env bash
#
# bootstrap.sh — stand up a local Moodle development instance.
#
# One-shot setup for a fresh Ubuntu machine. Idempotent enough to re-run, but
# it will not re-install Moodle over an existing database.
#
# Usage:  ./bootstrap.sh
#         MOODLE_ADMIN_PASS='...' ./bootstrap.sh     # override the dev password
#
set -euo pipefail

# Resolve this script's own directory BEFORE any cd.
#
# The original bug lived here. $0 is the relative string "./bootstrap.sh" when
# the script is invoked that way, and `readlink -f` resolves relative paths
# against the *current* working directory. Once the script had cd'd into
# $MOODLE_DOCKER_WORKDIR, `readlink -f "$0"` pointed at a bootstrap.sh that does
# not exist there — and readlink -f resolves missing final components without
# complaint rather than erroring, so the failure only surfaced one line later as
# a missing env.sh.
#
# ${BASH_SOURCE[0]} rather than $0 so this still works if the script is sourced.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Loading environment"
# shellcheck source=./env.sh
source "${SCRIPT_DIR}/env.sh"

echo "==> Checking prerequisites"
for cmd in git docker; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Missing: $cmd"
        echo "Install with: sudo apt install -y docker.io docker-compose-v2 git"
        echo "Then: sudo usermod -aG docker \"\$USER\"  (log out and back in)"
        exit 1
    }
done

# Confirm the daemon is reachable, not merely that the client is installed.
# A user who has not yet re-logged in after usermod fails here with a clear
# message instead of an opaque permissions error twenty lines further down.
docker info >/dev/null 2>&1 || {
    echo "Docker is installed but the daemon is not reachable."
    echo "If you have just run usermod -aG docker, log out and back in"
    echo "(or run: newgrp docker) and try again."
    exit 1
}

echo "==> Cloning moodle-docker tooling"
if [ ! -d "$MOODLE_DOCKER_WORKDIR" ]; then
    git clone https://github.com/moodlehq/moodle-docker.git \
        "$MOODLE_DOCKER_WORKDIR"
fi
cd "$MOODLE_DOCKER_WORKDIR"

echo "==> Cloning Moodle codebase (${MOODLE_BRANCH})"
if [ ! -d "$MOODLE_DOCKER_WWWROOT" ]; then
    git clone --branch "$MOODLE_BRANCH" --depth 1 \
        https://github.com/moodle/moodle.git "$MOODLE_DOCKER_WWWROOT"
fi

echo "==> Placing config template"
# Moodle reads its settings from container environment variables via getenv().
# Do not hand-edit the resulting config.php at this stage.
cp -n "${MOODLE_DOCKER_WORKDIR}/config.docker-template.php" \
      "${MOODLE_DOCKER_WWWROOT}/config.php"

echo "==> Starting containers"
bin/moodle-docker-compose up -d

echo "==> Waiting for the database to initialise"
# Skipping this is the single most common cause of a failed install.
bin/moodle-docker-wait-for-db

echo "==> Installing Moodle"
bin/moodle-docker-compose exec webserver \
    php admin/cli/install_database.php \
        --agree-license \
        --fullname="LJA Dev" \
        --shortname="LJA" \
        --adminpass="${MOODLE_ADMIN_PASS}" \
        --adminemail="admin@example.com"

echo
echo "==> Done. Moodle is at http://localhost:${MOODLE_DOCKER_WEB_PORT}"
echo "    Login: admin / ${MOODLE_ADMIN_PASS}   (development only, never reuse)"
echo "    Next:  ./seed.sh"
