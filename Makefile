.PHONY: test migrate revision lint

test:
	uv run pytest tests/ -v

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(msg)"

lint:
	uv run python -m py_compile src/config.py
	uv run python -m py_compile src/db/models.py
	uv run python -m py_compile src/db/session.py
	uv run python -m py_compile src/db/queries.py
