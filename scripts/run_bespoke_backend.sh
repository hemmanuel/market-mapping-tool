#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
export BACKEND_PORT="${BACKEND_PORT:-8100}"
export POSTGRES_URL="${POSTGRES_URL:-postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db}"
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:17687}"
export NEO4J_USERNAME="${NEO4J_USERNAME:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:19000}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-admin}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-password}"
export MINIO_BUCKET_NAME="${MINIO_BUCKET_NAME:-market-maps-bespoke}"

if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m uvicorn src.api.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
