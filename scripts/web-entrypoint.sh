#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting web server..."
exec uv run uvicorn src.web.app:create_app --factory --host 0.0.0.0 --port 8000
