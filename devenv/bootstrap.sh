#!/usr/bin/env bash
#
# bootstrap.sh — stand up a local Moodle 5.2 development instance.
#
# One-shot setup for a fresh Ubuntu machine. Idempotent enough to re-run, but
# it will not re-install Moodle over an existing database.
#
# Usage:  ./bootstrap.sh
#
set -euo pipefail

MOODLE_BRANCH="MOODLE_502_STABLE"
WORKDIR="${HOME}/dev/moodle-docker"

echo "==> Checking prerequisites"
for cmd in git docker; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Missing: $cmd"
        echo "Install with: sudo apt install -y docker.io docker-compose-v2 git"
        echo "Then: sudo usermod -aG docker \"\$USER\"  (log out and back in)"
        exit 1
    }
done

echo "==> Cloning moodle-docker tooling"
if [ ! -d "$WORKDIR" ]; then
    git clone https://github.com/moodlehq/moodle-docker.git "$WORKDIR"
fi
cd "$WORKDIR"

echo "==> Cloning Moodle codebase (${MOODLE_BRANCH})"
if [ ! -d "./moodle" ]; then
    git clone --branch "$MOODLE_BRANCH" --depth 1 \
        https://github.com/moodle/moodle.git ./moodle
fi

echo "==> Loading environment"
# shellcheck source=/dev/null
source "$(dirname "$(readlink -f "$0")")/env.sh"

echo "==> Placing config template"
# Moodle reads its settings from container environment variables via getenv().
# Do not hand-edit the resulting config.php at this stage.
cp -n config.docker-template.php "${MOODLE_DOCKER_WWWROOT}/config.php"

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
        --adminpass="Devpass1!" \
        --adminemail="admin@example.com"

echo
echo "==> Done. Moodle is at http://localhost:${MOODLE_DOCKER_WEB_PORT}"
echo "    Login: admin / Devpass1!   (development only, never reuse)"
echo "    Next:  ./seed.sh"
