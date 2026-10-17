#!/usr/bin/env bash
# Local development stack: FastAPI backend + Next.js dashboard (+ Telegram bot poller).
# Usage: ./scripts/run_dev.sh [--bot]
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -e .env ]]; then
  echo "no .env found; switching to the development preset"
  ./scripts/switch_env.sh development
fi

with_bot="${1:-}"
backend_port="${BACKEND_PORT:-8080}"
web_port="${FRONTEND_PORT:-3000}"

pids=()
cleanup() {
  echo
  echo "stopping dev stack..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo "→ backend  http://localhost:${backend_port} (uvicorn --reload)"
(cd backend && uv run uvicorn mekong_backend.main:app --reload --port "$backend_port") &
pids+=($!)

echo "→ frontend http://localhost:${web_port} (next dev)"
(cd frontend && bun run dev) &
pids+=($!)

if [[ "$with_bot" == "--bot" ]]; then
  echo "→ bot      Telegram long-polling"
  (cd bot && uv run python -m mekong_bot.main) &
  pids+=($!)
fi

wait
