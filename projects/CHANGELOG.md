# Changelog

All notable changes to the MekongPulse monorepo. Versions follow [SemVer](https://semver.org/); each package under `projects/` is versioned independently.

## [0.9.0] — 2026-10-18

Assistant replies render as markdown, the officer thread survives refresh, and channel-post failures explain themselves.

### Added

- `frontend` — 0.7.0: assistant replies render through `react-markdown` + `remark-gfm` — headings, bold/italic, lists, tables, code, blockquotes, and safe external links, with no raw HTML — styled at chat scale for Khmer text. The conversation and focused commune now persist in `localStorage` (60-message cap, defensive validation, storage failures degrade silently) with a clear-conversation control. 342 message keys per locale.
- `backend` — 0.5.0: admin `GET /api/v1/telegram/channel` verifies that the bot can see the configured broadcast channel and returns its id/type/title/username, or `ok: false` with actionable setup guidance. Publish and digest failures now map Telegram errors (`chat not found`, missing rights, blocked/kicked, timeout/network) to operator instructions instead of raw error text; the digest reports publisher errors as `status: error` rather than claiming success.

### Changed

- `technical-report.md` 1.6.0 → 1.7.0 — markdown rendering, client-side thread persistence, and the channel diagnostic endpoint documented; test counts refreshed (146 shared, 83 backend, 37 bot).
- `product-report.md` 1.5.0 → 1.6.0 — assistant formatting/history and channel-setup guidance reflected in FR-13.

## [0.8.0] — 2026-10-18

The advisor survives one model's daily quota by rotating to sibling Gemini Flash models at the call level.

### Added

- `shared` — 0.6.0: `model_rotation.py` — an ordered chain from `GEMINI_TEXT_MODEL` plus `GEMINI_FALLBACK_MODELS` (default `gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash-lite`) with in-process cooldowns: quota 429 for one hour, overload 503 for one minute, missing model 404 for six hours. Both engines rotate per model call — an ADK `BaseLlm` wrapper and the native google-genai ReAct caller — and STT follows the same chain, so a failed turn is never replayed and `publish_to_channel` cannot post twice. A failure after partial output is raised, not retried.

### Changed

- `technical-report.md` 1.5.0 → 1.6.0 — model fallback documented in the architecture and security notes; ADR-0011 records why rotation happens per call and why Gemma was rejected. Verified against the live key: `gemini-3.7-flash`, `gemini-3.6-flash`, and `gemini-3.5-flash-lite` each return tool calls; `gemma-4-26b-a4b-it` emits a correct function call but leaks its reasoning and ignored the Khmer instruction in the final answer, while `gemma-4-31b-it` returns 500 with tools.
- Test counts refreshed: 146 shared, 73 backend, 37 bot.

## [0.7.0] — 2026-10-18

The officer assistant becomes a first-class page with passcode sign-in and Khmer voice input — no more pasting the admin token.

### Added

- `shared` — 0.5.0: `stt.py` — `transcribe_audio(settings, audio, mime_type, locale_hint)` sends a recorded clip to `gemini-3.8-flash` audio understanding and returns the transcript; no key, provider failure, or an empty result raises `TranscriptionUnavailable` instead of leaking a 500. Config gains `OFFICER_PASSCODE` (falls back to `ADMIN_TOKEN`) and `OFFICER_SESSION_TTL_HOURS` (default 12).
- `backend` — 0.4.0: `POST /api/v1/officer/login` exchanges the officer passcode for an HMAC-SHA256-signed, expiring session (`v1.<exp>.<sig>`); wrong passcode 401, sign-in unconfigured 503, five failed attempts per IP per minute 429, all comparisons constant-time. `POST /api/v1/advisor/transcribe` (`{audio_base64, mime_type, locale_hint}` → `{text}`; 413 above 4 MB decoded, 503 when transcription is unavailable). The advisor authorizes publishing with `Authorization: Bearer <session>`; the legacy `X-Officer-Token` admin header remains for scripts.
- `frontend` — 0.6.0: dedicated assistant page `/{locale}/assistant` — full-page chat with a focus-commune chip, collapsible tool trace, and action statuses, linked from the header nav, the bottom nav, and a dashboard CTA card. Sign-in card replaces the raw token field: passcode → stored session with client-side expiry and sign-out. Khmer-capable voice input (MediaRecorder → server STT, 60 s cap, permission/size/unavailable handling, cancel discards without a request). 340 message keys per locale.

### Changed

- `frontend` — the sidebar officer panel is gone; the assistant now has its own surface instead of sitting at the edge of the dashboard.
- `docs` — product and technical reports 1.5.0: FR-13 and AC-11 cover session sign-in, new AC-14 covers spoken Khmer input; the security section documents the session bearer token and the retained script header; ADR-0010 records the passcode → session and server-side STT decisions; test counts refreshed (135 shared, 73 backend, 37 bot).

## [0.6.1] — 2026-10-18

The advisor degrades gracefully when the LLM provider fails (Gemini free-tier 429 exhausted).

### Fixed

- `shared` — 0.4.1: `answer()` / `answer_detailed()` classify provider failures (`google.genai` ClientError/ServerError, ADK's resource-exhausted wrapper) and raise `AdvisorUnavailable` instead of leaking the raw exception. `POST /api/v1/advisor` now returns the designed 503 problem instead of a 500, and the Telegram advisor keeps its friendly fallback text. Found while live-verifying the new endpoint with the free-tier quota exhausted.

## [0.6.0] — 2026-10-18

Verification and ground truth: a deterministic evidence layer, field reports, an officer assistant with real channel actions, a bilingual daily digest, and a Khmer-first bilingual web with a public commune page.

### Added

- `shared` — 0.4.0: `evidence.py` — deterministic QC over the stored station series (gaps, stuck values, spikes, range), heuristic cross-checks (rainfall agreement, upstream coherence), a confidence label with stable reason ids, a 5-step bilingual evidence chain, and the MRC-style limitations notice; no LLM in any verdict. `digest.py` — `build_digest(repo, settings) -> (khmer, english)` from persisted risk rows only.
- `shared` — three officer tools in `adk_tools.py`: `get_commune_evidence`, `draft_status_update` (deterministic bilingual text from stored rows), and `publish_to_channel` (a real post to the public channel, gated by the officer token, statuses `denied`/`unavailable`/`posted`/`error`); tool-call tracing via `answer_detailed` → `AdvisorOutcome` with the recorded calls. `FieldReport` model + `field_reports` table with idempotent DDL and `add_field_report`/`list_field_reports` across the memory, PostgreSQL, and Firestore repositories; `WEB_BASE_URL` setting (defaults to the Firebase console) for commune-page links.
- `backend` — 0.3.0: `GET /api/v1/communes/{code}/evidence` (provenance payload; 404/409 problems); `POST /api/v1/communes/{code}/reports` (201, source "web") and `GET .../reports` (limit 1..100); `POST /api/v1/advisor` returning `{reply, tool_calls, actions}`, with publishing driven by the `X-Officer-Token` header (the admin token); admin-guarded `POST /api/v1/digest/send` posting the bilingual digest to the public channel.
- `bot` — 0.4.0: `/report` flow — pick a subscribed commune, answer `water_reached`/`no_water`/`other` with buttons, reporter label recorded, source "telegram"; `/digest` returns the bilingual digest in DM; escalation posts now append the commune-page link (`{WEB_BASE_URL}/km/commune?code=...`).
- `frontend` — 0.5.0: next-intl 3.26.5 with Khmer-default `[locale]` routing (English toggle) across the console, static export with `trailingSlash` and the Firebase `/` rewrite to `/km/index.html`; new public commune page `/{locale}/commune?code=XXXXXX` (one-tap Listen with a text fallback when audio is null, crop-stage chips, evidence summary, field reports, share); `AssessmentDialog` shows the evidence panel, field reports and a link to the full page; officer assistant panel (chat UI, collapsible tool trace, channel-post status, token kept in localStorage); 316 message keys per locale.
- `scripts` — `server_digest.sh`: daily 07:00 (Asia/Phnom_Penh) cron trigger for the digest, mirroring `server_sync.sh` and its admin bearer-token pattern.
- `docs` — product and technical reports 1.4.0: FR-11..15 and AC-09..13; relay-mediated farmer reach with `research/farmer-reach.md`; ADR-0007 (Telegram as relay/broadcast surface, supersedes ADR-0003), ADR-0008 (deterministic verification layer), ADR-0009 (next-intl Khmer-first); new API paths and schemas, the `field_reports` ERD entry, and refreshed test counts (126 shared, 45 backend, 37 bot).

### Changed

- `product-report.md` 1.3.0 → 1.4.0 — farmers are reached through relay people and Telegram is repositioned as a broadcast/relay surface; extension advisors enter as persona PER-004; officials' console and officer assistant serve PER-001/PER-004; Tier 3 adds photo-attached reports and Facebook posting and labels existing roadmap items with their `research/features-scan.md` ranks.
- `technical-report.md` 1.3.0 → 1.4.0 — architecture, API spec, ERD, ADRs, and traceability matrix brought level with the shipped stack; `WEB_BASE_URL` and the self-hosted digest cron documented.
- `README.md` — test counts refreshed (126 shared, 37 bot, 45 backend) and the self-hosted schedule notes the daily digest cron and `WEB_BASE_URL`.

## [0.5.0] — 2026-10-18

Blue-green deployment for the self-hosted `labyrinth.ts` stack, driven by a GitHub Actions pipeline that runs on every PR and merge. No package versions changed — this release is deployment infrastructure and docs only.

### Added

- `ci` — `.github/workflows/deploy.yml`: a PR to `main` builds the dashboard into a `pr-<n>` Firebase preview channel (URL commented on the PR) and rebuilds the API preview slot; a merge builds the idle API color, switches traffic to it, then builds the dashboard from main, deploys it to the channel named after the new color and promotes that channel to live. `workflow_dispatch` runs the same pipeline or a `rollback` (color flip, no rebuild). Fork PRs are skipped — they get no secrets. Two CLI facts the pipeline encodes: firebase-tools 15 has no `hosting:channel:release`, so promoting is `hosting:clone <site>:<color> <site>:live`; and channels default to a 7-day TTL, so both the PR channel (14d) and the color channels (30d, refreshed every merge) set one.
- `scripts` — `deploy_blue_green.sh`: build the idle color → health-check it on its loopback port (`/api/v1/health`) → rewrite the Caddyfile → `caddy reload`. Flags `--preview` (PR slot only), `--switch-only` (flip back, no rebuild) and `--status`; `flock` serializes concurrent deploys, a failed health check leaves the live color untouched and dumps the failed container's log tail.
- `deploy` — `caddy/Caddyfile`: the proxy the Cloudflare tunnel already targets (`http://localhost:8080`). Both API colors are upstreams with `lb_policy first` (active color listed first) and active health checks, so a dead active color fails over to the other one without a redeploy.

### Changed

- `deploy` — `docker-compose.server.yml`: the single `backend` service is now `backend-blue` (`127.0.0.1:8081`), `backend-green` (`127.0.0.1:8082`) and `backend-preview` (`127.0.0.1:8083`) from one shared `x-api` anchor, with `caddy` owning `:8080`. The bot waits on `db` instead of the API: it reads the database and the public audio URL, not the API service name.
- `docs` — README §5 documents the color slots, the workflow table, the four script flags, the repository secrets, and the one-time channel seed, plus the caveat that both colors share one database (schema changes must stay backward-compatible for the color still serving).

## [0.4.2] — 2026-10-18

TTS outages degrade to text instead of failing the request.

### Fixed

- `shared` — 0.3.2: `GeminiTTS.synthesize` converts any generation failure (quota 429, safety blocks, transient API errors) into `TTSUnavailable`, which the pipeline already treats as "deliver the text bulletin without audio". A live free-tier quota exhaustion (`429 … limit: 10, model: gemini-3.8-flash-tts`) was surfacing as `500 Internal server error` on `POST /api/v1/communes/{code}/assess` instead of the documented text-only fallback.

## [0.4.1] — 2026-10-18

Voice notes no longer read the announcer instructions aloud, and the assessment dialog opens above the map.

### Fixed

- `frontend` — 0.4.1: the assessment dialog opened from the basin map rendered underneath it. The backdrop sat at `z-index: 40` while Leaflet's panes reach 700, its controls 1000, and the basemap switcher 1100, so every map layer painted over the dialog. The backdrop now stacks at `z-index: 1200`, above all map layers.
- `shared` — 0.3.1: voice notes no longer open by reading their own delivery instructions aloud. `synth_tts_prompt()` sent the multi-sentence "You are a calm, respectful announcer…" preamble plus tone rules as part of the spoken text, and a live voice note read all of it before the bulletin. The TTS model has no developer-instruction channel (routing the text through `system_instruction` returns `400 Developer instruction is not enabled for this model`), so the prompt is now a single short colon-terminated style line ("Read this aloud in Khmer with a calm, reassuring tone…") followed by the bulletin only. Regression tests pin the prompt shape and assert no `system_instruction` is sent.

## [0.4.0] — 2026-10-18

The officials' console gets its Tier 3 read-path tools: a printable status summary, CSV export, alert dispatch log, and an interactive basin map.

### Added

- `frontend` — 0.4.0: printable basin status summary (`StatusSummary`) with tier counts, a station status table, the top-10 elevated communes, and a print/PDF layout; client-side CSV export of the risk register (`lib/csv.ts`) with a UTF-8 BOM so Excel reads Khmer names correctly; alert dispatch log (`AlertLog`) reading `GET /api/v1/alerts/log` with commune names, tier, directive, recipients, bulletin details, and voice-note links; Leaflet basin map with switchable Esri Light Gray, OpenStreetMap, and OpenTopoMap basemaps, canvas-rendered commune markers, and station diamonds.
- `backend` — 0.2.0: `GET /api/v1/alerts/log` — public, newest-first log of dispatched sentinel escalations with gazetteer-enriched commune names; `limit` defaults to 50 and clamps to 1..200.
- `shared` — 0.3.0: `Repository.recent_sentinel_alerts(limit)` implemented across the memory, PostgreSQL, and Firestore adapters (newest escalation first); the Postgres row mapping is shared with `last_sentinel_alert`.

### Changed

- `frontend` — the static SVG basin map is replaced by Leaflet. The console now requests basemap tiles from Esri, OpenStreetMap, or OpenTopoMap, so the "no external map provider" claim no longer holds; the commune and station overlays still render over the neutral canvas when tiles are slow or blocked. The default Light style uses Esri Light Gray because CARTO's keyless Positron endpoint now serves watermarked "API KEY REQUIRED" tiles. The now-unused SVG projection helper (`project()`) is removed from `lib/design.ts`.
- `docs` — product and technical reports 1.3.0: FR-10 and AC-08 cover the summary, CSV export, and alert log; the API spec includes `/api/v1/alerts/log`; the map stack and map claims match Leaflet and its tile providers; README test counts refreshed to 94 shared, 28 bot, 28 backend.

### Fixed

- `shared`, `backend`, `bot` — test settings are hermetic (`_env_file=None`). Running pytest from the `projects/` root previously loaded `.env` → `.env.staging`, so a real Gemini or Telegram key turned unit tests into live network calls: flaky failures when the provider rejected them, hangs when it was slow. All three suites now pass offline from any working directory.

## [0.3.3] — 2026-10-18

Stage-personalized push alerts, a read-only console fix, and the technical report brought level with the shipped stack.

### Added

- `shared` — 0.2.0: sentinel escalations now dispatch per stored stage. Subscribers are grouped by their subscription's rice stage and each group gets its own directive set; subscribers without a stored stage keep the conservative ripening default (INV-03). Covered by `test_escalation_personalizes_by_stored_stage`.
- `docs` — `research/features-scan.md`, `research/sellers-market.md`, `research/gov-workflow.md`: comparable-systems inventory with candidate features; Cambodian paddy-market evidence (buyer information gap; the public-signal design constraint); NCDM reporting chain plus the officials' console roadmap.

### Changed

- `bot` — 0.3.0: `make_telegram_dispatcher` accepts `post_to_channel` (default `true`; existing two-argument call sites unchanged); the sentinel sets it so the public channel receives exactly one post per commune escalation, carried on the ripening group.
- `frontend` — 0.3.1: the assessment dialog no longer offers crop-stage chips. The console is read-only (FR-10), so `api.assess()` omits `crop_stage` and the backend applies its conservative ripening default; the dead `CROP_STAGES` constant and `.crop-stage-row` rule are removed.
- `docs` — `technical-report.md` 1.1.0 → 1.2.0: aligned with the shipped stack and revised product report — `gemini-3.8-flash` + `gemini-3.8-flash-tts` (24 kHz PCM → MP3 via `lameenc`), zero-tile SVG/canvas console (Google Maps and Material Web claims removed), 15-minute scheduler, four-station roster including `019802` Kompong Cham, `TEST-SPA-01` corrected to `081001` (Khpob) with new `TEST-SPA-03`, agronomy fixture rewritten against the real `AgriDecisionEngine` API, ADR-0005 amended, deployment topology (Cloud Run target + current self-hosted demo with the Firebase console) stated, FR-10 added to the traceability matrix (10/10).
- `docs` — `product-report.md`: FR-10 Officials' Coordination Console added; sellers/traders scoped as public-signal-only beneficiaries with the documented ethics constraint; non-goals 7–8 added (no buyer feeds, no parallel damage pipeline); Tier 3 roadmap rebuilt from the three new research notes.

### Fixed

- `shared`, `bot` — sentinel escalations ignored each subscriber's stored rice stage (the patrol always assessed with `RIPENING`), so the push path did not match FR-09/AC-03's stage-aware promise. Push alerts now carry each subscriber's stage's directives; the public-channel post stays single and conservative.

## [0.3.2] — 2026-10-18

Product report 1.2.0 (audience split) plus sourced research notes for the AI Builder Cup submission.

### Added

- `docs` — `research/`: sourced research for the submission. `competition.md` (Google Cloud AI Builder Cup 2026 rules, themes, rubric, submission constraints, from primary sources), `landscape.md` (flood/agri advisory landscape and the hazard × stage × Khmer gap), `cambodia-context.md` (fact-check of the report's figures against institutional sources).
- `docs` — `product-report.md` §5 "Google Cloud AI Builder Cup 2026 alignment": theme mapping, rubric mapping (40/25/25/10), submission constraints checklist.

### Changed

- `docs` — `product-report.md` 1.1.0 → 1.2.0: audience split made explicit. Farmers are served only through the Telegram bot, where the rice-stage profile is asked once and stored on the subscription (FR-04/06/09, AC-01/07, JRN-03/04); the web dashboard is specified as a read-only officials' console (non-goal 5, AC-08, JRN-08/09), so no crop-stage prompt exists outside the bot.
- `docs` — `product-report.md`: claims corrected to match the shipped stack (zero-tile SVG basin map instead of Google Maps Platform; `gemini-3.8-flash` + `gemini-3.8-flash-tts` instead of Gemini 2.0 Flash; 15-minute scheduler; MFI CSV export marked Phase 2).
- `docs` — `product-report.md`: figures fact-checked and corrected (2022: 152,386 ha affected, 85,482 households; US$405–500/ha production cost instead of $400–700/ha "fertilizer and seed"; EWS 1294 ~118,000 subscribers; station `019803` → `033402` for Koh Khel; Koh Thom and Peam Chor corrected from communes to districts; stage default noted as season-aware).

## [0.3.1] — 2026-10-18

Self-hosted API: the dashboard stays on Firebase Hosting, but the API now runs on the `labyrinth.ts` server instead of a laptop tunnel.

### Added

- `scripts` — `docker-compose.server.yml`: API + dedicated PostgreSQL sidecar for the `labyrinth.ts` host. The port is published on loopback only (the host's existing Cloudflare tunnel is the sole ingress), `restart: unless-stopped` survives reboots, and a `bot` profile runs the optional Telegram poller.
- `scripts` — `server_sync.sh`: telemetry sync + sentinel patrol trigger for cron (`*/15 * * * *`), mirroring the two Cloud Scheduler jobs in `deploy_gcp.sh`.
- `docs` — self-hosted API section in `README.md` (rsync + compose, tunnel hostname `mekongpulse-api.labyrinth.buzz`, dashboard republish, bot profile).

### Changed

- `scripts` — public API moved from the ephemeral `trycloudflare.com` quick tunnel to `https://mekongpulse-api.labyrinth.buzz` (Cloudflare Tunnel on the server); the Firebase dashboard was republished against the new URL.

## [0.3.0] — 2026-10-17

Dashboard redesign: light "river lab" theme derived from the bytelabkh.com brand tokens.

### Changed

- `frontend` — 0.3.0: full visual rebuild. The Material 3 dark theme (navy/cyan on near-black) is replaced by a light system built on the Byte Lab palette: white paper, mist `#eef2f7` bands, navy `#213a63` for primary actions, sky `#0ea5e9` as the single accent, ink/slate text, hairline borders. IBM Plex Sans + IBM Plex Mono replace Roboto; Kantumruy Pro remains the Khmer fallback.
- `frontend` — new hero band stating the basin condition in plain language ("N communes in flood danger") with a risk-distribution bar and tier legend, replacing the duplicated basin-summary card.
- `frontend` — the Khmer voice bulletin now lives in a signature deep-navy panel on the dashboard and inside the assessment dialog.
- `frontend` — station selector chips are merged with the hydrograph card; emoji tier markers and glyph placeholders are replaced with drawn icons and colored dots.

### Fixed

- `frontend` — map, hydrograph canvas, badges, and dialogs all render against the new light tokens (dark-theme color values removed).

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
