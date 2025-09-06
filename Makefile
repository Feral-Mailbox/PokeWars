# File: Makefile

# Default environment
ENV ?= dev

# Docker Compose file paths
PROJECT = poketactics
COMPOSE_BASE = infrastructure/docker-compose.yml
COMPOSE_DEV = infrastructure/docker-compose.dev.yml
DC_NON_DEV = docker compose -p $(PROJECT) -f $(COMPOSE_BASE)
DC = docker compose -p $(PROJECT) -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)

# === Startup ===
first-launch:
	mkdir -p infrastructure/certs infrastructure/assets infrastructure/nginx
	@echo "Make sure your certs exist at infrastructure/certs/{fullchain.pem,privkey.pem}"
	$(DC) up -d
	
first-launch:
	$(DC) down
	$(DC) up -d
	$(DC) run --rm backend alembic revision --autogenerate -m "init"
	$(DC) run --rm backend alembic upgrade head
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
	$(DC) up -d

down:
	$(DC) down

restart:
	$(DC) down
	$(DC) up -d

build:
	$(DC) build

rebuild:
	DOCKER_BUILDKIT=1 $(DC) build --no-cache
	$(DC) up -d

logs:
	$(DC) logs -f --tail=200

ps:
	$(DC) ps

nuke:
	$(DC) down -v --remove-orphans
	docker image prune -f
	docker volume rm infrastructure_pgdata || true

# === DB ===
migrate:
	$(DC) run --rm backend alembic revision --autogenerate -m "$(m)"

upgrade:
	$(DC) run --rm backend alembic upgrade head

reset-db: down nuke first-launch

psql:
	$(DC_NON_DEV) exec postgres psql -U gameuser -d game_db

# === Shell ===
shell:
	$(DC_NON_DEV) exec backend /bin/sh

dev-shell:
	$(DC) exec backend /bin/sh

# === Tests ===
test: test-backend test-frontend test-infrastructure 

test-backend:
	PYTHONPATH=apps/backend pytest tests/backend --cov=app

test-frontend:
	cd apps/frontend && npx vitest run --coverage

test-infrastructure:
	pytest tests/infrastructure

.PHONY: first-launch up down rebuild migrate upgrade logs nuke psql status shell dev-shell reset-db test test-backend test-frontend