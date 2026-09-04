#!/bin/sh
set -eu

# One-off commands (alembic, seed scripts, shell) must run instead of the server.
# `docker compose run backend alembic upgrade head` passes those args here.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Production default: 2-4 uvicorn workers (default 3). Override with UVICORN_WORKERS.
workers="${UVICORN_WORKERS:-3}"

# Non-numeric values fall back to 3.
if ! printf "%s" "$workers" | grep -Eq "^[0-9]+$"; then
  workers=3
fi

if [ "$workers" -lt 2 ]; then
  workers=2
elif [ "$workers" -gt 4 ]; then
  workers=4
fi

echo "Starting uvicorn with ${workers} workers"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$workers"
