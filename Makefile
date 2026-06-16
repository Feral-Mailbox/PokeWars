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
#   make refresh-seed       - Upsert all catalog tables (maps, units, moves, items)
#   make refresh-seed SEED=maps,units ENV=dev
#   make bootstrap-admin     - Recreate/sync admin without touching catalog data

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
	$(DC_USED) down --remove-orphans
	$(DC_USED) up -d postgres redis
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
	# If there are *no* version files, generate the initial migration
	@test -n "$$(ls -A apps/backend/alembic/versions 2>/dev/null)" || \
		$(DC_USED) run --rm backend alembic revision --autogenerate -m "init"
	@echo "Running database migrations..."
	$(DC_USED) run --rm backend alembic upgrade head
	@echo "Seeding catalog data and bootstrap admin..."
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only maps,units,moves,items --refresh
	@echo "Starting application services..."
	$(DC_USED) up -d
	@if [ "$(ENV)" = "dev" ]; then \
		echo "Waiting for pgAdmin to be ready (this may take up to 30 seconds)..."; \
		sleep 30; \
	fi
	@echo "Setup complete! Log in with BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD from apps/backend/.env"
	@if [ "$$RUN_TESTS" = "1" ]; then \
		$(MAKE) test; \
	else \
		echo "Skipping tests (set RUN_TESTS=1 to enable)"; \
	fi

# === Lifecycle ===
up:
	$(DC_USED) up -d --build --remove-orphans

down:
	$(DC_USED) down --remove-orphans

restart:
	$(DC_USED) down --remove-orphans
	$(DC_USED) up -d --build --remove-orphans

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
	docker rm -f nginx pgadmin backend frontend 2>/dev/null || true

# === DB ===
migrate:
	$(DC_USED) run --rm backend alembic revision --autogenerate -m "$(m)"

upgrade:
	$(DC_USED) run --rm backend alembic upgrade head

reset-db: down nuke first-launch

wait-for-postgres:
	@for i in 1 2 3 4 5; do \
		if $(DC_USED) exec -T postgres pg_isready -U gameuser > /dev/null 2>&1; then \
			exit 0; \
		fi; \
		if [ $$i -lt 5 ]; then sleep 2; fi; \
	done; \
	echo "Postgres is not ready. Run 'make up' first."; \
	exit 1

# Refresh selected catalog tables in place. Does not delete users, games, or moderation data.
# Also ensures the bootstrap admin account exists (see BOOTSTRAP_ADMIN_* in apps/backend/.env).
# Examples:
#   make refresh-seed
#   make refresh-seed SEED=maps,units
#   make refresh-seed SEED=maps ENV=dev
SEED ?= maps,units,moves,items
refresh-seed: wait-for-postgres
	@echo "Refreshing catalog tables: $(SEED)"
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only "$(SEED)" --refresh

bootstrap-admin: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --bootstrap-only

reset-bootstrap-password: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/reset_bootstrap_password.py

seed-maps: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only maps --refresh

seed-units: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only units --refresh

seed-moves: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only moves --refresh

seed-items: wait-for-postgres
	$(DC_USED) run --rm -e PYTHONPATH=/app backend python scripts/seed_catalog.py --only items --refresh

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

.PHONY: first-launch up down rebuild migrate upgrade logs nuke psql status shell dev-shell reset-db wait-for-postgres refresh-seed bootstrap-admin reset-bootstrap-password seed-maps seed-units seed-moves seed-items test test-backend test-frontend