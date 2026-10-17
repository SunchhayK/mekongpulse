#!/usr/bin/env bash
# Deploy MekongPulse to Google Cloud: Cloud Run (backend + web), Cloud Scheduler
# (telemetry sync + sentinel patrol every 15 min), Secret Manager, and the
# Telegram webhook registration.
#
# DRY RUN BY DEFAULT: every command is printed, nothing executes.
# Execute for real with:  DRY_RUN=0 ./scripts/deploy_gcp.sh
#
# Requires: gcloud (authenticated), a filled projects/.env.production preset,
# and the Telegram/Gemini/admin secrets present in Secret Manager (see step 3).
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT_ID="${GCP_PROJECT:-ai-builder-cup-511603}"
REGION="${GCP_REGION:-asia-southeast1}"
AR_REPO="${AR_REPO:-mekongpulse}"
DRY_RUN="${DRY_RUN:-1}"

BACKEND_SERVICE="mekongpulse-backend"
FRONTEND_SERVICE="mekongpulse-web"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
SECRETS=(TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET TELEGRAM_BROADCAST_CHANNEL_ID ADMIN_TOKEN LOG_SALT GEMINI_API_KEY)

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '+ %s\n' "$*"
  else
    printf '> %s\n' "$*"
    "$@"
  fi
}

capture() {
  # Runs a command and echoes its stdout (for URL discovery). Dry run prints a stub.
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '+ (capture) %s\n' "$*" >&2
    echo "https://DRY-RUN-URL.invalid"
  else
    "$@"
  fi
}

if [[ ! -f .env.production ]]; then
  echo "missing projects/.env.production preset" >&2
  exit 1
fi
# Read the production preset directly; never mutate the active .env symlink.
# shellcheck disable=SC1091
set -a && source .env.production && set +a

echo "=== MekongPulse deploy → project ${PROJECT_ID}, region ${REGION} (DRY_RUN=${DRY_RUN}) ==="

echo
echo "--- 1. enable services ---"
run gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com secretmanager.googleapis.com \
  firestore.googleapis.com storage.googleapis.com \
  --project "$PROJECT_ID"

echo
echo "--- 2. artifact registry ---"
run gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" --project "$PROJECT_ID" \
  --description "MekongPulse service images" || true

echo
echo "--- 3. secrets (values pulled from the local production env file) ---"
for secret in "${SECRETS[@]}"; do
  value="${!secret:-}"
  if [[ "$DRY_RUN" == "1" ]]; then
    run gcloud secrets create "$secret" --replication-policy=automatic --project "$PROJECT_ID"
    run gcloud secrets versions add "$secret" --data-file=- --project "$PROJECT_ID" "(from \$'$secret')"
    continue
  fi
  if [[ -z "$value" || "$value" == REPLACE_ME* ]]; then
    echo "skip: $secret is empty/placeholder in .env.production"
    continue
  fi
  if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --replication-policy=automatic --project "$PROJECT_ID"
  fi
  printf '%s' "$value" | gcloud secrets versions add "$secret" --data-file=- --project "$PROJECT_ID"
done

echo
echo "--- 4. build images (Cloud Build) ---"
run gcloud builds submit --project "$PROJECT_ID" \
  --tag "${IMAGE_BASE}/backend:latest" --file backend/Dockerfile .
run gcloud builds submit --project "$PROJECT_ID" \
  --tag "${IMAGE_BASE}/bot:latest" --file bot/Dockerfile .

echo
echo "--- 5. deploy backend (Cloud Run) ---"
run gcloud run deploy "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --image "${IMAGE_BASE}/backend:latest" \
  --allow-unauthenticated --port 8080 --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 3 --timeout 300 \
  --set-env-vars "ENVIRONMENT=production,FIRESTORE_PROJECT=${PROJECT_ID},USE_VERTEX_AI=true,VERTEX_PROJECT=${PROJECT_ID},VERTEX_LOCATION=${REGION}"
BACKEND_URL="$(capture gcloud run services describe "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "backend url: ${BACKEND_URL}"

echo
echo "--- 6. build + deploy web dashboard against the backend url ---"
run gcloud builds submit --project "$PROJECT_ID" \
  --config frontend/cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE_BASE}/frontend:latest,_API_BASE=${BACKEND_URL}" .
run gcloud run deploy "$FRONTEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --image "${IMAGE_BASE}/frontend:latest" \
  --allow-unauthenticated --port 3000 --memory 256Mi --cpu 1 \
  --min-instances 0 --max-instances 2
FRONTEND_URL="$(capture gcloud run services describe "$FRONTEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "frontend url: ${FRONTEND_URL}"

echo
echo "--- 7. wire public urls + scheduler ---"
run gcloud run services update "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "PUBLIC_BASE_URL=${BACKEND_URL},CORS_ORIGINS=${FRONTEND_URL},GCS_PUBLIC_BASE=https://storage.googleapis.com/${GCS_BUCKET:-mekongpulse-audio}" \
  --set-secrets "TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,TELEGRAM_BROADCAST_CHANNEL_ID=TELEGRAM_BROADCAST_CHANNEL_ID:latest,ADMIN_TOKEN=ADMIN_TOKEN:latest,LOG_SALT=LOG_SALT:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest"

create_or_update_job() {
  local name="$1" uri="$2"
  run gcloud scheduler jobs create http "$name" \
    --project "$PROJECT_ID" --location "$REGION" \
    --schedule "*/15 * * * *" --time-zone "Asia/Phnom_Penh" \
    --uri "$uri" --http-method POST \
    --headers "Authorization=Bearer ${ADMIN_TOKEN:-REPLACE_ME}" \
    --attempt-deadline 280s || \
    run gcloud scheduler jobs update http "$name" \
      --project "$PROJECT_ID" --location "$REGION" \
      --schedule "*/15 * * * *" --time-zone "Asia/Phnom_Penh" \
      --uri "$uri" --http-method POST \
      --headers "Authorization=Bearer ${ADMIN_TOKEN:-REPLACE_ME}"
}
create_or_update_job "mekongpulse-telemetry-sync" "${BACKEND_URL}/api/v1/telemetry/sync"
create_or_update_job "mekongpulse-sentinel-patrol" "${BACKEND_URL}/api/v1/patrol/run"

echo
echo "--- 8. register the Telegram webhook ---"
run curl -fsS "https://api.telegram.org/bot\${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${BACKEND_URL}/api/v1/telegram/webhook" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET:-REPLACE_ME}"

echo
if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry run complete - nothing was deployed. Re-run with DRY_RUN=0 after 'gcloud auth login'."
else
  echo "deploy complete: ${BACKEND_URL} · ${FRONTEND_URL}"
fi
