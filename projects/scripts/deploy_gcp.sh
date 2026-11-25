#!/usr/bin/env bash
# Deploy MekongPulse to Google Cloud: Cloud Run (backend), Cloud Tasks (watch
# officer + rate-limited Telegram fan-out), Cloud Scheduler (15-min patrol,
# daily 07:00 digest, weekly stage-advance with OIDC auth), Firestore indexes
# (or optional Cloud SQL + PostGIS), Secret Manager, Firebase Hosting, and
# Telegram webhook registration.
#
# DRY RUN BY DEFAULT: every command is printed, nothing executes.
# Execute for real with:  DRY_RUN=0 ./scripts/deploy_gcp.sh
#
# Requires: gcloud (authenticated), a filled projects/.env.production preset
# (or ENV_FILE=/path/to/env), and secrets configured in Secret Manager.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.production}"
BACKEND_SERVICE="mekongpulse-backend"

# Capture caller-provided CLI overrides before sourcing ENV_FILE so CLI > ENV_FILE > defaults.
_CLI_GCP_PROJECT="${GCP_PROJECT:-}"
_CLI_GCP_REGION="${GCP_REGION:-}"
_CLI_AR_REPO="${AR_REPO:-}"
_CLI_FIREBASE_PROJECT="${FIREBASE_PROJECT:-}"
_CLI_DRY_RUN="${DRY_RUN:-}"
_CLI_BUILD_BOT_IMAGE="${BUILD_BOT_IMAGE:-}"
_CLI_USE_OIDC_SCHEDULER="${USE_OIDC_SCHEDULER:-}"
_CLI_USE_VERTEX_AI="${USE_VERTEX_AI:-}"
_CLI_USE_CLOUD_SQL="${USE_CLOUD_SQL:-}"
_CLI_ENABLE_CLOUD_TRACE="${ENABLE_CLOUD_TRACE:-}"
_CLI_VERTEX_LOCATION="${VERTEX_LOCATION:-}"
_CLI_CLOUD_TASKS_QUEUE="${CLOUD_TASKS_QUEUE:-}"
_CLI_CLOUD_TASKS_DISPATCH_QUEUE="${CLOUD_TASKS_DISPATCH_QUEUE:-}"
_CLI_SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-}"
_CLI_SCHEDULER_SERVICE_ACCOUNT_EMAIL="${SCHEDULER_SERVICE_ACCOUNT_EMAIL:-}"

# All env vars that must always be redacted from printed commands.
REDACT_VARS=(
  TELEGRAM_BOT_TOKEN
  TELEGRAM_WEBHOOK_SECRET
  TELEGRAM_BROADCAST_CHANNEL_ID
  ADMIN_TOKEN
  LOG_SALT
  GEMINI_API_KEY
  OFFICER_PASSCODE
  DATABASE_URL
  REDIS_URL
)

# Secrets synced to Secret Manager (GEMINI_API_KEY only when not using Vertex AI IAM).
SECRETS=(
  TELEGRAM_BOT_TOKEN
  TELEGRAM_WEBHOOK_SECRET
  TELEGRAM_BROADCAST_CHANNEL_ID
  ADMIN_TOKEN
  LOG_SALT
)

run() {
  # Print the command with secret values redacted; execute it untouched.
  local printable="$*" secret value
  for secret in "${REDACT_VARS[@]}"; do
    value="${!secret:-}"
    if [[ -n "$value" ]]; then
      printable="${printable//"$value"/<redacted>}"
    fi
  done
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '+ %s\n' "$printable"
  else
    printf '> %s\n' "$printable"
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

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing ${ENV_FILE} preset" >&2
  exit 1
fi
# Read the production preset directly; never mutate the active .env symlink.
# shellcheck disable=SC1090
set -a && source "$ENV_FILE" && set +a

# Apply precedence: CLI override > ENV_FILE > safe production default, then derive vars.
PROJECT_ID="${_CLI_GCP_PROJECT:-${GCP_PROJECT:-ai-builder-cup-9f8cd}}"
REGION="${_CLI_GCP_REGION:-${GCP_REGION:-asia-southeast1}}"
AR_REPO="${_CLI_AR_REPO:-${AR_REPO:-mekongpulse}}"
FIREBASE_PROJECT="${_CLI_FIREBASE_PROJECT:-${FIREBASE_PROJECT:-ai-builder-cup-9f8cd}}"
DRY_RUN="${_CLI_DRY_RUN:-${DRY_RUN:-1}}"
BUILD_BOT_IMAGE="${_CLI_BUILD_BOT_IMAGE:-${BUILD_BOT_IMAGE:-0}}"
USE_OIDC_SCHEDULER="${_CLI_USE_OIDC_SCHEDULER:-${USE_OIDC_SCHEDULER:-1}}"
USE_VERTEX_AI="${_CLI_USE_VERTEX_AI:-${USE_VERTEX_AI:-true}}"
USE_CLOUD_SQL="${_CLI_USE_CLOUD_SQL:-${USE_CLOUD_SQL:-0}}"
ENABLE_CLOUD_TRACE="${_CLI_ENABLE_CLOUD_TRACE:-${ENABLE_CLOUD_TRACE:-true}}"
VERTEX_LOCATION="${_CLI_VERTEX_LOCATION:-${VERTEX_LOCATION:-${REGION}}}"
CLOUD_TASKS_QUEUE="${_CLI_CLOUD_TASKS_QUEUE:-${CLOUD_TASKS_QUEUE:-mekongpulse-watch}}"
CLOUD_TASKS_DISPATCH_QUEUE="${_CLI_CLOUD_TASKS_DISPATCH_QUEUE:-${CLOUD_TASKS_DISPATCH_QUEUE:-mekongpulse-telegram-fanout}}"
SCHEDULER_SA_NAME="${_CLI_SCHEDULER_SA_NAME:-${SCHEDULER_SA_NAME:-mekongpulse-scheduler}}"
SCHEDULER_SA_EMAIL="${_CLI_SCHEDULER_SERVICE_ACCOUNT_EMAIL:-${SCHEDULER_SERVICE_ACCOUNT_EMAIL:-${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}}"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
AUDIO_BUCKET="${GCS_BUCKET:-mekongpulse-audio}"

if [[ "$USE_VERTEX_AI" != "true" ]]; then
  SECRETS+=(GEMINI_API_KEY)
fi
if [[ -n "${OFFICER_PASSCODE:-}" && "${OFFICER_PASSCODE:-}" != REPLACE_ME* ]]; then
  SECRETS+=(OFFICER_PASSCODE)
elif [[ "$DRY_RUN" == "1" ]]; then
  SECRETS+=(OFFICER_PASSCODE)
fi
if [[ "$USE_CLOUD_SQL" == "1" ]]; then
  SECRETS+=(DATABASE_URL)
fi

echo "=== MekongPulse deploy → project ${PROJECT_ID}, region ${REGION} (DRY_RUN=${DRY_RUN}, VERTEX=${USE_VERTEX_AI}, OIDC=${USE_OIDC_SCHEDULER}, CLOUD_SQL=${USE_CLOUD_SQL}) ==="

echo
echo "--- 1. enable services ---"
SERVICES=(
  run.googleapis.com
  artifactregistry.googleapis.com
  cloudbuild.googleapis.com
  cloudscheduler.googleapis.com
  cloudtasks.googleapis.com
  secretmanager.googleapis.com
  firestore.googleapis.com
  storage.googleapis.com
  firebasehosting.googleapis.com
  aiplatform.googleapis.com
  cloudtrace.googleapis.com
  monitoring.googleapis.com
  logging.googleapis.com
)
if [[ "$USE_CLOUD_SQL" == "1" ]]; then
  SERVICES+=(sqladmin.googleapis.com)
fi
run gcloud services enable "${SERVICES[@]}" --project "$PROJECT_ID"

echo
echo "--- 2. one-time resources: Firestore + indexes, audio bucket, Cloud Tasks queues ---"
if [[ "$USE_CLOUD_SQL" != "1" ]]; then
  run gcloud firestore databases create --location="$REGION" --project "$PROJECT_ID" || true
  if [[ -f firestore.indexes.json ]]; then
    (cd frontend && run bunx firebase-tools deploy --only firestore:indexes --project "$PROJECT_ID") || true
  fi
fi
run gcloud storage buckets create "gs://${AUDIO_BUCKET}" --location="$REGION" --project "$PROJECT_ID" || true
run gcloud storage buckets add-iam-policy-binding "gs://${AUDIO_BUCKET}" \
  --member=allUsers --role=roles/storage.objectViewer --project "$PROJECT_ID" || true

# Cloud Tasks queues: durable watch-officer queue + Telegram 25 msg/s fan-out queue.
run gcloud tasks queues create "$CLOUD_TASKS_QUEUE" \
  --location="$REGION" --project "$PROJECT_ID" \
  --max-dispatches-per-second=5 --max-concurrent-dispatches=5 \
  --max-attempts=3 || true
run gcloud tasks queues create "$CLOUD_TASKS_DISPATCH_QUEUE" \
  --location="$REGION" --project "$PROJECT_ID" \
  --max-dispatches-per-second=25 --max-concurrent-dispatches=10 \
  --max-attempts=5 || true

# Scheduler OIDC service account (short-lived OIDC tokens instead of static bearer tokens).
if [[ "$USE_OIDC_SCHEDULER" == "1" ]]; then
  run gcloud iam service-accounts create "$SCHEDULER_SA_NAME" \
    --display-name="MekongPulse Cloud Scheduler OIDC invoker" \
    --project "$PROJECT_ID" || true
fi

echo
echo "--- 3. artifact registry ---"
run gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" --project "$PROJECT_ID" \
  --description "MekongPulse service images" || true

echo
echo "--- 4. secrets (values pulled from ${ENV_FILE}) ---"
for secret in "${SECRETS[@]}"; do
  value="${!secret:-}"
  if [[ "$DRY_RUN" == "1" ]]; then
    run gcloud secrets create "$secret" --replication-policy=automatic --project "$PROJECT_ID"
    run gcloud secrets versions add "$secret" --data-file=- --project "$PROJECT_ID" "(from \$'$secret')"
    continue
  fi
  if [[ -z "$value" || "$value" == REPLACE_ME* ]]; then
    echo "skip: $secret is empty/placeholder in ${ENV_FILE}"
    continue
  fi
  if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --replication-policy=automatic --project "$PROJECT_ID"
  fi
  printf '%s' "$value" | gcloud secrets versions add "$secret" --data-file=- --project "$PROJECT_ID"
done

echo
echo "--- 5. build images (Cloud Build) ---"
run gcloud builds submit --project "$PROJECT_ID" \
  --config cloudbuild.yaml \
  --substitutions "_DOCKERFILE=backend/Dockerfile,_IMAGE=${IMAGE_BASE}/backend:latest" .
if [[ "$BUILD_BOT_IMAGE" == "1" ]]; then
  run gcloud builds submit --project "$PROJECT_ID" \
    --config cloudbuild.yaml \
    --substitutions "_DOCKERFILE=bot/Dockerfile,_IMAGE=${IMAGE_BASE}/bot:latest" .
else
  echo "skip: bot image build disabled (webhook runs inside backend; set BUILD_BOT_IMAGE=1 to build)"
fi

echo
echo "--- 6. deploy backend (Cloud Run) ---"
BASE_ENV="^|^ENVIRONMENT=production|USE_VERTEX_AI=${USE_VERTEX_AI}|VERTEX_PROJECT=${PROJECT_ID}|VERTEX_LOCATION=${VERTEX_LOCATION:-${REGION}}|ENABLE_CLOUD_TRACE=${ENABLE_CLOUD_TRACE}|FIREBASE_PROJECT_ID=${FIREBASE_PROJECT}"
if [[ "$USE_CLOUD_SQL" == "1" ]]; then
  BASE_ENV="${BASE_ENV}|REPOSITORY_BACKEND=postgres"
else
  BASE_ENV="${BASE_ENV}|FIRESTORE_PROJECT=${PROJECT_ID}"
fi

DEPLOY_ARGS=(
  gcloud run deploy "$BACKEND_SERVICE"
  --project "$PROJECT_ID" --region "$REGION"
  --image "${IMAGE_BASE}/backend:latest"
  --allow-unauthenticated --port 8080 --memory 512Mi --cpu 1
  --no-cpu-throttling
  --min-instances 0 --max-instances 3 --timeout 300
  --set-env-vars "$BASE_ENV"
)
if [[ "$USE_CLOUD_SQL" == "1" && -n "${CLOUD_SQL_CONNECTION_NAME:-}" ]]; then
  DEPLOY_ARGS+=(--add-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME")
fi
run "${DEPLOY_ARGS[@]}"

BACKEND_URL="$(capture gcloud run services describe "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "backend url: ${BACKEND_URL}"

if [[ "$USE_OIDC_SCHEDULER" == "1" ]]; then
  run gcloud run services add-iam-policy-binding "$BACKEND_SERVICE" \
    --project "$PROJECT_ID" --region "$REGION" \
    --member="serviceAccount:${SCHEDULER_SA_EMAIL}" \
    --role="roles/run.invoker" || true
fi

echo
echo "--- 7. build + deploy the web dashboard (Firebase Hosting) ---"
DRY_RUN="$DRY_RUN" ENV_FILE="$ENV_FILE" ./scripts/deploy_web_firebase.sh "$BACKEND_URL"
FRONTEND_URL="https://${FIREBASE_PROJECT}.web.app"
echo "frontend url: ${FRONTEND_URL}"

echo
echo "--- 8. wire public urls, runtime state, secrets + schedulers ---"
CORS_ORIGINS_VALUE="${FRONTEND_URL},https://${FIREBASE_PROJECT}.firebaseapp.com"
UPDATE_ENV="^|^PUBLIC_BASE_URL=${BACKEND_URL}|WEB_BASE_URL=${FRONTEND_URL}|CORS_ORIGINS=${CORS_ORIGINS_VALUE}"
UPDATE_ENV="${UPDATE_ENV}|GCS_BUCKET=${AUDIO_BUCKET}|GCS_PUBLIC_BASE=https://storage.googleapis.com/${AUDIO_BUCKET}"
UPDATE_ENV="${UPDATE_ENV}|CLOUD_TASKS_QUEUE=${CLOUD_TASKS_QUEUE}|CLOUD_TASKS_DISPATCH_QUEUE=${CLOUD_TASKS_DISPATCH_QUEUE}"
UPDATE_ENV="${UPDATE_ENV}|CLOUD_TASKS_LOCATION=${REGION}|CLOUD_TASKS_PROJECT=${PROJECT_ID}"
if [[ "$USE_OIDC_SCHEDULER" == "1" ]]; then
  UPDATE_ENV="${UPDATE_ENV}|OIDC_AUDIENCE=${BACKEND_URL}|SCHEDULER_SERVICE_ACCOUNT_EMAIL=${SCHEDULER_SA_EMAIL}|CLOUD_TASKS_SERVICE_ACCOUNT=${SCHEDULER_SA_EMAIL}"
fi
if [[ -n "${OFFICER_TELEGRAM_IDS:-}" ]]; then
  UPDATE_ENV="${UPDATE_ENV}|OFFICER_TELEGRAM_IDS=${OFFICER_TELEGRAM_IDS}"
fi
if [[ -n "${REDIS_URL:-}" && "${REDIS_URL:-}" != REPLACE_ME* ]]; then
  UPDATE_ENV="${UPDATE_ENV}|REDIS_URL=${REDIS_URL}"
fi
if [[ -n "${AUDIO_CDN_BASE_URL:-}" && "${AUDIO_CDN_BASE_URL:-}" != REPLACE_ME* ]]; then
  UPDATE_ENV="${UPDATE_ENV}|AUDIO_CDN_BASE_URL=${AUDIO_CDN_BASE_URL}"
fi

SECRET_BINDINGS="TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,TELEGRAM_BROADCAST_CHANNEL_ID=TELEGRAM_BROADCAST_CHANNEL_ID:latest,ADMIN_TOKEN=ADMIN_TOKEN:latest,LOG_SALT=LOG_SALT:latest"
if [[ "$USE_VERTEX_AI" != "true" ]]; then
  SECRET_BINDINGS="${SECRET_BINDINGS},GEMINI_API_KEY=GEMINI_API_KEY:latest"
fi
if [[ "$DRY_RUN" == "1" || ( -n "${OFFICER_PASSCODE:-}" && "${OFFICER_PASSCODE:-}" != REPLACE_ME* ) ]]; then
  SECRET_BINDINGS="${SECRET_BINDINGS},OFFICER_PASSCODE=OFFICER_PASSCODE:latest"
fi
if [[ "$USE_CLOUD_SQL" == "1" ]]; then
  SECRET_BINDINGS="${SECRET_BINDINGS},DATABASE_URL=DATABASE_URL:latest"
fi

run gcloud run services update "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "$UPDATE_ENV" \
  --set-secrets "$SECRET_BINDINGS"

create_or_update_job() {
  local name="$1" schedule="$2" uri="$3"
  local create_auth_args=() update_auth_args=()
  if [[ "$USE_OIDC_SCHEDULER" == "1" ]]; then
    create_auth_args=(
      --oidc-service-account-email "$SCHEDULER_SA_EMAIL"
      --oidc-token-audience "$BACKEND_URL"
    )
    update_auth_args=("${create_auth_args[@]}")
  else
    create_auth_args=(
      --headers "Authorization=Bearer ${ADMIN_TOKEN:-REPLACE_ME}"
    )
    update_auth_args=(
      --update-headers "Authorization=Bearer ${ADMIN_TOKEN:-REPLACE_ME}"
    )
  fi
  run gcloud scheduler jobs create http "$name" \
    --project "$PROJECT_ID" --location "$REGION" \
    --schedule "$schedule" --time-zone "Asia/Phnom_Penh" \
    --uri "$uri" --http-method POST \
    "${create_auth_args[@]}" \
    --attempt-deadline 280s || \
    run gcloud scheduler jobs update http "$name" \
      --project "$PROJECT_ID" --location "$REGION" \
      --schedule "$schedule" --time-zone "Asia/Phnom_Penh" \
      --uri "$uri" --http-method POST \
      "${update_auth_args[@]}" \
      --attempt-deadline 280s
}

# 15-minute telemetry sync + sentinel patrol
create_or_update_job "mekongpulse-sentinel-patrol" "*/15 * * * *" "${BACKEND_URL}/api/v1/patrol/run"
# Daily 07:00 Phnom Penh bilingual digest
create_or_update_job "mekongpulse-daily-digest" "0 7 * * *" "${BACKEND_URL}/api/v1/digest/send"
# Weekly Monday 08:00 Phnom Penh crop-stage auto-advance
create_or_update_job "mekongpulse-stage-advance" "0 8 * * 1" "${BACKEND_URL}/api/v1/digest/stage-advance"

echo
echo "--- 9. register the Telegram webhook ---"
run curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN:-REPLACE_ME}/setWebhook" \
  --data-urlencode "url=${BACKEND_URL}/api/v1/telegram/webhook" \
  --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET:-REPLACE_ME}"

echo
if [[ "$DRY_RUN" == "1" ]]; then
  echo "dry run complete - nothing was deployed. Re-run with DRY_RUN=0 after 'gcloud auth login'."
else
  echo "deploy complete: ${BACKEND_URL} · ${FRONTEND_URL}"
fi
