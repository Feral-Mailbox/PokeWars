# ⚔️ PokéWars

A browser-based multiplayer strategy game inspired by **Advance Wars** and **Pokémon Showdown**. Built with FastAPI, React, PostgreSQL, Redis, and Docker.

---

## 🚀 Quick Start (First Time Setup)

### 1. Generate Local Certificates

Use [`mkcert`](https://github.com/FiloSottile/mkcert):

```bash
mkcert -install
mkcert localhost 127.0.0.1 ::1
mv localhost+2.pem fullchain.pem
mv localhost+2-key.pem privkey.pem
mkdir -p infrastructure/certs
mv fullchain.pem privkey.pem infrastructure/certs/
```

### 2. Create Environment Files

All sensitive config is handled through `.env` files:

| File                             | Purpose                      |
|----------------------------------|------------------------------|
| `.env` (in `/apps/frontend`)	   | Vite + API endpoint config   |
| `.env` (in `/apps/backend`)      | App-level secrets & DB URI   |
| `.env.db` (in `/infrastructure`) | Postgres user/pass/db name   |

Utilize the example `.env` files in the listed directories to aid in your setup

### 3. Launch Containers And Update Tables

```bash
make first-launch
```

This will:
- Build the entire project via Docker Compose
- Run Alembic migrations to sync the database
- Launch backend, frontend, Redis, and Postgres
- Your browser should open to `http://localhost:5173` (frontend)
- Backend is at `http://localhost:8000`

> ⚠️ Don’t skip this on first boot — this wires up all tables and services.

---

## 🛠 Prerequisites

You’ll need:

- [Docker](https://www.docker.com/)
- [Docker Compose v2](https://docs.docker.com/compose/)
- [Make](https://www.gnu.org/software/make/) (`brew install make` or `sudo apt install make`)

Optional:
- [pgAdmin4](https://www.pgadmin.org/) for visualizing the Postgres DB (will be at `http://localhost:5050`)

---

## 🧪 Dev Commands

```bash
# Spin up containers (backend, frontend, db, etc.)
make up

# Shut everything down cleanly
make down

# Apply all migrations to the DB
make upgrade

# Generate a new Alembic migration (autogenerates from models)
make migrate m="some message"

# Get into a psql shell
make db-shell

# List tables in the database
make db-tables

# Wipe DB, containers, and Alembic revisions
make nuke

# Open a dev shell inside backend container
make shell

# Run all tests
make test

# Run tests with coverage reports
make coverage
# Backend HTML  → apps/backend/coverage/index.html
# Frontend HTML → apps/frontend/coverage/lcov-report/index.html

```

`make test` / `make coverage` create a local `.venv` (if missing) and install `apps/backend/requirements.dev.txt`.  
Frontend coverage uses Vitest (`npm run test:coverage`), or Docker Node if `npm` isn’t on your PATH.

---

## 🔁 CI (GitHub Actions)

Continuous integration lives in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). There is **no automated deploy workflow** yet — production updates are still done on the host (`git pull`, `make upgrade`, `make up`).

### When it runs

The **CI** workflow starts on:

- every push to `main`
- every pull request

### What the `test` job does

Runs on `ubuntu-latest` as a single job named **`test`** (this is the status check to require in branch protection):

1. **Backend** — Python 3.12, `pip install -r apps/backend/requirements.dev.txt`, then pytest with coverage (`tests/backend`)
2. **Infrastructure** — pytest for Docker Compose / nginx / committed env *example* files (`tests/infrastructure`)
3. **Frontend** — Node 20, `npm ci` and `npm run test:coverage` in `apps/frontend`
4. **Artifacts** — uploads `apps/backend/coverage` and `apps/frontend/coverage` as `coverage-reports` (14-day retention), even if a later step fails

Live `.env` files are gitignored. Infra tests assert `infrastructure/.env.db.example` (and, locally, compare keys to `.env.db` if that file exists).

Runs and logs: **Actions** tab on the GitHub repo. Download coverage from a run’s **Artifacts**.

### Local vs CI

| | Local | GitHub Actions |
|---|---|---|
| Command | `make test` / `make coverage` | workflow `test` job |
| Backend | project `.venv`, `tests/backend` | same pytest + coverage |
| Frontend | `npm run test:coverage` (or Node Docker) | `npm ci && npm run test:coverage` |
| Infra | `make test-infrastructure` | same `tests/infrastructure` suite |

### Branch protection

Protect `main` in GitHub (**Settings → Rules → Rulesets**, or **Settings → Branches**):

- Require the **`test`** status check to pass before merge
- Block force pushes and branch deletion
- Optionally require a pull request (skip required reviewers if you work alone)

Do not merge or deploy a commit unless this check is green.

---

## 🗂 Project Structure

```bash
.github/workflows/  ← GitHub Actions (ci.yml)
apps/
  backend/          ← FastAPI backend + Alembic + models
  frontend/         ← React + Vite frontend
tests/              ← Backend, frontend, and infrastructure tests
infrastructure/     ← Docker config + .env examples + Compose files
```

---

## 📜 License

MIT — free to use, remix, and deploy as long as you give credit ✌️

---

