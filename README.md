# ⚔️ PokéWars

A browser-based multiplayer strategy game inspired by **Advance Wars** and **Pokémon Showdown**. Built with FastAPI, React, PostgreSQL, Redis, and Docker.

---

## 🚀 Quick Start (First Time Setup)

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

```

---

## 🗂 Project Structure

```bash
apps/
  backend/        ← FastAPI backend + Alembic + models
  frontend/       ← React + Vite frontend

infrastructure/   ← Docker config + .env files + Compose files
```

---

## 🧬 Env Configuration

All sensitive config is handled through `.env` files:

| File                             | Purpose                      |
|----------------------------------|------------------------------|
| `.env` (in `/apps/frontend`)	   | Vite + API endpoint config   |
| `.env` (in `/apps/backend`)      | App-level secrets & DB URI   |
| `.env.db` (in `/infrastructure`) | Postgres user/pass/db name   |

> You don’t need to edit these unless you’re debugging or deploying

---

## 📜 License

MIT — free to use, remix, and deploy as long as you give credit ✌️

---

