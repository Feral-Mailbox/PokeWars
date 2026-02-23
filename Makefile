# File: Makefile
#
# Usage:
#   make [target]           - Runs in PRODUCTION mode (default)
#   make [target] ENV=dev   - Runs in DEVELOPMENT mode with hot reload
#
# Examples:
#   make up                 - Start production containers
#   make up ENV=dev         - Start dev containers with hot reload
#   make reset-db           - Reset production database
#   make reset-db ENV=dev   - Reset dev database

# Default environment - set to prod by default, override with ENV=dev for development
ENV ?= prod

# Docker Compose file paths
PROJECT = poketactics
COMPOSE_BASE = infrastructure/docker-compose.yml
COMPOSE_DEV = infrastructure/docker-compose.dev.yml

# Pick which docker compose invocation to use
# Production: base compose only
# Development: base + dev overrides
ifeq ($(ENV),prod)
DC_USED = docker compose -p $(PROJECT) -f $(COMPOSE_BASE)
else ifeq ($(ENV),dev)
DC_USED = docker compose -p $(PROJECT) -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)
else
$(error Invalid ENV value. Use ENV=prod or ENV=dev)
endif

# === Startup ===	
first-launch:
	$(DC_USED) down
	$(DC_USED) up -d
	# Wait for postgres to be ready
	@echo "Waiting for database to be ready..."
	@sleep 5
	@for i in 1 2 3 4 5; do \
		if $(DC_USED) exec -T postgres pg_isready -U gameuser > /dev/null 2>&1; then \
			echo "Database is ready"; \
			break; \
		fi; \
		if [ $$i -lt 5 ]; then \
			echo "Database not ready, waiting... ($$i/5)"; \
			sleep 3; \
		fi; \
	done
	# Wait for pgAdmin to be ready
	@echo "Waiting for pgAdmin to be ready (this may take up to 30 seconds)..."
	@sleep 30
	# If there are *no* version files, generate the initial migration
	@test -n "$$(ls -A apps/backend/alembic/versions 2>/dev/null)" || \
		$(DC_USED) run --rm backend alembic revision --autogenerate -m "init"
	# Always bring DB up to latest
	@echo "Running database migrations..."
	$(DC_USED) run --rm backend alembic upgrade head
	# Seed data - use run --rm like migrations for fresh database connections
	@echo "Seeding official maps..."
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_official_maps.py
	@echo "Seeding units..."
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_units.py
	@echo "Seeding moves..."
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_moves.py
	@echo "Setup complete!"
	@if [ "$$RUN_TESTS" = "1" ]; then \
		$(MAKE) test; \
	else \
		echo "Skipping tests (set RUN_TESTS=1 to enable)"; \
	fi

# === Lifecycle ===
up:
	$(DC_USED) up -d --build

down:
	$(DC_USED) down

restart:
	$(DC_USED) down
	$(DC_USED) up -d --build

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
	docker volume rm $(PROJECT)_pgdata $(PROJECT)_pgadmin_data 2>/dev/null || true
	# Kill any orphaned containers/volumes from previous runs
	docker ps -a | grep $(PROJECT) | awk '{print $$1}' | xargs -r docker rm -f 2>/dev/null || true
	docker volume ls | grep $(PROJECT) | awk '{print $$2}' | xargs -r docker volume rm -f 2>/dev/null || true
	# Clean up hardcoded container names from old runs
	docker rm -f nginx pgadmin 2>/dev/null || true

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