# File: Makefile

# Default environment
ENV ?= dev

# Docker Compose file paths
INFRA_DIR = infrastructure
COMPOSE_BASE = $(INFRA_DIR)/docker-compose.yml
COMPOSE_DEV = $(INFRA_DIR)/docker-compose.dev.yml

# === Startup ===
first-launch:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) down -v --remove-orphans
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d --build
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) run --rm backend alembic revision --autogenerate -m "init"
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) run --rm backend alembic upgrade head
	docker exec -e PYTHONPATH=/app -it backend python scripts/seed_official_maps.py
	docker exec -e PYTHONPATH=/app -it backend python scripts/seed_units.py
	docker exec -e PYTHONPATH=/app -it backend python scripts/seed_moves.py
	@if [ "$$RUN_TESTS" = "1" ]; then \
		$(MAKE) test; \
	else \
		echo "Skipping tests (set RUN_TESTS=1 to enable)"; \
	fi

# === Lifecycle ===
up:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d

down:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) down -v --remove-orphans

rebuild:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) up -d --build

logs:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) logs -f

nuke:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) down -v --remove-orphans
# sudo pkill -f docker-proxy || true
	docker volume prune -f
	rm -rf apps/backend/alembic/versions/*
	docker volume rm infrastructure_pgdata || true

status:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) ps

# === DB ===
migrate:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) run --rm backend alembic revision --autogenerate -m "$(m)"

upgrade:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) run --rm backend alembic upgrade head

reset-db: down nuke first-launch

psql:
	docker compose -f $(COMPOSE_BASE) exec postgres psql -U gameuser -d game_db

# === Shell ===
shell:
	docker compose -f $(COMPOSE_BASE) exec backend /bin/sh

dev-shell:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_DEV) exec backend /bin/sh

# === Tests ===
test: test-backend test-frontend test-infrastructure 

test-backend:
	PYTHONPATH=apps/backend pytest tests/backend --cov=app

test-frontend:
	cd apps/frontend && npx vitest run --coverage

test-infrastructure:
	pytest tests/infrastructure

.PHONY: first-launch up down rebuild migrate upgrade logs nuke psql status shell dev-shell reset-db test test-backend test-frontend