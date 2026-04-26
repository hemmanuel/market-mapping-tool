#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
export FRONTEND_PORT="${FRONTEND_PORT:-3300}"
export API_BASE_URL="${API_BASE_URL:-http://localhost:8100}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-$API_BASE_URL}"

cd "$ROOT_DIR/frontend"
exec npm run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT"
