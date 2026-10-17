---
id: REPORT-TECH-002
document_type: technical_report
title: MekongPulse Technical Architecture and Engineering Report
project_name: "MekongPulse"
version: 1.2.0
status: approved
last_updated: 2026-10-18
owners: ["@bytelab-lead", "@tech-lead", "@backend-lead"]
dependencies: ["REPORT-PROD-002", "REPORT-DSGN-002", "DESIGN.md"]
---

# Technical Report: MekongPulse

## 1. Technical Requirements Document (TRD)

### 1.1 Scope of engineering work

- **In-scope**:
  - Python 3.12 FastAPI microservice. Deployment-ready on Google Cloud Run in Singapore (`asia-southeast1`) via `deploy_gcp.sh`; the current public demo runs the same container image self-hosted via Docker Compose behind a Cloudflare tunnel, with the console on Firebase Hosting (see §9.1).
  - Google Cloud Agent Development Kit (ADK) multi-agent pipeline: Ingestion Agent, Spatial Reasoner, Agronomic Advisor, Khmer Vernacular Dispatcher.
  - Telemetry integration with Mekong River Commission (MRC) REST API (`api.mrcmekong.org`) for 4 permanent Cambodian stations: Prek Kdam (`020102`), Chaktomuk (`033401`), Koh Khel (`033402`), and Kompong Cham (`019802`).
  - Weather forecast integration with Open-Meteo API for 7-day hourly precipitation and 0–7cm soil moisture.
  - Spatial in-memory R-Tree index over the official 2025 MEF Cambodian administrative gazetteer (1,661 communes).
  - Gemini integration via the Gemini API: `gemini-3.8-flash` for Khmer bulletin polish and the ADK advisor; `gemini-3.8-flash-tts` for spoken Khmer audio (24 kHz PCM WAV transcoded to MP3 with `lameenc`; no system ffmpeg in the container).
  - Telegram Bot webhook processing for GPS location pin queries and automated broadcast dispatches.
  - Rice-stage profiles: the bot asks once per commune subscription (Khmer inline options), stores the stage on the subscription, and reuses it for every alert and advisory answer. Escalations are dispatched per stage group, so each subscriber receives their stage's directive set; the public channel receives a single post per escalation (conservative ripening posture). `/crop` changes the stage later; the web console is read-only and never collects per-farmer data.
  - Firestore for time-series observation snapshots, commune risk profiles, and alert history in production; PostgreSQL (asyncpg) in development, staging, and self-hosted modes; Cloud Storage for audio caching.
- **Deferred / out-of-scope**:
  - Custom physical river buoys or ultrasonic sensor hardware.
  - Heavy 2D hydrodynamic numerical fluid simulations.
  - SMS cellular telecommunication gateways.
  - Native mobile application binaries (iOS/Android app store packages).

### 1.2 Technology stack and tooling inventory

| Category                     | Technology / Library / SDK         | Pinned version    | Purpose in project                                                 |
| ---------------------------- | ---------------------------------- | ----------------- | ------------------------------------------------------------------ |
| Runtime & Language           | Python, CPython                    | 3.11-slim         | Core microservice execution and async runtime                      |
| Package & Tool Manager       | uv                                 | >= 0.5.0          | Sub-second deterministic dependency resolution and virtualenv sync |
| Web Framework                | FastAPI                            | 0.115.x           | High-throughput asynchronous HTTP API and webhook gateway          |
| ASGI Web Server              | Uvicorn (standard)                 | 0.32.x            | Production HTTP/1.1 server worker                                  |
| Schema & Settings Validation | Pydantic, pydantic-settings        | 2.10.x            | Request/response data validation and type enforcement              |
| Async HTTP Client            | HTTPX                              | 0.28.x            | Non-blocking telemetry ingestion client with connection pooling    |
| Spatial & Geometry Engine    | Shapely, Rtree / STRtree           | 2.0.x             | Sub-15ms in-memory spatial geocoding for 1,661 MEF communes        |
| AI Reasoning & Synthesis     | google-genai (Gemini API), google-adk (bot) | 1.x / 2.12.x      | `gemini-3.8-flash` bulletins & ADK advisor; `gemini-3.8-flash-tts` Khmer voice synthesis |
| Time-Series & State Store    | google-cloud-firestore             | 2.19.x            | Real-time observation snapshots and commune risk index             |
| Audio Object Storage         | google-cloud-storage               | 2.18.x            | Direct streaming upload and hosting for synthesized MP3 notes      |
| Secret Management            | google-cloud-secret-manager        | 2.20.x            | Zero-leak credential injection for Telegram and Gemini keys        |
| Task Scheduling              | Google Cloud Scheduler             | Managed           | Scheduled 15-minute HTTP cron triggers to `/api/v1/telemetry/sync` (mirrored by host cron when self-hosted) |
| Serverless Hosting           | Google Cloud Run + Firebase Hosting | Gen 2 (Singapore) | Auto-scaling API containers (`asia-southeast1`) + static dashboard on Firebase Hosting |
| Basin Map & Charts           | Hand-rolled React + SVG map, HTML5 canvas hydrographs | n/a | Zero-tile commune risk map and canvas hydrograph curves; no external map provider, API key, or tile requests |
| UI Framework                 | React 18 + hand-rolled CSS design tokens | 18.3.x      | Light "river lab" theme (navy `#213a63`, sky `#0ea5e9`), IBM Plex + Kantumruy Pro fonts; no external UI library |
| Design Tokens & UI Contract  | CSS custom properties + root `DESIGN.md` | v1.0         | Tokenized palette, type scale, and component states consumed across the console |
| Test Harness                 | Pytest, pytest-asyncio, pytest-cov | 8.3.x             | Deterministic unit and Given-When-Then integration tests           |

### 1.3 High-risk domains: Buy vs build policy

| High-risk domain                        | Why building from scratch fails                                                                                            | Standard vetted solution in MekongPulse                                                     |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **Secret management & API keys**        | Hardcoded env files in Git repositories leak API tokens; container layer leaks expose credentials in image registries.     | Google Cloud Secret Manager injected via Cloud Run runtime metadata (`--set-secrets`).      |
| **Object storage & audio delivery**     | Buffering multi-megabyte synthesized audio streams in memory crashes lightweight Cloud Run instances with OOM errors.      | Direct stream pipe to Google Cloud Storage (`google-cloud-storage`) with public CDN URLs.   |
| **Spoken Khmer speech synthesis**       | Hand-rolled phoneme synthesizers or rule-based TTS lack Khmer tone sandhi, honorifics, and dialect nuances.                | Google Gemini native TTS (`gemini-3.8-flash-tts`) with Khmer prompting; 24 kHz PCM transcoded to MP3 with `lameenc`. |
| **Spatial point-in-polygon resolution** | Iterating 1,661 commune polygon boundaries sequentially yields O(N) lookup times exceeding 450ms.                          | In-memory Shapely STRtree index over 2025 MEF gazetteer GeoJSON yielding < 15ms lookups.    |
| **Scheduled telemetry synchronization** | In-process `while True: await asyncio.sleep(900)` loops crash silently on unhandled exceptions and fail across instances. | Google Cloud Scheduler firing authenticated HTTP POST triggers to `/api/v1/telemetry/sync`. |
| **Webhook authentication**              | Blindly processing incoming webhooks leaves bots open to spoofed payload injection and replay attacks.                     | HMAC token verification via standard `X-Telegram-Bot-Api-Secret-Token` header validation.   |

### 1.4 SLA / SLO performance budgets

| Metric                                       | Target objective (SLO) | Degradation threshold (alert) | Measurement tool                       |
| -------------------------------------------- | ---------------------- | ----------------------------- | -------------------------------------- |
| Telegram Location Webhook Latency (p95)      | < 3,000ms              | > 5,000ms for 5 mins          | Cloud Run Request Latency Metric       |
| Telemetry Polling Execution (All 4 stations) | < 4,000ms              | > 10,000ms                    | Ingestion Worker Timer Metric          |
| Spoken Khmer Audio Synthesis Time            | < 2,200ms              | > 4,500ms                     | Gemini client span tracing             |
| Memory Footprint (per instance)              | < 600MB steady-state   | > 1.4GB (OOM warning)         | Cloud Run Container Memory Utilization |
| Spatial Gazette Geocoding Query              | < 15ms                 | > 50ms                        | In-Memory Shapely R-Tree Lookup Timer  |
| Cold-Start Response Time                     | < 1,500ms              | > 3,500ms                     | Cloud Monitoring Startup Latency       |

### 1.5 Security and authentication architecture

- **API and Webhook Security**: Telegram incoming updates enforce the `X-Telegram-Bot-Api-Secret-Token` header. Web dashboard REST APIs enforce CORS restricted to verified domains (`*.run.app` and localhost during development).
- **Secret Management**: Google Cloud Secret Manager manages credentials (`TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GCS_BUCKET_NAME`) in the Cloud Run path; development, staging, and self-hosted modes read the same names from the gitignored `.env` presets.
- **Data Protection**: User GPS coordinates and subscriber identifiers are anonymized via SHA-256 salting before persistent logging in Firestore. TLS 1.3 encryption is enforced in transit.
- **Access Control**: Public endpoints allow read-only telemetry queries; administrative broadcast triggers require IAM Bearer token authentication.

### 1.6 Observability and telemetry

- **Structured JSON Logging**: Standard Python logging emits JSON structured lines:
  ```json
  {
    "timestamp": "2026-10-16T02:00:00Z",
    "level": "INFO",
    "trace_id": "projects/bytelab/traces/8f1e2d3c",
    "event": "TELEGRAM_LOCATION_QUERY",
    "commune_code": "080404",
    "commune_name": "Kaoh Thum Ka",
    "risk_tier": "WARNING",
    "audio_generated": true,
    "duration_ms": 2420
  }
  ```
- **OpenTelemetry Tracing**: W3C `traceparent` context propagated across Cloud Run instances, background workers, and Gemini API calls.
- **Health Verification**: Exposes `/health` returning status `HEALTHY`, MRC station connectivity check, and Firestore connection state.

---

## 2. Software Design Document (SDD)

### 2.1 C4 container architecture

```mermaid
flowchart TD
  subgraph ClientChannels["Client Presentation Channels"]
    Telegram["Telegram Bot Client\n(Mobile Farmers & Commune Chiefs)"]
    WebDashboard["Officials' Console (Next.js 14,\nstatic export on Firebase Hosting)\n(Commune Chiefs, District Committees,\nCooperatives, Public - read-only)"]
  end

  subgraph IngressPlatform["Container Runtime\n(Cloud Run target / self-hosted Docker)"]
    FastAPIApp["FastAPI Gateway & Webhook Service\n(concurrency=80, min-instances=1)"]
  end

  subgraph MultiAgentEngine["Agent Application Services"]
    IngestAgent["Agent 1: Hydro-Telemetry Ingestor\n(MRC & Open-Meteo Poller)"]
    SpatialAgent["Agent 2: Spatial Inundation Reasoner\n(1,661 MEF Gazetteer Matcher)"]
    AgriAgent["Agent 3: Agronomic Decision Engine\n(Crop Calendar & Directives)"]
    VernacularAgent["Agent 4: Gemini Vernacular Dispatcher\n(Khmer Synthesis & Voice TTS)"]
  end

  subgraph GoogleCloudData["Google Cloud Managed Platform"]
    Firestore[("Cloud Firestore\n(Stations, Observations, Commune Risk)")]
    GCS[("Cloud Storage\n(Generated Khmer MP3 Voice Notes)")]
    Gemini["Google Gemini API\n(gemini-3.8-flash + gemini-3.8-flash-tts)"]
  end

  subgraph ExternalAPIs["External Telemetry & Forecasting"]
    MRC["Mekong River Commission API\n(Stations 020102, 033401, 033402, 019802)"]
    OpenMeteo["Open-Meteo Weather API\n(7-Day Rain & Soil Moisture)"]
  end

  Telegram -->|HTTPS POST /telegram/webhook| FastAPIApp
  WebDashboard -->|HTTPS GET /api/v1/*| FastAPIApp
  FastAPIApp --> IngestAgent
  FastAPIApp --> SpatialAgent
  FastAPIApp --> AgriAgent
  FastAPIApp --> VernacularAgent

  IngestAgent -->|Poll Every 15m| MRC
  IngestAgent -->|Query Forecast| OpenMeteo
  VernacularAgent -->|Inference & Speech| Gemini

  IngestAgent --> Firestore
  SpatialAgent --> Firestore
  VernacularAgent --> GCS
```

### 2.2 Dependency boundaries and directory layout

- **Inward dependency rule**: `Domain` core has zero external framework dependencies. `Application` imports `Domain`. `Infrastructure` and `Presentation` import `Application` and `Domain`.
- **Directory layout** (uv workspace under `projects/`):
  ```text
  projects/
  ├── shared/src/mekong_shared/    # Domain engine: models, MRC + Open-Meteo clients, SpatialRiskClassifier,
  │                                # AgriDecisionEngine, MekongSentinel, TTS, repositories (memory/Postgres/Firestore)
  ├── backend/src/mekong_backend/  # FastAPI gateway: routers/, deps.py, problems.py, app.py, main.py
  ├── bot/src/mekong_bot/          # Telegram service, dispatcher, PTB handlers, polling entrypoint
  ├── frontend/src/app/            # Next.js 14 read-only officials console, client-rendered
  └── scripts/                     # switch_env.sh, run_dev.sh, init_db.sh, deploy_gcp.sh, build_gazetteer.py
  ```

### 2.3 Failure modes and resilience

- **Adjacent station failover**: If Prek Kdam (`020102`) times out or returns HTTP 500, the ingestion service automatically falls back to Chaktomuk (`033401`) — or Koh Khel (`033402`) when Chaktomuk is also unavailable — applying an empirically derived hydraulic offset (median stage difference over the overlapping historical window, recomputed on every refresh; see `compute_hydraulic_offset`).
- **Gemini audio synthesis timeout**: The Telegram webhook never blocks on audio: location/share replies are text-only risk cards, and voice notes are attached only on the alert push path, so the webhook always responds within Telegram's deadline. When synthesis is unavailable, alerts degrade to text (audio is best-effort; text is always delivered).
- **Cold cache resilience**: The spatial gazetteer is bundled in the container image (`data/commune_gazetteer_2025.json`, ~0.8 MB centroids + DEM elevations, plus `data/raw/mef_commune_boundaries.geojson`, ~6.3 MB polygons), requiring zero external network calls during cold start.

---

## 3. Entity Relationship Diagrams (ERD) & Schema

### 3.1 Relational schema

```mermaid
erDiagram
  HYDRO_STATION ||--|{ HYDRO_OBSERVATION : records
  COMMUNE ||--o{ ALERT_DISPATCH : receives
  COMMUNE ||--o| WEATHER_FORECAST : forecasts
  HYDRO_STATION ||--o{ COMMUNE : influences
  COMMUNE ||--o{ COMMUNE_SUBSCRIPTION : subscribes
  COMMUNE ||--o{ SENTINEL_ALERT : triggers
  SENTINEL_PATROL_RUN ||--o{ SENTINEL_ALERT : records

  HYDRO_STATION {
    string id PK "020102|033401|033402|019802"
    string name
    string river_name
    float latitude
    float longitude
    float alarm_stage_m
    float flood_stage_m
    float zero_gauge_elevation_m
  }

  HYDRO_OBSERVATION {
    string id PK
    string station_id FK
    timestamp recorded_at
    float water_level_m
    float rate_of_rise_m_per_hr
    float rainfall_mm
    float temperature_c
    boolean is_stale_fallback
  }

  COMMUNE {
    string id PK "MEF 6-digit code (e.g. 080404)"
    string name_khmer
    string name_english
    string district_name
    string province_name
    float latitude
    float longitude
    float ground_elevation_m
    float levee_height_m
    string nearest_station_id FK
    string current_risk_tier "NORMAL|ADVISORY|WARNING|DANGER"
    int lead_time_hours
    timestamp updated_at
  }

  WEATHER_FORECAST {
    string id PK
    string commune_id FK, UK
    timestamp forecast_time
    float precipitation_48h_mm
    float soil_moisture_0_7cm_pct
    float runoff_potential_score
  }

  COMMUNE_SUBSCRIPTION {
    string id PK
    string telegram_chat_id
    string commune_id FK
    string crop_stage "TILLERING|VEGETATIVE|FLOWERING|RIPENING"
    timestamp subscribed_at
    timestamp last_notified_at
    string last_notified_risk_tier
  }

  SENTINEL_PATROL_RUN {
    string id PK
    timestamp run_at
    int stations_polled
    int communes_evaluated
    int alerts_dispatched_count
    int execution_duration_ms
  }

  SENTINEL_ALERT {
    string id PK
    string patrol_run_id FK
    string commune_id FK
    string station_id FK
    string risk_tier "NORMAL|ADVISORY|WARNING|DANGER"
    int lead_time_hours
    string directive_title
    text bulletin_text
    string audio_url
    timestamp dispatched_at
    int recipients_count
  }

  ALERT_DISPATCH {
    string id PK
    string commune_id FK
    string risk_tier "NORMAL|ADVISORY|WARNING|DANGER"
    string directive_type "HARVEST|FERTILIZER_HOLD|SLUICE_OPEN|MONITOR"
    text khmer_bulletin_text
    string audio_storage_uri
    int audio_duration_seconds
    int recipients_count
    timestamp dispatched_at
  }
```

### 3.2 Indexing strategy and partition keys

- `idx_observations_station_time`: Firestore composite index on `(station_id ASC, recorded_at DESC)` for 7-day hydrograph queries.
- `idx_communes_risk_province`: Firestore composite index on `(current_risk_tier ASC, province_name ASC)` for regional flood map filtering.
- `idx_alerts_commune_time`: Firestore composite index on `(commune_id ASC, dispatched_at DESC)` for alert deduplication and auditing.
- `spatial_rtree_communes`: In-memory R-Tree spatial index mapping latitude/longitude coordinates to MEF commune boundaries in <15ms.

---

## 4. API Specifications

### 4.1 OpenAPI 3.1 definitions

```yaml
openapi: 3.1.0
info:
  title: MekongPulse REST API
  description: OpenAPI 3.1.0 Specification for MekongPulse Autonomous Hydrological Telemetry & Agronomic Preservation Platform.
  version: 1.0.0
servers:
  - url: https://mekongpulse-backend-<hash>-as.a.run.app  # from `gcloud run services describe`; see §9.1
    description: Production Google Cloud Run (Singapore)
  - url: http://localhost:8080
    description: Local Development Environment

paths:
  /api/v1/health:
    get:
      summary: Liveness and Readiness Probe
      operationId: checkHealth
      responses:
        "200":
          description: Service is healthy.
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: "HEALTHY"
                  timestamp:
                    type: string
                    format: date-time
                  mrc_station_connection:
                    type: string
                    example: "CONNECTED"

  /api/v1/telemetry/latest:
    get:
      summary: Get latest cached telemetry across all monitored Mekong stations
      operationId: getLatestTelemetry
      responses:
        "200":
          description: Array of latest station readings.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/StationTelemetry"

  /api/v1/communes/risk-map:
    get:
      summary: Retrieve real-time inundation risk ratings for Cambodian communes
      operationId: getCommuneRiskMap
      parameters:
        - name: province
          in: query
          required: false
          schema:
            type: string
          example: "Kandal"
      responses:
        "200":
          description: List of commune risk profiles for map visualization.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/CommuneRiskProfile"

  /api/v1/communes/{commune_code}/assess:
    post:
      summary: Trigger on-demand hydrological & agronomic risk assessment
      operationId: assessCommuneRisk
      parameters:
        - name: commune_code
          in: path
          required: true
          schema:
            type: string
          example: "080404"
      requestBody:
        required: false
        content:
          application/json:
            schema:
              type: object
              properties:
                crop_stage:
                  type: string
                  description: >-
                    Rice stage for directive selection. Optional; defaults to RIPENING.
                    In production the value comes from the farmer's stored subscription
                    profile (set once in the Telegram bot); the read-only web console
                    never sends it.
                  enum: [TILLERING, VEGETATIVE, FLOWERING, RIPENING]
                  default: RIPENING
      responses:
        "200":
          description: Localized risk assessment and agronomic action directives.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/AssessmentResult"
        "404":
          $ref: "#/components/responses/NotFound"

  /api/v1/telegram/webhook:
    post:
      summary: Telegram Bot Webhook Endpoint
      operationId: handleTelegramUpdate
      parameters:
        - name: X-Telegram-Bot-Api-Secret-Token
          in: header
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
      responses:
        "200":
          description: Update processed successfully.

components:
  schemas:
    StationTelemetry:
      type: object
      required:
        [
          station_id,
          station_name,
          water_level_m,
          rate_of_rise_m_per_hr,
          alarm_stage_m,
          recorded_at,
        ]
      properties:
        station_id:
          type: string
          example: "033402"
        station_name:
          type: string
          example: "Koh Khel"
        river_name:
          type: string
          example: "Bassac River"
        water_level_m:
          type: number
          format: float
          example: 7.62
        rate_of_rise_m_per_hr:
          type: number
          format: float
          example: 0.07
        alarm_stage_m:
          type: number
          format: float
          example: 7.50
        flood_stage_m:
          type: number
          format: float
          example: 7.90
        recorded_at:
          type: string
          format: date-time

    CommuneRiskProfile:
      type: object
      required:
        [
          commune_code,
          commune_name_khmer,
          commune_name_english,
          risk_tier,
          lead_time_hours,
        ]
      properties:
        commune_code:
          type: string
          example: "080404"
        commune_name_khmer:
          type: string
          example: "កោះធំ ក"
        commune_name_english:
          type: string
          example: "Kaoh Thum Ka"
        province:
          type: string
          example: "Kandal"
        risk_tier:
          type: string
          enum: [NORMAL, ADVISORY, WARNING, DANGER]
          example: "WARNING"
        lead_time_hours:
          type: integer
          example: 38

    AssessmentResult:
      type: object
      required: [commune_code, risk_tier, directive, khmer_bulletin]
      properties:
        commune_code:
          type: string
          example: "080404"
        risk_tier:
          type: string
          enum: [NORMAL, ADVISORY, WARNING, DANGER]
        lead_time_hours:
          type: integer
          example: 38
        directive:
          type: string
          example: "EMERGENCY_HARVEST_ACCELERATION"
        khmer_bulletin:
          type: string
        audio_url:
          type: string
          format: uri
          nullable: true

    ProblemDetails:
      type: object
      required: [type, title, status, detail]
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string

  responses:
    NotFound:
      description: The requested resource was not found.
      content:
        application/problem+json:
          schema:
            $ref: "#/components/schemas/ProblemDetails"
```

---

## 5. Test Plans and Test Cases

### 5.1 Deterministic test matrix

| Test ID       | Module / Unit          | Given                               | When                        | Then                                                 | Priority |
| ------------- | ---------------------- | ----------------------------------- | --------------------------- | ---------------------------------------------------- | -------- |
| `TEST-HYD-01` | `MRCTelemetryClient`   | Station `020102` online             | `poll_station("020102")`    | Returns valid float water level and timestamp        | P0       |
| `TEST-HYD-02` | `MRCTelemetryClient`   | Station `020102` returns HTTP 500   | `poll_station("020102")`    | Fails over to `033401` with `is_stale_fallback=True` | P0       |
| `TEST-SPA-01` | `SpatialReasoner`      | GPS `(11.266, 105.033)` (Kandal; 2025 MEF boundary) | `resolve_commune(lat, lng)` | Returns commune `081001` (Khpob, S'ang) via polygon resolution; < 15ms typical | P0 |
| `TEST-SPA-02` | `SpatialReasoner`      | GPS `(14.058, 108.277)` in Vietnam  | `resolve_commune(lat, lng)` | Raises `OutsideBasinError` with 422 ProblemDetails   | P1       |
| `TEST-SPA-03` | `Gazetteer.search`     | Query "Koh Thom" (2025 MEF spelling "Kaoh Thum") | `search_commune(name)` | Returns `080404`/`080405` (Kaoh Thum Ka/Kha), all in district "Kaoh Thum" | P1 |
| `TEST-AGR-01` | `AgriDecisionEngine`   | Risk `WARNING`, Crop `RIPENING`     | `evaluate_directives()`     | Returns `EMERGENCY_HARVEST_ACCELERATION`             | P0       |
| `TEST-AGR-02` | `AgriDecisionEngine`   | Rain `> 50mm`, Crop `VEGETATIVE`    | `evaluate_directives()`     | Returns `HOLD_CHEMICAL_FERTILIZER`                   | P0       |
| `TEST-DIS-01` | `VernacularDispatcher` | Valid directive parameters          | `synthesize_khmer_voice()`  | Produces valid MP3 stream (duration 30–60s)          | P1       |

Drift correction: the v1.1.0 draft expected `TEST-SPA-01` to resolve to `080402` ("Koh Thom"); the 2025 MEF boundary is the source of truth, the point is inside `081001` (Khpob, S'ang), and `080402` is Kampong Kong. See `shared/tests/test_spatial.py`.

### 5.2 Given-When-Then test fixtures

```python
from mekong_shared.agronomy import AgriDecisionEngine, primary_directive
from mekong_shared.models import CropStage, RiskTier, Urgency

def test_emergency_harvest_directive_for_ripening_rice():
    # Given
    engine = AgriDecisionEngine()

    # When
    directives = engine.evaluate(RiskTier.WARNING, CropStage.RIPENING, lead_time_hours=38)

    # Then
    primary = primary_directive(directives)
    assert primary.action_code == "EMERGENCY_HARVEST_ACCELERATION"
    assert "ប្រមូលផល" in primary.instruction_kh
    assert primary.urgency is Urgency.HIGH

def test_fertilizer_hold_during_heavy_rain_forecast():
    # Given: 65mm of rain forecast within 48h over vegetative rice
    engine = AgriDecisionEngine()

    # When
    directives = engine.evaluate(RiskTier.ADVISORY, CropStage.VEGETATIVE, rain_48h_mm=65.0)

    # Then
    hold = next(d for d in directives if d.action_code == "HOLD_CHEMICAL_FERTILIZER")
    assert "ផ្អាកការបាចជី" in hold.instruction_kh
    assert hold.urgency is Urgency.MEDIUM  # ADVISORY tier
```

---

## 6. Architectural Decision Records (ADRs)

### ADR-0001: Open Hydrological Telemetry vs. Custom Physical River IoT Sensors

- **Status**: Accepted
- **Context**: MekongPulse requires real-time river elevations and rise rates across Cambodian river basins. We considered building custom ultrasonic/radar IoT sensor buoys vs. consuming verified public telemetry APIs from the Mekong River Commission (MRC).
- **Decision**: Consume public MRC Telemetry APIs (`api.mrcmekong.org`).
- **Consequences**:
  - _Positive_: Eliminates $250k+ in sensor manufacturing, deployment permits, and solar battery maintenance. Zero risk of monsoon debris washing away buoys. Permanent calibrated stations.
  - _Negative_: Dependent on MRC endpoint availability (mitigated with adjacent station failover and local Firestore caching).

### ADR-0002: Multi-Agent Architecture (Google ADK) vs. Monolithic Procedural Backend

- **Status**: Accepted
- **Context**: System orchestrates distinct domains: hydro-telemetry polling, spatial geocoding, agronomic rules, and Khmer voice synthesis.
- **Decision**: Adopt Google Cloud Agent Development Kit (ADK) multi-agent architecture with 4 specialized agents.
- **Consequences**:
  - _Positive_: Clean separation of concerns. Robust unit testability for individual agents. Aligns with Google Cloud hackathon criteria.
  - _Negative_: Modest orchestration abstraction overhead compared to a single procedural script.

### ADR-0003: Telegram Bot & Voice Notes vs. Standalone Mobile App

- **Status**: Accepted
- **Context**: Choosing the primary delivery mechanism for rural commune leaders and smallholder farmers.
- **Decision**: Deliver via Telegram Bot (`@MekongPulseBot`) using interactive cards and spoken Khmer voice notes.
- **Consequences**:
  - _Positive_: Zero installation friction (Telegram is ubiquitously installed in Cambodian rural administration). Audio voice notes completely eliminate literacy barriers.
  - _Negative_: Constrained to Telegram's UI button and card rendering capabilities.

### ADR-0004: In-Memory Spatial R-Tree Index vs. Heavy PostGIS Database

- **Status**: Accepted
- **Context**: Resolving user GPS coordinates to one of 1,661 Cambodian administrative communes.
- **Decision**: Load 2025 MEF gazetteer GeoJSON into an in-memory Shapely R-Tree spatial index.
- **Consequences**:
  - _Positive_: Sub-15ms spatial point-in-polygon resolution. Zero PostGIS container hosting costs. Total dataset is < 10 MB RAM.
  - _Negative_: Adds ~1.2s of GeoJSON parsing during container startup.

### ADR-0005: Gemini Native TTS (gemini-3.8-flash-tts) + lameenc vs. External Specialized TTS

- **Status**: Accepted (amended)
- **Context**: Generating natural spoken Khmer alerts for rural farmers. The original draft assumed Gemini 2.0 Flash multimodal synthesis; that model cannot emit audio, and 2.5-era Gemini TTS lacked Khmer support. The verified Khmer-capable path is `gemini-3.8-flash-tts`.
- **Decision**: Use Google Gemini native TTS (`gemini-3.8-flash-tts`) via the Gemini API (API-key path; Vertex AI remains supported by the client when `USE_VERTEX_AI=true`). The model returns 24 kHz PCM WAV, which the service transcodes to MP3 with `lameenc` bindings, avoiding a system ffmpeg dependency in the container.
- **Consequences**:
  - _Positive_: Unified SDK and billing for Khmer reasoning and audio synthesis. Culturally respectful honorifics and correct agricultural vocabulary. No system codec dependency in the runtime image.
  - _Negative_: Audio generation takes 1.8–2.2 seconds round-trip; `lameenc` is a pinned native wheel carried per target platform.

### ADR-0006: Battle-Tested Managed Cloud Services vs. Hand-Rolling High-Risk Domains

- **Status**: Accepted
- **Context**: Critical project areas (credential management, audio object storage, scheduled background polling, and Khmer voice synthesis) require high reliability under a 48-hour build schedule.
- **Decision**: Adopt Google Cloud managed services (Secret Manager, Cloud Storage, Cloud Scheduler) and battle-tested standard libraries (Shapely, HTTPX, Pydantic) instead of rolling custom background daemons or hand-crafted security mechanisms.
- **Consequences**:
  - _Positive_: Eliminates credential leaks, prevents container memory exhaustion from audio buffering, guarantees reliable 15-minute polling triggers, and keeps total codebase focused strictly on core domain logic (hydrology, agronomy, and spatial reasoners).
  - _Negative_: Introduces dependency on Google Cloud IAM and service APIs.

---

## 7. Tech Spikes and Team Readiness

### 7.1 Spike sandbox code

- **Location**: `scratch/spike_[topic].py` (< 30 lines each).

#### Spike 1: Live MRC River Telemetry Poller

```python
# File: scratch/spike_mrc_poll.py
import httpx

STATION_PREK_KDAM = "020102"
url = f"https://api.mrcmekong.org/api/v1/time-series/telemetry/recent/measurement/{STATION_PREK_KDAM}"

with httpx.Client(timeout=10.0) as client:
    resp = client.get(url)
    assert resp.status_code == 200, f"MRC API failed: {resp.status_code}"
    data = resp.json()
    assert len(data) > 0, "Empty observations array"
    latest = data[0]
    print(f"Spike PASSED: Prek Kdam water level = {latest.get('w')}m at {latest.get('d')}")
```

#### Spike 2: Open-Meteo 7-Day Rainfall Forecast

```python
# File: scratch/spike_weather_forecast.py
import httpx

# Demo point in Kandal: 11.266° N, 105.033° E (2025 MEF boundaries place it in Khpob commune, S'ang district)
url = "https://api.open-meteo.com/v1/forecast?latitude=11.266&longitude=105.033&hourly=precipitation,soil_moisture_0_to_7cm&timezone=Asia%2FPhnom_Penh"

with httpx.Client(timeout=10.0) as client:
    resp = client.get(url)
    assert resp.status_code == 200, f"Open-Meteo failed: {resp.status_code}"
    hourly = resp.json()["hourly"]
    precip_48h = sum(hourly["precipitation"][:48])
    print(f"Spike PASSED: 48h Rain = {precip_48h:.1f}mm, Soil Saturation = {hourly['soil_moisture_0_to_7cm'][0]:.2f}")
```

### 7.2 Definition of Ready (DoR) checklist

- [x] Python 3.12 runtime verified (uv workspace; `python:3.12-slim` in container images).
- [x] Single-command local server boot verified (`cd projects/backend && uv run uvicorn mekong_backend.main:app --port 8080`; orchestrated by `./projects/scripts/run_dev.sh`).
- [x] Verified live connectivity to MRC endpoint `api.mrcmekong.org` (HTTP 200; all 4 stations polled and persisted).
- [x] Live `TELEGRAM_BOT_TOKEN` / `GEMINI_API_KEY` wired through the gitignored `.env` presets; the bot, Gemini bulletin polish, and TTS voice notes verified live.
- [x] 2025 MEF Cambodian administrative commune gazetteer built to `data/commune_gazetteer_2025.json` (1,661 communes with centroids + DEM elevations via `scripts/build_gazetteer.py`).
- [ ] Cloud Run live deployment pending a GCP billing account; `deploy_gcp.sh` dry-run verified end-to-end, and the current public demo runs the same image self-hosted (Docker Compose + Cloudflare tunnel) with the console on Firebase Hosting.

---

## 8. Milestone Mentorship & Vertical Slices

### 8.1 Milestone plan

- **Milestone 1: The Walking Skeleton (Hours 0–12)**
  - Scope: End-to-end slice connecting live MRC water polling, mock GPS webhook, basic threshold comparison, and Telegram bot text reply (`"Prek Kdam water level is 6.42m. Risk: Normal"`).
  - Verification: Automated integration tests (`shared/tests/test_mrc.py`, `shared/tests/test_pipeline_assess.py`, `backend/tests/test_health.py`) pass end-to-end.
- **Milestone 2: Spatial Inundation & Agronomic Directive Engine (Hours 12–24)**
  - Scope: Ingestion of all 4 Cambodian stations, Open-Meteo rain forecast, 1,661 commune R-Tree index, and `AgriDecisionEngine` directives.
  - Verification: Replay test with 2022 Kandal flood telemetry data confirming accurate risk tiering.
- **Milestone 3: Vernacular Khmer Speech & Console Dashboard (Hours 24–36)**
  - Scope: Gemini TTS (`gemini-3.8-flash-tts`) spoken Khmer audio generation, Telegram voice note delivery, and the zero-tile SVG risk console.
  - Verification: Automated probe asserting valid MP3 audio stream and < 2.5s synthesis time.
- **Milestone 4: Production Hardening & Cloud Run Deployment (Hours 36–48)**
  - Scope: Google Cloud Run deployment (`asia-southeast1`), Cloud Scheduler 15-min polling cron, Secret Manager integration, and station failover testing.
  - Verification: Smoke test on production URL verifying `/health` and webhook response time < 3.0s.

### 8.2 Scope Swap Rule protocol

1. Any newly requested hackathon feature is evaluated against the 4-milestone plan.
2. If non-essential to the primary judging demo, it is moved to the **Phase 2 Backlog** and rejected for the hackathon release.
3. If an essential modification is approved, an equivalent scope item from Milestone 3 or 4 MUST be swapped out to guarantee on-time deployment.

### 8.3 Milestone 5: Google ADK Agentic Architecture (Sentinel & ReAct Advisor)

- **Slice 5.1: Domain Tool Registry (`projects/shared`)**
  - Implement native Google ADK tools wrapping existing telemetry, spatial reasoner, agronomic engine, and voice synthesis.
  - Expose `get_station_telemetry(station_id)`, `resolve_commune_by_location(lat, lng)`, `search_commune(name)`, `evaluate_crop_directive(commune_id, crop_stage)`, and `synthesize_voice_bulletin(commune_id)`.
  - Verification: Unit tests in `test_adk_tools.py` executing tools via mock and live telemetry.
- **Slice 5.2: PostgreSQL Schema Migrations & Subscription Store (`projects/backend` & `shared`)**
  - Create tables `commune_subscriptions`, `sentinel_patrol_runs`, and `sentinel_alerts` in existing PostgreSQL container `pg_db`.
  - Implement async CRUD repository for Telegram chat subscriptions and alert deduplication.
  - Verification: Integration tests asserting subscription creation and deduplication query performance.
- **Slice 5.3: MekongAdvisor Conversational ReAct Agent (`projects/bot`)**
  - Integrate Google ADK `Agent` with `gemini-3.8-flash` in `projects/bot`.
  - Maintain multi-turn conversational session context per Telegram chat ID in PostgreSQL.
  - Support natural language Khmer/English dialogue, multi-step tool execution, and voice synthesis on demand.
  - Verification: Automated chat test verifying multi-turn tool-calling and response generation.
- **Slice 5.4: MekongSentinel Autonomous Patrol Daemon (`projects/backend` or standalone worker)**
  - Implement background patrol task running every 15 minutes.
  - Detect risk tier transitions (`NORMAL -> WARNING/DANGER`), flash surges, or lead time gates (< 36 hours).
  - Enforce 6-hour debounce cooldown per commune.
  - Autonomously trigger Gemini voice note generation and dispatch to subscribed Telegram users and public channel.
  - Verification: Patrol simulation test triggering alert on synthetic water surge with debounce validation.

---

## 9. System Runbooks and Playbooks

### 9.1 Local and production boot commands

```bash
# Local development boot (from the repository root)
./projects/scripts/switch_env.sh development   # point projects/.env at the dev preset
./projects/scripts/run_dev.sh                  # backend :8080 + frontend :3000 (add --bot for polling)

# Production deployment (DRY-RUN BY DEFAULT; prints every gcloud command)
./projects/scripts/deploy_gcp.sh               # review the plan
DRY_RUN=0 ./projects/scripts/deploy_gcp.sh     # execute: Artifact Registry + Cloud Build, Cloud Run
                                               # (mekongpulse-backend), Cloud Scheduler
                                               # (15-min sync + sentinel patrol), Secret Manager,
                                               # Telegram webhook registration, then the dashboard
                                               # -> Firebase Hosting via deploy_web_firebase.sh

# Dashboard-only redeploy (e.g. after the backend URL changes)
DRY_RUN=0 ./projects/scripts/deploy_web_firebase.sh https://<backend-url>
```

The deploy script reads `projects/.env.production` directly (it never mutates the active `.env` symlink), requires the secret values to be present in that preset, and prompts nothing. The web dashboard ships as a static export (`NEXT_OUTPUT=export`, built against the deployed backend URL) to the Firebase Hosting site named by `FIREBASE_PROJECT` — `https://ai-builder-cup-9f8cd.web.app`.

The current public demo does not run on Cloud Run. The API container runs self-hosted on the `labyrinth.ts` host via `projects/docker-compose.server.yml` behind that host's Cloudflare tunnel (`https://mekongpulse-api.labyrinth.buzz`), with `projects/scripts/server_sync.sh` on a 15-minute host cron standing in for Cloud Scheduler, and the Firebase console republished against the tunnel URL. The Cloud Run path above remains the deployment target when GCP billing is enabled.

### 9.2 Health verification

```bash
# Local
curl -sf http://localhost:8080/api/v1/health | grep '"status":"HEALTHY"'
curl -sf http://localhost:8080/api/v1/telemetry/latest | jq .

# Cloud Run (URL via: gcloud run services describe mekongpulse-backend \
#   --region asia-southeast1 --format='value(status.url)')
curl -sf "$BACKEND_URL/api/v1/health" | grep '"status":"HEALTHY"'

# Firebase Hosting dashboard (static export)
curl -sf https://ai-builder-cup-9f8cd.web.app/ | grep -q "MekongPulse" && echo "web OK"

# Self-hosted public API behind the Cloudflare tunnel (current demo path)
curl -sf https://mekongpulse-api.labyrinth.buzz/api/v1/health | grep '"status":"HEALTHY"'
```

### 9.3 Incident playbook: Upstream MRC station endpoint outage

- **Severity**: P2
- **Trigger**: An individual MRC station returns HTTP 404 or 500 during scheduled polling.
- **Mitigation procedure**:
  1. Inspect station health logs in Cloud Logging:
     ```bash
     gcloud logging read 'resource.type="cloud_run_revision" AND textPayload=~"MRC_STATION_TIMEOUT"' --limit 10
     ```
  2. Verify fallback station status directly:
     ```bash
     curl -sf https://api.mrcmekong.org/api/v1/time-series/telemetry/recent/measurement/033401 | jq '.[0]'
     ```
  3. Trigger manual synchronization with forced fallback:
     ```bash
     curl -X POST "http://localhost:8080/api/v1/telemetry/sync?force_fallback=true"   # local/dev
     curl -X POST "$BACKEND_URL/api/v1/telemetry/sync?force_fallback=true" \
       -H "Authorization: Bearer $ADMIN_TOKEN"                                       # Cloud Run (admin-gated)
     ```
  4. If all MRC endpoints are unreachable, the pipeline serves the last persisted readings, marks them `estimated` (`is_stale_fallback`, `FALLBACK_USED`/`CACHE_USED` warnings) and escalates conservatively per INV-03. No action required; inspect `warnings[]` in the sync response.

---

## 10. Spec-Verification and Drift Audit

### 10.1 Executive compliance scorecard

| Category                          | Pass / Fail |  Checked Items   | Violations Found | Notes                                                     |
| --------------------------------- | :---------: | :--------------: | :--------------: | --------------------------------------------------------- |
| Functional Requirements (PRD/SRS) |  **PASS**   |     10 / 10      |        0         | FR-01..09 verified with Gherkin; FR-10 by smoke check + demo checklist |
| Technology Stack & Tooling        |  **PASS**   |  17 components   |        0         | Google ADK (2.12.0), gemini-3.8-flash + gemini-3.8-flash-tts, asyncpg verified |
| High-Risk Domain Buy vs Build     |  **PASS**   |    6 domains     |        0         | Secret Manager, GCS, Cloud Scheduler, STRtree enforced    |
| API Contract Compliance (OpenAPI) |  **PASS**   |     6 routes     |        0         | Validated OpenAPI 3.1.0 schema with Subscriptions & Patrol|
| Database Schema Alignment (ERD)   |  **PASS**   |    7 entities    |        0         | PostgreSQL & Firestore subscriptions, sentinel runs/alerts|
| Design Tokens & UI Contract       |  **PASS**   | brand token set  |        0         | Light theme tokens in `globals.css`; no external UI library |
| System Invariants Compliance      |  **PASS**   |   4 invariants   |        0         | Grounded telemetry and zero-hardware invariant confirmed  |
| Scope Creep & Phantom Code        |  **PASS**   | 0 unspec'd items |        0         | Heavy 2D numerical hydrodynamic simulation deferred       |

### 10.2 Requirement cross-reference matrix

| Requirement ID  | Spec Document | Target Route / Function         | Implementation File Target                                  | Verification Test                                        |  Status  |
| --------------- | ------------- | ------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------- | :------: |
| FR-01 / ING-001 | PRD / SRS     | `mrc.poll_mrc_telemetry`        | `shared/src/mekong_shared/mrc.py`                           | `shared/tests/test_mrc.py`                               | **PASS** |
| FR-02 / ING-004 | PRD / SRS     | `OpenMeteoClient.fetch_forecast`| `shared/src/mekong_shared/weather.py`                       | `shared/tests/test_weather.py`                           | **PASS** |
| FR-03 / RSK-001 | PRD / SRS     | `SpatialRiskClassifier.classify`| `shared/src/mekong_shared/risk.py`                          | `shared/tests/test_risk.py`, `test_spatial.py`           | **PASS** |
| FR-04 / AGR-001 | PRD / SRS     | `evaluate_agronomic_directives` | `shared/src/mekong_shared/agronomy.py`                      | `shared/tests/test_agronomy.py`                          | **PASS** |
| FR-05 / DIS-001 | PRD / SRS     | `synthesize_khmer_voice`        | `shared/src/mekong_shared/tts.py`, `bulletin.py`            | `shared/tests/test_tts.py`, `test_bulletin.py`           | **PASS** |
| FR-06           | PRD           | `POST /api/v1/telegram/webhook` | `backend/src/mekong_backend/routers/telegram.py`            | `backend/tests/test_telegram_webhook.py`                 | **PASS** |
| FR-07           | PRD / SRS     | `MekongSentinel Background`     | `shared/src/mekong_shared/sentinel.py`, backend `patrol.py` | `shared/tests/test_sentinel.py`, `backend/tests/test_patrol_api.py` | **PASS** |
| FR-08           | PRD / SRS     | `MekongAdvisor ReAct Agent`     | `shared/src/mekong_shared/adk_agent.py`, `mekong_bot/`      | `shared/tests/test_advisor.py`                           | **PASS** |
| FR-09           | PRD / SRS     | `Commune Subscriptions Store`   | `backend/src/mekong_backend/routers/subscriptions.py`       | `backend/tests/test_subscriptions_api.py`                | **PASS** |
| FR-10           | PRD           | Read-only officials console     | `frontend/src/app/page.tsx`, `components/BasinMap.tsx`, `RiskList.tsx`, `VoicePlayer.tsx` | Firebase smoke check (`curl` grep) + demo checklist      | **PASS** |
| INV-01          | SRS           | Grounded telemetry verification | `shared/src/mekong_shared/mrc.py`                           | `shared/tests/test_mrc.py`                               | **PASS** |
| INV-02          | SRS           | Fail-safe station fallback      | `shared/src/mekong_shared/mrc.py`, `pipeline.py`            | `shared/tests/test_failover.py`                          | **PASS** |

### 10.3 Discrepancies and audit findings

1. **Telegram Audio Format Compatibility**: Telegram clients on older Android devices fail to render `.ogg` Opus audio notes unless properly formatted with specific container flags.
   - _Mitigation_: Gemini TTS returns 24 kHz PCM WAV; the service transcodes every bulletin to standard `.mp3` (`lameenc`) with MIME type `audio/mpeg`, so no Opus container flags are involved.
2. **Station Inundation Lag**: Upstream river flood crests take approximately 18–36 hours to travel from Kampong Cham (`019802`) to Chaktomuk / Bassac (`033401`).
   - _Mitigation_: Built hydraulic wave travel time equations into `SpatialRiskClassifier` to calculate accurate arrival windows.
