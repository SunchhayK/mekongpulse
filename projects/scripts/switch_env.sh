#!/usr/bin/env bash
# Point projects/.env at one of the environment presets (kept local; never committed).
# Usage: ./scripts/switch_env.sh {development|staging|production}
set -euo pipefail
cd "$(dirname "$0")/.."

env="${1:-}"
case "$env" in
  development | staging | production) ;;
  *)
    echo "usage: $0 {development|staging|production}" >&2
    exit 1
    ;;
esac

ln -sfn ".env.$env" .env
echo "→ projects/.env -> .env.$env ($(grep -m1 '^ENVIRONMENT=' ".env.$env"))"
