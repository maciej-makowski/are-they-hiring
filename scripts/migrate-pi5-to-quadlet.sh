#!/usr/bin/env bash
# One-shot migration from podman-compose deployment to native quadlets.
# Run on a host that currently has the are-they-hiring-compose.service unit
# active. Idempotent: re-running on an already-migrated box is a no-op.
#
# What it does:
#   1. Stop + disable the running are-they-hiring-compose.service
#   2. Copy the compose-named DB volume (are-they-hiring_arethey-db-data) into
#      the quadlet-named volume (are-they-hiring-db-data) the new pod expects
#   3. Remove the now-stale compose unit + compose file
#   4. Apply the pi5 profile (lays down quadlets, daemon-reload, restart pod)
#   5. Sanity-check: list containers, hit web on localhost
#
# Volume rename rationale:
#   podman-compose names volumes <project>_<volume>, so the live DB lives in
#   are-they-hiring_arethey-db-data. The quadlet db.container declares
#   Volume=are-they-hiring-db-data:/var/lib/postgresql/data — a different
#   name. Without the copy step the new pod would start against an empty
#   volume and the schema would auto-create from scratch (data loss).

set -euo pipefail

# Anchor cwd at the repo root so `make deploy` finds the right Makefile
# regardless of where the user invoked the script from.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

HOST="${1:-}"
if [[ -z "$HOST" ]]; then
  echo "Usage: $0 user@host" >&2
  exit 2
fi

OLD_VOLUME="are-they-hiring_arethey-db-data"
NEW_VOLUME="are-they-hiring-db-data"

echo "### stopping + disabling the existing compose service ###"
ssh "$HOST" '
  set -e
  if systemctl --user is-enabled are-they-hiring-compose.service >/dev/null 2>&1; then
    systemctl --user disable --now are-they-hiring-compose.service
  elif systemctl --user is-active are-they-hiring-compose.service >/dev/null 2>&1; then
    systemctl --user stop are-they-hiring-compose.service
  fi
'

echo "### copying DB volume '"$OLD_VOLUME"' -> '"$NEW_VOLUME"' ###"
ssh "$HOST" '
  set -e
  if ! podman volume exists '"$OLD_VOLUME"' 2>/dev/null; then
    echo "  source volume '"$OLD_VOLUME"' not found — assuming already migrated, skipping copy"
    exit 0
  fi
  if podman volume exists '"$NEW_VOLUME"' 2>/dev/null && [ -n "$(podman volume inspect '"$NEW_VOLUME"' --format "{{.Mountpoint}}" | xargs -I{} ls -A {})" ]; then
    echo "  destination volume '"$NEW_VOLUME"' already populated — skipping copy"
    exit 0
  fi
  podman volume create '"$NEW_VOLUME"' >/dev/null 2>&1 || true
  podman run --rm \
    -v '"$OLD_VOLUME"':/from:ro \
    -v '"$NEW_VOLUME"':/to \
    docker.io/alpine:3.20 \
    sh -c "cp -a /from/. /to/ && chown -R 999:999 /to"
  echo "  volume copy complete"
'

echo "### removing stale compose unit + compose file ###"
ssh "$HOST" '
  set -e
  rm -f ~/.config/systemd/user/are-they-hiring-compose.service
  rm -f ~/.config/are-they-hiring/compose.yml
  systemctl --user daemon-reload
'

echo "### deploying quadlet profile ###"
make deploy PROFILE=pi5 HOST="$HOST"

echo "### migration complete; verifying ###"
ssh "$HOST" '
  podman ps --format "table {{.Names}} {{.Status}}"
  curl -sS -o /dev/null -w "web local: %{http_code}\n" http://localhost:8000/ || true
'
