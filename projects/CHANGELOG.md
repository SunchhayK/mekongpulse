# Changelog

All notable changes to the MekongPulse monorepo. Versions follow [SemVer](https://semver.org/); each package under `projects/` is versioned independently.

## [0.2.0] — 2026-10-17

Web deployment moves to Firebase Hosting (static export); Cloud Run stays the backend runtime.

### Added

- `frontend` — `NEXT_OUTPUT=export` build mode (conditional in `next.config.mjs`; the containerized staging stack keeps `standalone`), plus `firebase.json` and `.firebaserc` targeting the `ai-builder-cup-9f8cd` Hosting site.
- `scripts` — `deploy_web_firebase.sh`: builds the export against a backend URL (`NEXT_PUBLIC_API_BASE_URL`) and deploys to Firebase Hosting; dry-run by default.
- `frontend` — `id`/`name` attributes on the commune search field, voice-note scrubber, and province filter (resolves the remaining console notice).

### Changed

- `scripts` — `deploy_gcp.sh` no longer deploys a web Cloud Run service; its step 6 now invokes the Firebase web deploy after capturing the backend URL, and CORS defaults to `https://ai-builder-cup-9f8cd.web.app`. `frontend/cloudbuild.yaml` is unused.
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
