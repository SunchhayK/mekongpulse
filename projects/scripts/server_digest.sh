#!/usr/bin/env bash
# Daily bilingual digest to the public Telegram channel for the labyrinth.ts deployment.
# Admin-guarded like server_sync.sh; there is no Cloud Scheduler twin (Cloud Run's
# scheduler jobs cover sync and patrol only).
#
# Install on the server (daily 07:00 Asia/Phnom_Penh):
#   0 7 * * * /home/ruined/mekongpulse/projects/scripts/server_digest.sh >> /home/ruined/mekongpulse/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

API="${API_BASE:-http://localhost:8080}"
ENV_FILE="${ENV_FILE:-.env.staging}"

set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

: "${ADMIN_TOKEN:?ADMIN_TOKEN missing from $ENV_FILE}"

# The endpoint answers 200 with status "posted" | "unavailable" | "error"
# (cron-friendly: a missing Telegram channel is not a failed run).
curl -fsS -m 180 -H "Authorization: Bearer $ADMIN_TOKEN" \
  -X POST "$API/api/v1/digest/send" -o /dev/null && echo "digest ok  $(date -Is)"
