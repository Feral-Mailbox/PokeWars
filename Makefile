# File: Makefile

# Default environment
ENV ?= dev

# Docker Compose file paths
PROJECT = poketactics
COMPOSE_BASE = infrastructure/docker-compose.yml
COMPOSE_DEV = infrastructure/docker-compose.dev.yml

# Pick which docker compose invocation to use
ifeq ($(ENV),prod)
DC_USED = docker compose -p $(PROJECT) -f $(COMPOSE_BASE)
else
DC_USED = docker compose -p $(PROJECT) -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)
endif

# === Startup ===	
first-launch:
	$(DC_USED) down
	$(DC_USED) up -d
	# If there are *no* version files, generate the initial migration
	@test -n "$$(ls -A apps/backend/alembic/versions 2>/dev/null)" || \
		$(DC_USED) run --rm backend alembic revision --autogenerate -m "init"
	# Always bring DB up to latest
	$(DC_USED) run --rm backend alembic upgrade head
	# Seed data
	$(DC_USED) exec -e PYTHONPATH=/app backend python scripts/seed_official_maps.py
	$(DC_USED) exec -e PYTHONPATH=/app backend python scripts/seed_units.py
	$(DC_USED) exec -e PYTHONPATH=/app backend python scripts/seed_moves.py
	@if [ "$$RUN_TESTS" = "1" ]; then \
		$(MAKE) test; \
	else \
		echo "Skipping tests (set RUN_TESTS=1 to enable)"; \
	fi

# === Lifecycle ===
up:
	$(DC_USED) up -d

down:
	$(DC_USED) down

restart:
	$(DC_USED) down
	$(DC_USED) up -d

build:
	$(DC_USED) build

rebuild:
	DOCKER_BUILDKIT=1 $(DC_USED) build --no-cache
	$(DC_USED) up -d

logs:
	$(DC_USED) logs -f --tail=200

ps:
	$(DC_USED) ps

nuke:
	$(DC_USED) down -v --remove-orphans
	docker image prune -f
	docker volume rm infrastructure_pgdata || true

# === DB ===
migrate:
	$(DC_USED) run --rm backend alembic revision --autogenerate -m "$(m)"

upgrade:
	$(DC_USED) run --rm backend alembic upgrade head

reset-db: down nuke first-launch

psql:
	$(DC_USED) exec postgres psql -U gameuser -d game_db

# === Shell ===
shell:
	$(DC) exec backend /bin/sh

dev-shell:
	$(DC_USED) exec backend /bin/sh

# === Tests ===
test: test-backend test-frontend test-infrastructure 

test-backend:
	PYTHONPATH=apps/backend pytest tests/backend --cov=app

test-frontend:
	cd apps/frontend && npx vitest run --coverage

test-infrastructure:
	pytest tests/infrastructure

.PHONY: first-launch up down rebuild migrate upgrade logs nuke psql status shell dev-shell reset-db test test-backend test-frontend