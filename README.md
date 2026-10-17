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
| **`production`** | Cloud Firestore Native | GCS Audio Bucket | Webhook | Google Cloud Run (`:8080`) | Scalable serverless cloud deployment |

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

The script points `projects/.env` at the chosen preset (a symlink — all services and Docker Compose read it) and prints the active environment.

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

### 3. Production Deployment (Google Cloud)

Deploy to Cloud Run, Cloud Firestore Native, and Cloud Storage (the script is dry-run by default — it prints every command for review before anything executes):

```bash
./projects/scripts/deploy_gcp.sh             # review the plan
DRY_RUN=0 ./projects/scripts/deploy_gcp.sh   # execute (requires gcloud auth + real secrets in .env.production)
```

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
