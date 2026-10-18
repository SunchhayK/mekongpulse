#!/usr/bin/env bash
# Periodic sentinel patrol for the labyrinth.ts deployment. The patrol runs a
# full pipeline.sync() first, so it covers telemetry, weather and risk refresh.
# Mirrors the two Cloud Scheduler jobs in deploy_gcp.sh.
#
# Install on the server (every 15 minutes):
#   */15 * * * * /home/ruined/mekongpulse/projects/scripts/server_sync.sh >> /home/ruined/mekongpulse/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

API="${API_BASE:-http://localhost:8080}"
ENV_FILE="${ENV_FILE:-.env.staging}"

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

: "${ADMIN_TOKEN:?ADMIN_TOKEN missing from $ENV_FILE}"

# /patrol/run performs a full pipeline.sync() before the sentinel pass, so a
# separate /telemetry/sync here would duplicate every ingest and risk write.
curl -fsS -m 180 -H "Authorization: Bearer $ADMIN_TOKEN" \
  -X POST "$API/api/v1/patrol/run" -o /dev/null && echo "patrol ok  $(date -Is)"
