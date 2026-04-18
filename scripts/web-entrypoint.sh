#!/bin/bash
set -e

echo "Running database migrations..."
.venv/bin/alembic upgrade head

echo "Starting web server..."
exec .venv/bin/uvicorn src.web.app:create_app --factory --host 0.0.0.0 --port 8000
