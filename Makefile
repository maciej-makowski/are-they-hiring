.PHONY: test test-e2e migrate revision lint build run clean test-env-up test-env-down

test:
	uv run pytest tests/integration/ -v

test-e2e:
	uv run pytest tests/e2e/ -v

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(msg)"

lint:
	uv run python -m py_compile src/config.py
	uv run python -m py_compile src/db/models.py
	uv run python -m py_compile src/web/app.py

build:
	podman build -f Containerfile.web -t are-they-hiring-web .
	podman build -f Containerfile.scraper -t are-they-hiring-scraper .

run:
	podman play kube podman/pod.yml

clean:
	podman play kube --down podman/pod.yml 2>/dev/null || true

test-env-up:
	podman-compose -f podman-compose.test.yml up -d

test-env-down:
	podman-compose -f podman-compose.test.yml down -v
