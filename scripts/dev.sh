#!/bin/bash
set -e

PODMAN="podman --remote"
COMPOSE="podman-compose --podman-path ./scripts/podman-remote.sh -f podman-compose.dev.yml"

echo "Starting dev environment..."
$COMPOSE up -d

echo ""
echo "Services running:"
$COMPOSE ps
echo ""
echo "Web UI: http://localhost:8000"
echo "Press Ctrl+C to stop all services"
echo ""

LOG_PIDS=()

cleanup() {
    echo ""
    echo "Stopping log streams..."
    for pid in "${LOG_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "Stopping dev environment..."
    $COMPOSE down
}
trap cleanup EXIT

# Follow logs from each container in background, prefixed with container name
for container in $($PODMAN ps --filter "name=are-they-hiring_" --format "{{.Names}}"); do
    $PODMAN logs -f "$container" 2>&1 | sed "s/^/[$container] /" &
    LOG_PIDS+=($!)
done

# Wait for Ctrl+C
wait
