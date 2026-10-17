#!/usr/bin/env bash
# Build the dashboard as a static export and ship it to Firebase Hosting.
# The API base URL is baked at build time (NEXT_PUBLIC_API_BASE_URL).
#
# Usage:  ./scripts/deploy_web_firebase.sh [backend_url]
#         backend_url defaults to PUBLIC_BASE_URL from .env.production.
# DRY_RUN=1 (default) prints the plan; DRY_RUN=0 executes.
set -euo pipefail
cd "$(dirname "$0")/.."

DRY_RUN="${DRY_RUN:-1}"

if [[ ! -f .env.production ]]; then
  echo "missing projects/.env.production preset" >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a && source .env.production && set +a

FIREBASE_PROJECT="${FIREBASE_PROJECT:-ai-builder-cup-9f8cd}"
BACKEND_URL="${1:-${PUBLIC_BASE_URL:-}}"

case "$BACKEND_URL" in
  "" | REPLACE_ME*)
    echo "backend url required: pass it as an argument or set PUBLIC_BASE_URL" >&2
    exit 1
    ;;
esac

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '+ %s\n' "$*"
  else
    printf '> %s\n' "$*"
    "$@"
  fi
}

echo "=== MekongPulse web → Firebase Hosting ($FIREBASE_PROJECT), API base $BACKEND_URL (DRY_RUN=$DRY_RUN) ==="

(
  cd frontend
  run env NEXT_OUTPUT=export NEXT_PUBLIC_API_BASE_URL="$BACKEND_URL" bun run build
  run bunx firebase-tools deploy --only hosting --project "$FIREBASE_PROJECT"
)

if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry run complete - nothing deployed. Re-run with DRY_RUN=0 after 'bunx firebase-tools login'."
else
  echo "web deployed: https://${FIREBASE_PROJECT}.web.app"
fi
