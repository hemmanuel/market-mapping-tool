#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export POSTGRES_URL="${POSTGRES_URL:-postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db}"

if [ -x "$ROOT_DIR/.venv/bin/alembic" ]; then
  ALEMBIC_BIN="$ROOT_DIR/.venv/bin/alembic"
else
  ALEMBIC_BIN="${ALEMBIC_BIN:-alembic}"
fi

cd "$ROOT_DIR"
exec "$ALEMBIC_BIN" upgrade head
