# Changelog

All notable changes to the MekongPulse monorepo. Versions follow [SemVer](https://semver.org/); each package under `projects/` is versioned independently.

## [0.1.3] — 2026-10-17

### Fixed

- `shared` — the Khmer bulletin polish prompt now forbids preamble/meta text and markdown. A live smoke test showed the model prefixing the bulletin with "Below is the revised message…" plus `**`/`---` formatting, and that exact text was what the TTS voice note spoke; the polished output now starts with the bulletin itself.
- `scripts` — `run_dev.sh` now loads the active `.env` preset into the environment before starting services; previously the backend/bot ran without `ADMIN_TOKEN`, `LOG_SALT`, or the bot token (defaults only), so admin routes returned 401 in dev.
- `scripts` — `deploy_gcp.sh` corrected for the API-key path and hardened before its first live run: Cloud Run now gets `USE_VERTEX_AI=false` (the stale `VERTEX_*` env would have broken the first production boot), `GCS_BUCKET` is passed to the service, and a new step 2 provisions the Firestore database plus the public-read audio bucket. Command printing now redacts secret values in both dry and real modes, and the Telegram webhook step expands the bot token (it previously sent a literal `${TELEGRAM_BOT_TOKEN}`).

### Added

- `docs` — free-tier live demo path (local API + `cloudflared` tunnel + Firebase Hosting) in `README.md`, for running without a GCP billing account.

## [0.2.1] — 2026-10-17

Voice bulletins now actually reach users — both interactive paths never requested them.

### Fixed

- `frontend` — 0.2.1: assessments now send `with_audio: true`. The dashboard never requested audio, so `assessment.audio` was always null and the voice player's controls were permanently disabled. The dialog copy now sets expectations for the ~minute TTS takes.
- `bot` — 0.2.0: `/risk`, location, and callback lookups reply with the Khmer voice bulletin, uploaded as voice bytes (Telegram's servers cannot fetch dev URLs like `http://localhost:8080`), with a typing indicator while synthesis runs.

## [0.1.2] — 2026-10-17

Security hardening: transport loggers no longer print request URLs.

### Fixed

- `shared` — `configure_logging` now keeps `httpx`/`httpcore` at WARNING. httpx logs full request URLs at INFO, and Telegram API URLs embed the bot token (`/bot<token>/getMe`), which leaked the token into service logs (and would have reached Cloud Logging in production). Found while verifying the dev boot.
- `shared` — regression test in `tests/test_logging_utils.py` asserts the transport loggers stay silenced.

## [0.2.0] — 2026-10-17

Web deployment moves to Firebase Hosting (static export); Cloud Run stays the backend runtime.

### Added

- `frontend` — `NEXT_OUTPUT=export` build mode (conditional in `next.config.mjs`; the containerized staging stack keeps `standalone`), plus `firebase.json` and `.firebaserc` targeting the `ai-builder-cup-9f8cd` Hosting site.
- `scripts` — `deploy_web_firebase.sh`: builds the export against a backend URL (`NEXT_PUBLIC_API_BASE_URL`) and deploys to Firebase Hosting; dry-run by default.
- `frontend` — `id`/`name` attributes on the commune search field, voice-note scrubber, and province filter (resolves the remaining console notice).

### Changed

- `scripts` — `deploy_gcp.sh` no longer deploys a web Cloud Run service; its step 6 now invokes the Firebase web deploy after capturing the backend URL, and CORS defaults to `https://ai-builder-cup-9f8cd.web.app`. `frontend/cloudbuild.yaml` removed.
- `repo` — environment presets (`.env.development`, `.env.staging`, `.env.production`) are no longer tracked in git; they now hold real secrets and live only on the operator's machine (`.env.*` is gitignored).
- `repo` — production Gemini runs on the API-key path (`USE_VERTEX_AI=false`): no Vertex project, no cross-project IAM. `technical-report.md` updated to match.
- `frontend` — version 0.2.0.

## [0.1.1] — 2026-10-17

Hardening pass after the first end-to-end runs against live MRC telemetry and PostgreSQL.

### Fixed

- `shared` — risk reads from PostgreSQL failed with `KeyError`: the row mapper expected `lat`/`lng`, the columns are `latitude`/`longitude`.
- `shared` — `CommuneRisk.station_level_m` was always `null` in Postgres reads; `risk_map`/`get_commune_risk` now attach the station's latest gauge reading (parity with the in-memory repository).
- `shared` — the elevation rule is now distance-gated (`WATER_SURFACE_PROXY_MAX_KM = 50`): a gauge more than 50 km away no longer fabricates DANGER for communes outside the backwater corridor (INV-01). On live data this reclassified 66 remote coastal/lake communes from DANGER to their stage-based tier; head-based lead times fall back to stage-based estimates at the same distance. Unknown distance stays conservative.
- `frontend` — `/favicon.ico` 404 (sole console error on the dashboard); added `app/icon.svg` (M3-token palette).

### Added

- `shared` — `tests/test_weather.py` covering FR-02 (48h/7d rain windows, 24h peak, soil moisture, short-forecast and HTTP-error paths).
- `shared` — distance-gate tests in `tests/test_risk.py` (near/far/unknown station distance).

### Changed

- All three Docker images delete the uv/bun download caches in the same layer (smaller images; keeps `gcloud builds submit` BuildKit-free compatible).

## [0.1.0] — 2026-10-17

Initial build: shared domain engine (FR-01..05, 07), FastAPI backend (FR-06, 09 + APIs), Telegram bot, Next.js 14 M3 dashboard, multi-environment presets (`dev`/`staging`/`production`), local Docker Compose staging stack, and the dry-run-first GCP deploy script.
