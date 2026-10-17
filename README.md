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
│ • Material Design 3 Web GIS Map      │
│ • Real-time Commune Risk Isochrones  │
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

Caveats: the API is reachable only while this machine is awake and the tunnel is running; the tunnel URL changes per session, so after a tunnel restart re-run steps 2–3 (the API must learn the new `PUBLIC_BASE_URL` and the dashboard must be republished against it).

---

## Testing Across Projects

Run automated test suites across all projects:

```bash
# 1. Shared Domain Engine (92 tests)
cd projects/shared && uv run pytest

# 2. Telegram Bot Service (26 tests)
cd projects/bot && uv run pytest

# 3. FastAPI Backend (24 tests)
cd projects/backend && uv run pytest

# 4. Frontend Compilation
cd projects/frontend && bun run build
```
