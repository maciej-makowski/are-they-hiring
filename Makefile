.PHONY: test test-e2e migrate revision lint lint-fix build build-all build-container-web build-container-scraper build-container-ollama run clean test-env-up test-env-down fetch classify reclassify dev install uninstall install-compose uninstall-compose

test:
	uv run pytest tests/integration/ -v

test-e2e:
	uv run pytest tests/e2e/ -v

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(msg)"

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

lint-fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

build-container-web:
	podman build -f Containerfile.web -t are-they-hiring-web .

build-container-scraper:
	podman build -f Containerfile.scraper -t are-they-hiring-scraper .

build-container-ollama:
	podman build -f Containerfile.ollama -t are-they-hiring-ollama .

build: build-container-web build-container-scraper

build-all: build build-container-ollama

run:
	podman play kube podman/pod.yml

clean:
	podman play kube --down podman/pod.yml 2>/dev/null || true

test-env-up:
	podman-compose -f podman-compose.test.yml up -d

test-env-down:
	podman-compose -f podman-compose.test.yml down -v

# Scraper commands (run inside scraper container or locally with DB access)
fetch:
	uv run python -m src.scrapers.scheduler fetch $(company)

classify:
	uv run python -m src.scrapers.scheduler classify $(company)

reclassify:
	uv run python -m src.scrapers.scheduler reclassify $(company)

dev:
	./scripts/dev.sh

install: build-all
	@echo "Installing systemd quadlet units..."
	mkdir -p $(HOME)/.config/containers/systemd
	cp podman/systemd/*.pod podman/systemd/*.container $(HOME)/.config/containers/systemd/
	@if [ ! -f $(HOME)/.config/are-they-hiring/.env ]; then \
		mkdir -p $(HOME)/.config/are-they-hiring; \
		cp podman/systemd/.env.example $(HOME)/.config/are-they-hiring/.env; \
		echo ""; \
		echo "*** IMPORTANT: Edit $(HOME)/.config/are-they-hiring/.env ***"; \
		echo "*** Set a real POSTGRES_PASSWORD and update DATABASE_URL  ***"; \
		echo ""; \
	fi
	systemctl --user daemon-reload
	@echo "Done. Start with: systemctl --user start are-they-hiring-pod.service"

uninstall:
	systemctl --user stop are-they-hiring-pod.service 2>/dev/null || true
	rm -f $(HOME)/.config/containers/systemd/are-they-hiring*.pod
	rm -f $(HOME)/.config/containers/systemd/are-they-hiring*.container
	systemctl --user daemon-reload
	@echo "Units removed. Data volume and .env preserved."

install-compose: build-all
	@echo "Installing compose-based systemd service..."
	mkdir -p $(HOME)/.config/are-they-hiring
	cp podman-compose.prod.yml $(HOME)/.config/are-they-hiring/compose.yml
	@if [ ! -f $(HOME)/.config/are-they-hiring/.env ]; then \
		cp podman/systemd/.env.example $(HOME)/.config/are-they-hiring/.env; \
		echo ""; \
		echo "*** IMPORTANT: Edit $(HOME)/.config/are-they-hiring/.env ***"; \
		echo "*** Set a real POSTGRES_PASSWORD and update DATABASE_URL  ***"; \
		echo ""; \
	fi
	mkdir -p $(HOME)/.config/systemd/user
	cp podman/systemd/are-they-hiring-compose.service $(HOME)/.config/systemd/user/
	systemctl --user daemon-reload
	@echo "Done. Start with: systemctl --user start are-they-hiring-compose.service"
	@echo "Enable on boot: systemctl --user enable are-they-hiring-compose.service"

uninstall-compose:
	systemctl --user stop are-they-hiring-compose.service 2>/dev/null || true
	systemctl --user disable are-they-hiring-compose.service 2>/dev/null || true
	rm -f $(HOME)/.config/systemd/user/are-they-hiring-compose.service
	systemctl --user daemon-reload
	@echo "Service removed. Data volume, compose file, and .env preserved."
