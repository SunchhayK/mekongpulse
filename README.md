# MekongPulse (មេគង្គភព)

> Autonomous, hyper-localized early-warning intelligence and stage-specific agricultural advisory system for Cambodian lowland communes along the Mekong, Bassac, and Tonle Sap rivers.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    Upstream River Telemetry Sources    │
                      │  MRC Telemetry & Google Flood Hub APIs │
                      └──────────────────┬─────────────────────┘
                                         │
                                         ▼
                      ┌────────────────────────────────────────┐
                      │     projects/shared (Domain Engine)    │
                      │  • Autonomous 4-Agent Pipeline         │
                      │  • Khmer Spoken Audio Synthesis Engine │
                      │  • Spatial Reasoner (1,661 Communes)   │
                      │  • Agronomic Decision Engine           │
                      └────────────┬──────────────┬────────────┘
                                   │              │
                   ┌───────────────┘              └───────────────┐
                   ▼                                              ▼
┌──────────────────────────────────────┐      ┌──────────────────────────────────────┐
│     projects/backend (FastAPI)       │      │        projects/bot (Telegram)       │
│ • Hydrological Ingestion & Sentinel  │      │ • Bilingual Welcome (Khmer/English)  │
│ • PostgreSQL (dev) / Firestore (prod)│      │ • GPS Pin & Fuzzy Search             │
│ • Audible Voice & Advisory Dispatch  │      │ • Stage-Specific Action Cards        │
└──────────────────┬───────────────────┘      └──────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       projects/frontend (Next.js 14) │
│ • Leaflet Web GIS Map                │
│ • Risk Tiers, Alert Log, CSV Export  │
│ • Audible Khmer Directives Player    │
└──────────────────────────────────────┘
```

---

## Multi-Environment Configuration

MekongPulse supports three operating environments out-of-the-box. All scripts, environment presets, and container definitions live under `projects/`, and the commands below run from the repository root:

| Environment | Database | Storage | Bot Mode | Network / Port | Primary Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`development`** | Local PostgreSQL (`pg_db:5432`) | Local | Polling | Localhost (`:8080`, `:3000`) | Rapid local code changes with auto-reload |
| **`staging`** | Host PostgreSQL (`host.docker.internal`) | Local / GCS | Polling | Docker Network | Containerized multi-service integration |
| **`production`** | Cloud Firestore Native | GCS Audio Bucket | Webhook | Cloud Run API (`:8080`) + Firebase Hosting | Scalable serverless cloud deployment |

### Switching Environments with 1 Command

Use [`projects/scripts/switch_env.sh`](file:///Users/ruined/Home/Projects/AiBuilderCup/mekongpulse/projects/scripts/switch_env.sh) to switch the active environment preset:

```bash
# Switch to Development
./projects/scripts/switch_env.sh development

# Switch to Staging
./projects/scripts/switch_env.sh staging

# Switch to Production
./projects/scripts/switch_env.sh production
```

The script points `projects/.env` at the chosen preset (a symlink — all services and Docker Compose read it) and prints the active environment. The presets live only on your machine (`.env.*` is gitignored — they carry real secrets).

---

## Running the Application

### 1. Development Mode (All Services Concurrently)

Start the entire system with a single command:

```bash
./projects/scripts/run_dev.sh
```

This launches:

- **FastAPI Backend** on [`http://localhost:8080`](http://localhost:8080)
- **Next.js Web GIS Dashboard** on [`http://localhost:3000`](http://localhost:3000)

Press `Ctrl+C` at any time to gracefully terminate all processes.

Pass `--bot` to also start the **Telegram Bot** in live polling mode:

```bash
./projects/scripts/run_dev.sh --bot
```

### 2. Containerized Staging Mode (Docker Compose)

Run the containerized microservices stack locally:

```bash
./projects/scripts/switch_env.sh staging
docker compose -f projects/docker-compose.yml up --build
```

> **Note**: Uses the existing local PostgreSQL container (`pg_db` on port 5432) via `host.docker.internal:5432`. No duplicate PostgreSQL container is created.

### 3. Production Deployment (Google Cloud + Firebase)

The backend, scheduler jobs, and secrets deploy to Google Cloud; the dashboard deploys to Firebase Hosting. Both scripts are dry-run by default — they print every command for review before anything executes:

```bash
./projects/scripts/deploy_gcp.sh             # review the plan (backend + infra, then web)
DRY_RUN=0 ./projects/scripts/deploy_gcp.sh   # execute (requires gcloud auth + real secrets in .env.production)

# Dashboard-only redeploy (e.g. after the backend URL changes)
./projects/scripts/deploy_web_firebase.sh https://<backend-url>
DRY_RUN=0 ./projects/scripts/deploy_web_firebase.sh   # requires: bunx firebase-tools login
```

The dashboard is built as a static export (`NEXT_OUTPUT=export`) with the backend URL baked in, and served from `ai-builder-cup-9f8cd.web.app` (`FIREBASE_PROJECT` in `.env.production`).

### 4. Free-Tier Live Demo (no Google Cloud billing)

The full GCP stack (Cloud Run, Firestore, Cloud Scheduler) requires a billing account on the project. Without one, the dashboard still goes public on Firebase Hosting (free tier) with the API served from this machine through a free Cloudflare tunnel:

```bash
# 1. Start the free tunnel FIRST (no account needed; the URL changes every run).
#    HTTP/2 is more reliable than the default QUIC on flaky networks.
cloudflared tunnel --url http://localhost:8080 --protocol http2
#    note the https://<name>.trycloudflare.com URL it prints

# 2. In another terminal: the API, told its public URL so audio links point at the tunnel
cd projects && set -a && source .env.development && set +a
export PUBLIC_BASE_URL=https://<name>.trycloudflare.com
cd backend && uv run uvicorn mekong_backend.main:app --port 8080

# 3. Publish the dashboard against that URL
cd projects && DRY_RUN=0 ./scripts/deploy_web_firebase.sh https://<name>.trycloudflare.com

# 4. Optional: the Telegram bot (polling — keep a single bot process per token)
cd projects && set -a && source .env.development && set +a
cd bot && uv run python -m mekong_bot.main
```

Caveats: the API is reachable only while this machine is awake and the tunnel is running; the tunnel URL changes per session, so after a tunnel restart re-run steps 2–3 (the API must learn the new `PUBLIC_BASE_URL` and the dashboard must be republished against it). For a stable URL without GCP billing, prefer the self-hosted API below.

### 5. Self-Hosted API (labyrinth.ts, blue-green)

The dashboard stays on Firebase Hosting; the API runs on the `labyrinth.ts` host (Docker Compose, its own PostgreSQL) behind that host's existing Cloudflare tunnel. The tunnel still targets `http://localhost:8080`, which is now the **Caddy** proxy in front of two API colors — nothing publishes beyond loopback:

- `backend-blue` (`127.0.0.1:8081`) and `backend-green` (`127.0.0.1:8082`) — production slots. Caddy serves the active color and fails over to the other one the moment the active color stops answering `/api/v1/health`.
- `backend-preview` (`127.0.0.1:8083`) — where PR builds land; never in the traffic pool.

[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) runs the pipeline on every PR and merge:

| Event | What happens |
| :--- | :--- |
| **PR opened or pushed** | Dashboard → a `pr-<n>` Firebase preview channel (the URL is commented on the PR); API → preview slot rebuilt and health-checked. Live traffic untouched. |
| **Merged to main** | API → idle color rebuilt, verified, traffic switched to it; dashboard → built from main, deployed to the channel named after the new color, then promoted to live from it. |
| **`deploy` workflow → `rollback`** | API traffic flips back to the color that served before (no rebuild) and its dashboard channel is promoted to live again. |

The switch is zero-downtime: the script builds the idle color, health-checks it on its loopback port, rewrites `caddy/Caddyfile`, and hot-reloads Caddy. The color traffic just left keeps running as the rollback target until the next deploy rebuilds it. The Telegram bot is a singleton (one process per token), so it is rebuilt in place after the switch instead.

```bash
# Manual runs, on the server or over ssh (~/mekongpulse/projects)
./scripts/deploy_blue_green.sh                # build the idle color and switch to it
./scripts/deploy_blue_green.sh --preview      # rebuild the PR preview slot only
./scripts/deploy_blue_green.sh --switch-only  # flip traffic, no rebuild (rollback)
./scripts/deploy_blue_green.sh --status       # active color + slot health

# Publish the dashboard by hand (PRs and merges normally do this)
cd ~/mekongpulse/projects && DRY_RUN=0 ./scripts/deploy_web_firebase.sh https://mekongpulse-api.labyrinth.buzz
```

One-time setup for the workflow — repository secrets (`Settings → Secrets and variables → Actions`):

| Secret | Value |
| :--- | :--- |
| `FIREBASE_SERVICE_ACCOUNT` | service-account JSON granted the Firebase Hosting Admin role |
| `SSH_HOST` `SSH_USER` | the real `labyrinth.ts` address (`ssh -G labyrinth-ts` prints it) and the login user |
| `SSH_PRIVATE_KEY` | key authorized on that host: `ssh-keygen -t ed25519 -f ~/.ssh/mekongpulse_deploy` then `ssh-copy-id -i ~/.ssh/mekongpulse_deploy.pub labyrinth-ts` |

Seed both dashboard channels once so a rollback has somewhere to go — the workflow refreshes each channel's 30-day TTL (the CLI's maximum) on every merge, and a channel carries whatever `frontend/out/` held when it was deployed, so build first if that directory is stale:

```bash
cd projects/frontend
NEXT_OUTPUT=export NEXT_PUBLIC_API_BASE_URL=https://mekongpulse-api.labyrinth.buzz bun run build
bunx firebase-tools hosting:channel:deploy blue --expires 30d
bunx firebase-tools hosting:channel:deploy green --expires 30d
```

The workflow ships the tree from the checked-out commit (rsync, no `--delete`, `.env*` excluded), so the server keeps its own `.env.staging`; the Mac rsync below is still how env changes get there.

```bash
# From the Mac (source of truth: github.com/SunchhayK/mekongpulse): sync the tree
rsync -az --exclude node_modules --exclude .venv --exclude .next --exclude out \
  --exclude .git projects/ labyrinth-ts:~/mekongpulse/projects/
```

One-time ingress and schedule (already configured for `labyrinth.ts`):

- Cloudflare Zero Trust → Networks → Tunnels → public hostname `mekongpulse-api.labyrinth.buzz` → `http://localhost:8080` (Caddy — unchanged by the color switch).
- Cron every 15 minutes mirrors the Cloud Scheduler jobs: `scripts/server_sync.sh` (telemetry sync + sentinel patrol).
- Daily 07:00 Asia/Phnom_Penh cron posts the bilingual digest: `scripts/server_digest.sh`.
- The console's officer assistant publishes with the server's `ADMIN_TOKEN` entered as the officer token; `WEB_BASE_URL` (default the Firebase site) is what channel posts and drafts link (`{WEB_BASE_URL}/km/commune?code=...`).
- Optional: route a second tunnel hostname to `http://localhost:8083` and set `PREVIEW_API_URL` in the workflow, so PR dashboards talk to PR code instead of the production API.

Caveats: the stack runs with `ENVIRONMENT=staging` (PostgreSQL + local audio; no GCS needed), `restart: unless-stopped` keeps it up across server reboots, and both colors share one database — schema changes must stay backward-compatible for the color still serving traffic. The first deploy removes the pre-blue-green `backend` container that held `:8080`, on its own.

---

## Testing Across Projects

Run automated test suites across all projects:

```bash
# 1. Shared Domain Engine (126 tests)
cd projects/shared && uv run pytest

# 2. Telegram Bot Service (37 tests)
cd projects/bot && uv run pytest

# 3. FastAPI Backend (45 tests)
cd projects/backend && uv run pytest

# 4. Frontend Compilation
cd projects/frontend && bun run build
```
