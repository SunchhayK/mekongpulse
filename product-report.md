---
id: REPORT-PROD-002
document_type: product_report
title: MekongPulse Product Specification Report
project_name: "MekongPulse"
version: 1.1.0
status: approved
last_updated: 2026-10-16
owners: ["@bytelab-lead", "@tech-lead", "@product-manager"]
profile: "Enterprise"
---

# Product Report: MekongPulse

## 1. Lean Canvas

### 1.1 Problem statements

1. **Unactionable Hydrological Telemetry**: The Mekong River Commission (MRC) and MOWRAM publish raw water elevations (e.g. "Prek Kdam at 6.33m") that rural commune leaders and farmers cannot translate into field-level flood arrival timing or crop danger. Impact: In 2022, 140,000 ha of Cambodian farmland submerged; smallholders lost $400–$700/ha in sunk fertilizer and seed costs.
2. **The Last-Mile Warning Gap**: Existing civic alert systems (e.g. EWS 1294) provide generic evacuation warnings (_"Move cattle to high ground"_), but offer zero agronomic guidance. Impact: Farmers fail to accelerate harvests or mistakenly apply $150/ha chemical fertilizer 24 hours before river flood surges wash 100% of it away.
3. **Microfinance Debt Collateral Default**: Smallholders pledge land titles (_Bann Dei_) for agricultural inputs; flood crop losses cause loan default, structural poverty, and forced migration to urban garment factories or cross-border labor.

#### Existing alternatives

- Official EWS 1294 IVR telephone voice calls (covers only 500k registered users; strictly civic evacuation notices).
- MOWRAM Facebook text bulletins (unstructured PDF images; inaccessible to low-literacy farmers).
- Informal word-of-mouth warnings from upstream fishermen (uncalibrated, late).

### 1.2 Customer segments

- **Target persona IDs**: [PER-001, PER-002, PER-003]
- **Primary audience**: Commune Chiefs (_Mekhum_), Village Disaster Management Groups (VDMGs), and smallholder rice farmers across flood-prone lowlands in Kandal, Kampong Cham, Prey Veng, and Battambang.
- **Secondary audience**: Agricultural Cooperatives (ACs) and contract-farming exporters (e.g. AMRU Rice) needing to schedule harvesting combines ahead of regional flood surges.
- **Tertiary audience**: Microfinance Institutions (Amret, Sathapana, Prasac) needing predictive crop climate risk feeds for portfolio risk hedging.
- **Early adopters**: 30 high-vulnerability communes along the Tonle Sap and Bassac flood corridors (e.g. Koh Thom, Peam Chor, Moung Ruessei).

### 1.3 Unique value proposition (UVP)

- **Core pitch**: Bridging Google Flood Hub's last-mile delivery gap by converting unauthenticated public river telemetry into hyper-local, stage-specific crop preservation directives delivered via Telegram and natural spoken Khmer voice notes.
- **Analogy**: "An AI meteorologist and agronomist in every Cambodian commune chief's pocket."

### 1.4 Proposed solution

1. **Autonomous Hydro-Meteorological Ingestion Loop**: Continuously polls live 15-minute water levels, rates of rise, and temperature from key MRC stations (`020102` Prek Kdam, `033401` Chaktomuk, `019803` Koh Khel) combined with Open-Meteo 7-day precipitation forecasts.
2. **Spatial Elevation Inundation Reasoner**: Maps gauge surge velocities against the 2025 MEF administrative gazetteer (1,661 communes) to calculate time-to-inundation and assign 4 standardized risk tiers (Normal, Advisory, Warning, Danger).
3. **Stage-Specific Agronomic Directives**: Evaluates rice maturity to issue actionable field commands: emergency combine mobilization (ripening stage) vs chemical fertilizer application hold (vegetative stage).
4. **Vernacular Spoken Khmer Audio**: Gemini 2.0 Flash synthesizes respectful Khmer language voice notes directly playable on low-cost smartphones without reading barriers.

### 1.5 Channels and delivery

- **Inbound**: Interactive Telegram Bot (`@MekongPulseBot`) responding to live location pins and commune searches within 3.0 seconds.
- **Outbound**: Automated daily hazard broadcasts to Commune Disaster Management Committee (CDMC) Telegram groups and village loudspeaker coordination feeds.
- **Web Dashboard**: Responsive Google Maps Platform geospatial dashboard showing real-time river hydrographs and commune vulnerability tiers.

### 1.6 Financial model

- **Revenue model**:
  - B2G & NGO Resilience Licensing: $500/year per district disaster committee for automated high-priority SMS/voice broadcasting.
  - Commercial Cooperative Subscription: $20/month per agricultural cooperative for combine harvest coordination feeds.
  - Microfinance Anticipatory Underwriting API: $1.50 per query assessing harvest climate risk for microloan originations.
- **Fixed infrastructure costs**: Google Cloud Run (min-instances=1) ~$15/month; Google Cloud Storage & Firestore ~$5/month.
- **Variable costs**: Gemini 2.0 Flash Khmer localization & audio generation ~$0.08 per 1,000 alerts; external APIs $0.00 (MRC and Open-Meteo open APIs are free). Marginal cost per commune alert batch < $0.002 USD.

### 1.7 Key metrics (OKRs)

- **North Star metric**: Hectares of standing rice protected through proactive harvest acceleration or fertilizer postponement.
- **Baseline**: 0 (New project kickoff).
- **Target (90 days)**: 2,500 hectares protected across 30 active early-adopter communes.
- **Secondary technical metrics**: Warning lead time: 36 to 72 hours; Telegram bot query turnaround < 3.0s (p95); spoken Khmer voice duration 30 to 60 seconds.

### 1.8 Unfair advantage

- **Zero-hardware infrastructure**: Requires zero custom river buoys or vulnerable physical sensors. Uses verified, permanent intergovernmental telemetry.
- **National administrative gazetteer integration**: Instant spatial geocoding for all 1,661 Cambodian communes using official 2025 MEF datasets.
- **Spoken Khmer vernacular delivery**: Overcomes low literacy through instant Gemini 2.0 Flash speech synthesis.

---

## 2. Product Requirements Document (PRD)

### 2.1 Executive summary

MekongPulse is an autonomous early warning and agronomic preservation system deployed on Google Cloud Run. It solves the "last-mile actionability gap" of large-scale hydrological models (such as Google Flood Hub and the Mekong River Commission) by translating raw meter river heights into hyper-local, stage-specific crop preservation directives delivered via Telegram and natural spoken Khmer voice notes.

### 2.2 Objectives and success metrics

| Metric name                     | Baseline                      | Target                              | Measurement method                                      |
| ------------------------------- | ----------------------------- | ----------------------------------- | ------------------------------------------------------- |
| Early warning lead time         | 0 to 12 hours (word of mouth) | 36 to 72 hours                      | Inundation prediction timestamp vs physical dike breach |
| Agricultural loss reduction     | $400–$700/ha destroyed        | >= 65% crop value salvaged          | Post-flood cooperative harvest survey                   |
| Telegram location query latency | N/A                           | < 3.0 seconds (p95)                 | Telemetry from pin share to audio/card dispatch         |
| Vernacular audio accessibility  | 0% (Text PDF bulletins)       | 100% of alerts accompanied by audio | Automated verification probe on alert dispatch          |

### 2.3 Explicit non-goals (out of scope)

The system MUST NOT attempt to solve the following items in this release:

1. **Custom Physical Sensor Hardware**: The system does not build or maintain physical IoT river buoys, ultrasonic sensors, or weather stations. It strictly consumes existing open public APIs.
2. **2D Hydrodynamic Floodplain Simulation**: The system does not run full Navier-Stokes numerical fluid simulations; it uses empirical rate-of-rise hydraulic head equations.
3. **Emergency Evacuation Dispatch**: The system does not replace national 119 emergency services or manage disaster rescue boats; it focuses on anticipatory agronomic preservation and commune early notice.
4. **Desktop Native Application**: The system is delivered via Telegram and responsive web; native desktop binaries are out of scope.

### 2.4 Functional requirements matrix

| Requirement ID | Name                              | Priority | Actor            | Input Contract                                           | Expected State Change / Output                                                                            |
| -------------- | --------------------------------- | -------- | ---------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| FR-01          | Autonomous Telemetry Polling      | P0       | System           | Scheduled cron trigger (every 15 mins)                   | Ingests live water levels from MRC stations (`020102`, `033401`, `019803`); persists time-series snapshot |
| FR-02          | Catchment Weather Forecasting     | P0       | System           | Commune coordinate bounding boxes                        | Pulls Open-Meteo 7-day precipitation and 0-7cm soil saturation                                            |
| FR-03          | Spatial Inundation Classification | P0       | System           | Water rise rate + MEF elevation gazetteer                | Assigns commune risk tier: `NORMAL`, `ADVISORY`, `WARNING`, or `DANGER`                                   |
| FR-04          | Agronomic Directive Generation    | P0       | System           | Risk tier + Crop stage (Ripening, Tillering, Vegetative) | Generates field directive: Emergency Harvest, Fertilizer Hold, Sluice Open                                |
| FR-05          | Gemini Khmer Vernacular Synthesis | P1       | System           | Technical risk and agronomic parameters                  | Synthesizes polite, culturally respectful Khmer text bulletin and 45s audio note                          |
| FR-06          | Telegram Bot Location Interaction | P1       | PER-001, PER-002 | Telegram user shares GPS location pin                    | Resolves nearest commune, returns risk badge, directive card, and playable voice note within 3.0s         |
| FR-07          | Autonomous Sentinel Background Patrol | P0   | Sentinel Agent   | 15-minute background patrol trigger                      | Evaluates all 1,661 communes against risk escalation triggers; dispatches unsolicited broadcast alerts with voice |
| FR-08          | Conversational ReAct Advisor Agent| P1       | Farmer, Chief    | Natural language text/audio query in Telegram/Web        | Google ADK ReAct loop invokes domain tools dynamically; returns stateful bilingual agronomic counsel     |
| FR-09          | Commune Subscription Management   | P1       | User, Chief      | Telegram `/subscribe <commune>` or inline button click   | Records chat ID to commune binding in PostgreSQL; receives automated push alerts upon risk escalation     |

### 2.5 Acceptance criteria (Gherkin scenarios)

#### AC-01: Location Pin Shared with High Flood Risk

```gherkin
Scenario: Farmer sends GPS location in flood-threatened commune
  Given an authenticated Telegram user in Koh Thom district, Kandal
  And the Prek Kdam river gauge rate-of-rise exceeds 0.08 m/hr
  When the user sends their GPS location pin to "@MekongPulseBot"
  Then the system MUST return a risk card within 3000ms
  And the risk tier MUST be marked "🟠 WARNING" or "🔴 DANGER"
  And the card MUST contain a stage-specific agronomic directive
  And the bot MUST attach a playable spoken Khmer audio voice note (MP3 format)
```

#### AC-02: Normal River Conditions Query

```gherkin
Scenario: Farmer queries commune during safe dry period
  Given an active Telegram session in Moung Ruessei, Battambang
  And river levels are > 2.0 meters below alarm stage
  When the user selects their commune from the menu
  Then the bot MUST return status "🟢 NORMAL"
  And the advisory MUST confirm normal farming activities are safe to proceed
  And the response time MUST be under 2000ms
```

#### AC-03: Autonomous Sentinel Background Alert Dispatch

```gherkin
Scenario: Sentinel detects river pulse escalation during 15-minute patrol
  Given the background Sentinel agent runs its 15-minute scheduled patrol
  And commune "080402" (Koh Thom) escalates from "🟡 ADVISORY" to "🟠 WARNING"
  And the last alert sent to commune "080402" was over 6 hours ago
  When the Sentinel agent evaluates the state transition
  Then it MUST autonomously synthesize a spoken Khmer voice alert via Gemini
  And it MUST push the alert card and voice note to all Telegram users subscribed to "080402"
  And it MUST post the warning bulletin to the public Telegram broadcast channel
  And it MUST log the dispatch run and recipient count in PostgreSQL "sentinel_alerts"
```

#### AC-04: Conversational ReAct Tool-Calling Turn

```gherkin
Scenario: User asks open-ended counterfactual question to ReAct agent
  Given an active chat with "@MekongPulseBot"
  When the user asks "If water rises 25cm tonight in Peam Chor, will my ripening rice flood?"
  Then the Google ADK ReAct agent MUST call the "get_station_telemetry" tool
  And it MUST call the "evaluate_crop_directive" tool with crop_stage "RIPENING"
  And it MUST reason over the simulated hydraulic delta
  And it MUST reply in natural conversational Khmer or English with exact lead times and harvest advice
```

#### AC-05: Heavy Rain with Fertilizer Hold Directive

```gherkin
Scenario: 48-hour rainfall forecast triggers fertilizer suspension
  Given a commune in Tillering rice growth stage (45 days post-planting)
  And Open-Meteo forecasts > 60mm rainfall over the next 48 hours
  And soil moisture saturation is > 85%
  When the agronomic decision engine evaluates the daily forecast
  Then the system MUST trigger directive "HOLD_FERTILIZER_APPLICATION"
  And the advice text MUST explicitly state that chemical applications will be washed away
```

#### AC-06: Upstream Station Telemetry Outage Fallback

```gherkin
Scenario: Primary MRC station endpoint returns HTTP 500 error
  Given the MRC station "020102" is temporarily unreachable
  When the telemetry ingestion agent attempts its scheduled poll
  Then the system MUST NOT crash or fail the entire ingestion run
  And the system MUST seamlessly fall back to adjacent station "033401"
  And the system MUST log a telemetry warning in Firestore
```

### 2.6 Edge cases and boundary conditions

- **Upstream Telemetry Outage**: If a specific MRC river station endpoint goes offline or times out, the ingestion service falls back to the nearest adjacent station with an empirical hydrologic correction factor.
- **Extreme Local Cloudburst with Low River Level**: When local rainfall is severe (>80mm/24h) but the river mainstream is calm, the system classifies the risk as `🟡 ADVISORY (LOCAL_FLASH_FLOOD)` rather than river overflow.
- **Low-Bandwidth Mobile Network**: If Telegram voice audio download fails or times out, the client automatically falls back to lightweight raw text and unicode risk indicators.

---

## 3. Software Requirements Specification (SRS)

### 3.1 System invariants

These invariants are immutable system rules. The implementation MUST NOT violate them under any operating condition:

1. **INV-01 (Hydrological Grounding)**: All flood risk levels and arrival time estimates MUST be grounded in verified external telemetry (MRC gauge heights or Open-Meteo precipitation). The system MUST NOT fabricate or hallucinate water elevations.
2. **INV-02 (Fail-Safe Telemetry Fallback)**: A network failure or HTTP 5xx error from an upstream telemetry endpoint MUST NOT crash the background worker. The system MUST fall back to adjacent basin stations or previous cached readings with explicit staleness timestamps.
3. **INV-03 (Agronomic Safety Primacy)**: Under conflicting risk signals, the agronomic recommendation engine MUST default to the conservative posture protecting human life and harvest capital (e.g., recommend harvest acceleration if risk is ambiguous).
4. **INV-04 (Zero-Hardware Dependency)**: The architecture MUST operate 100% on software-only cloud infrastructure without requiring physical river instrumentation.

### 3.2 External interface requirements

- **User Interfaces**:
  - Interactive Telegram Bot interface supporting inline keyboard navigation, location sharing, and direct audio note streaming.
  - Responsive web dashboard running in modern browsers with Google Maps Platform (Maps JavaScript API) geospatial layers.
- **Hardware Interfaces**: Google Cloud Run serverless execution container (2 vCPU, 2 GiB RAM, Generation 2 environment).
- **Software Interfaces**:
  - Mekong River Commission Telemetry API: `https://api.mrcmekong.org/api/v1/time-series/telemetry/recent/measurement/{stationId}`.
  - Open-Meteo Weather API: `https://api.open-meteo.com/v1/forecast`.
  - MEF Administrative Gazetteer: JSON/GeoJSON repository containing coordinates and elevations for 1,661 Cambodian communes.
  - Telegram Bot API: Webhook and polling handlers for `@MekongPulseBot`.
  - Google Vertex AI / Gemini 2.0 Flash: Multilingual text formatting and audio voice synthesis.

### 3.3 Non-functional requirements (NFRs)

| NFR ID | Category     | Metric Target                                                  | Verification Method                                      |
| ------ | ------------ | -------------------------------------------------------------- | -------------------------------------------------------- |
| NFR-01 | Latency      | p95 < 3,000ms for Telegram bot location query response         | Simulated webhook load tests via Locust                  |
| NFR-02 | Reliability  | Ingestion success rate >= 99.5% with adjacent-station fallback | Automated unit tests simulating station HTTP 500 outages |
| NFR-03 | Availability | >= 99.9% uptime on Google Cloud Run                            | Synthetic Google Cloud Monitoring probes                 |
| NFR-04 | Cost         | Marginal cost < $0.002 per commune alert dispatch              | Cloud billing telemetry over 5,000 simulated dispatches  |

### 3.4 Delivery tiers (Scope Hammering)

- **Tier 1 (Walking Skeleton / Hackathon MVP)**: Live MRC API polling for Prek Kdam and Chaktomuk stations; spatial elevation lookup for top 10 flood-prone communes in Kandal and Kampong Cham; Telegram bot responding to location pins with text risk card and agronomic advice; Cloud Run deployment with health probe.
- **Tier 2 (Target Competition Scope)**: Full 1,661 commune MEF gazetteer integration; spoken Khmer voice note audio generation via Gemini 2.0 Flash; Next.js interactive web dashboard with Google Maps Platform GIS map; Cloud Scheduler cron job polling telemetry every 30 minutes.
- **Tier 3 (Deferred / Phase 2 Roadmap)**: Crowdsourced community dike breach reporting with photo uploads; automated SMS gateway integration for non-smartphone users; MFI portfolio credit scoring API for climate insurance underwriting.

---

## 4. User Personas & Journey Maps

### 4.1 User personas (attribute schema)

#### Persona 1: PER-001 (Commune Chief / CCDM Chairman)

```yaml
persona_id: PER-001
role_name: Commune Chief (Mekhum) & CCDM Chairman
demographics:
  name: Dara Meas
  age: 54
  location: Koh Thom Commune, Kandal Province (Bassac River Basin)
  responsibility: 7 villages, 4,200 residents, 1,800 ha cultivated paddy
technical_proficiency: Medium
device_profile: Smartphone (OPPO Reno, 1080p, 4G Data)
primary_interfaces:
  - "Telegram Groups (District & Commune Administration)"
  - "Web GIS Dashboard"
rbac_permissions:
  - "alerts:broadcast"
  - "commune:status:write"
  - "reports:export"
jobs_to_be_done:
  - "Receive 48-hour advance notice before upstream Bassac river waters overtop village levees."
  - "Forward verified audio flood alerts directly to village chiefs and loudspeaker operators."
  - "Coordinate combine harvesters to prioritize low-lying agricultural zones."
pain_points:
  - "Provincial weather bulletins are text-heavy PDFs with no local flood arrival times."
  - "Farmers panic and sell unripe crops prematurely on false word-of-mouth rumors."
```

#### Persona 2: PER-002 (Smallholder Rice Farmer)

```yaml
persona_id: PER-002
role_name: Smallholder Rice Farmer
demographics:
  name: Bopha Sok
  age: 38
  location: Peam Chor Commune, Prey Veng Province
  holding_size: 3.0 hectares (wet-season Phka Rumduol jasmine paddy)
technical_proficiency: Low
literacy: Low text literacy; heavily prefers audio voice messages
device_profile: Low-cost Android Smartphone (Xiaomi Redmi 9A, 720p, 3G/4G Data)
primary_interfaces:
  - "Telegram voice notes & stickers"
  - "Facebook Messenger voice calls"
rbac_permissions:
  - "telemetry:read"
  - "alerts:receive"
  - "location:query"
jobs_to_be_done:
  - "Send GPS location pin via Telegram to know if water is coming to her field."
  - "Listen to a clear spoken Khmer voice note advising whether to harvest early or hold fertilizer."
  - "Protect her $4,200 microfinance loan investment from sudden submersion."
pain_points:
  - "Cannot read complex technical hydrographs or French/English scientific bulletins."
  - "Suffered total crop loss in 2022 due to unannounced overnight levee breach."
```

#### Persona 3: PER-003 (Microfinance Institution Ag-Loan Officer)

```yaml
persona_id: PER-003
role_name: MFI Senior Credit & Risk Officer
demographics:
  name: Sovann Rath
  age: 31
  location: Kampong Cham Regional Office
  portfolio: 320 active agricultural loans ($1.4M outstanding principal)
technical_proficiency: High
device_profile: Laptop (MacBook Air / Dell Latitude, Chrome, High-speed Wi-Fi)
primary_interfaces:
  - "Web GIS Vulnerability Heatmap"
  - "Automated CSV Risk Export"
rbac_permissions:
  - "communes:risk_map:read"
  - "analytics:export"
jobs_to_be_done:
  - "Monitor real-time flood risk across loan portfolios to plan anticipatory payment grace periods."
  - "Identify communes needing emergency harvest credit lines ahead of flood crests."
```

### 4.2 End-to-end journey map matrix

| Step ID | User Phase   | Actor   | Action                                                       | Touchpoint / Route      | Expected State Change                        | Failure Recovery Path                              |
| ------- | ------------ | ------- | ------------------------------------------------------------ | ----------------------- | -------------------------------------------- | -------------------------------------------------- |
| JRN-01  | Ingestion    | System  | Scheduled cron pulls 15-min telemetry from MRC stations      | `GET api.mrcmekong.org` | Hydro time-series updated in Firestore       | Falls back to adjacent station if 500 error        |
| JRN-02  | Evaluation   | System  | Spatial reasoner correlates rise velocity with MEF elevation | Spatial Reasoner        | Commune risk tier updated (`WARNING`)        | Uses conservative elevation buffer if data missing |
| JRN-03  | Directives   | System  | Agronomic engine checks crop calendar (85% maturity)         | Agri-Advisor            | Directs emergency harvest acceleration       | Defaults to protective harvest advice              |
| JRN-04  | Query        | PER-002 | Sends live GPS location pin in Telegram                      | `@MekongPulseBot`       | Nearest commune resolved (`Koh Thom`)        | Prompts text search if GPS pin is out of Cambodia  |
| JRN-05  | Dispatch     | System  | Gemini 2.0 synthesizes text card and audio voice note        | Telegram Webhook        | Sends risk badge, directive, and audio MP3   | Sends raw text card if audio synthesis times out   |
| JRN-06  | Listening    | PER-002 | Taps play on 45s spoken Khmer voice note                     | Telegram Audio Player   | Farmer listens to harvest directive in Khmer | Replay audio available offline                     |
| JRN-07  | Mobilization | PER-001 | Broadcasts audio note over commune public loudspeaker        | Loudspeaker Station     | Community mobilizes combine harvesters       | Telegram group announcement backup                 |
| JRN-08  | Dashboard    | PER-003 | Inspects live provincial river surge hydrograph              | `/dashboard`            | Regional risk heatmap rendered               | Table view fallback for slow internet              |
