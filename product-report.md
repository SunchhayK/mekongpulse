---
id: REPORT-PROD-002
document_type: product_report
title: MekongPulse Product Specification Report
project_name: "MekongPulse"
version: 1.6.1
status: approved
last_updated: 2026-10-18
owners: ["@bytelab-lead", "@tech-lead", "@product-manager"]
profile: "Enterprise"
competition: "Google Cloud AI Builder Cup 2026 (JAPAC)"
theme: "Sustainability & Social Impact"
---

# Product Report: MekongPulse

## 1. Lean Canvas

### 1.1 Problem statements

1. **Unactionable Hydrological Telemetry**: The existing forecast layers stop at the hazard. Google Flood Hub publishes riverine forecasts for 150+ countries including Cambodia, and the Mekong River Commission (MRC) publishes raw station elevations (e.g. "Prek Kdam at 6.33m"), but commune leaders and farmers cannot translate either into field-level flood arrival timing or crop danger. Impact: In 2022, 152,386 ha of agricultural land was affected across 14 provinces (85,482 households, 15 deaths; NCDM/HRF SitRep No. 2), and a lost season puts the US$405–500/ha production cost of wet-season rice at risk (CFAP).
2. **The Last-Mile Warning Gap**: Existing civic alert systems (e.g. EWS 1294) deliver hazard-generic messages (storm, UV, preparedness) but no agronomic guidance. Impact: Farmers fail to accelerate harvests, or spend roughly US$150/ha on a fertilizer application that heavy rain washes away (single-application cost range US$120–240/ha).
3. **Microfinance Debt Collateral Default**: Roughly 28% of indebted rural households have pledged land titles as loan collateral (six MFIs hold ~75% of microloans; a land title corresponds to loans of about US$4,700). Flood crop losses turn default into land loss, structural poverty, and forced migration to urban garment factories or cross-border labor.

#### Existing alternatives

- Google Flood Hub (free, riverine-only, covers Cambodia; expert data layer and email summaries; Google labels it "informational purposes only"; no crop advice).
- MRC flood forecasting (138 stations, 22 mainstream forecast points; bulletins re-disseminated by National Mekong Committees, agencies and media) and the One Mekong app.
- Official EWS 1294 IVR voice calls (~118,000 subscribers; hazard and preparedness messages, no agronomic guidance; subscription-based, SIM churn caps reach).
- MOWRAM Facebook text bulletins (unstructured PDF images; inaccessible to low-literacy farmers) and the FAO/MOWRAM PEARL agrometeorological bulletin (text, via Telegram/Facebook).
- Crop-stage advisory tools with no hazard trigger: IRRI Rice Crop Manager, AfricaRice RiceAdvice, AKILIMO (stage captured through extension workers, not per farmer on a messaging channel).
- Informal word-of-mouth warnings from upstream fishermen (uncalibrated, late).

### 1.2 Customer segments

MekongPulse reaches farmers through relay people and serves officials and extension advisors directly; the split is a product rule, not an implementation detail (`research/farmer-reach.md`):

- **Farmers (PER-002) — reached through relay people.** Smallholder rice farmers across flood-prone lowlands in Kandal, Kampong Cham, Prey Veng, and Battambang. Direct-to-farmer delivery is relay-mediated: commune chiefs, extension officers, co-op staff, and family members forward spoken Khmer bulletins and play the public commune page aloud. The Telegram bot remains a fan-out and ground-truth surface (alerts, `/report`), not an assumption of direct farmer adoption — rural reach is Facebook/Messenger/TikTok, Telegram's observed role in Cambodia is broadcasting to the relay layer, and surveyed app-install competence is minimal.
- **Commune chiefs and disaster committees (PER-001) — all channels.** The chief (_Mekhum_) receives alerts, forwards voice bulletins to village loudspeakers, uses the web console read-only for situational awareness and coordination, and works the officer assistant (draft on Telegram; draft → publish on its dedicated web page).
- **Extension advisors and agri-sector staff (PER-004) — officer assistant.** District/provincial extension officers, co-op staff, and programme officers are the trained-users audience for the officer assistant: they verify a commune's evidence, draft bilingual status updates, and publish to the broadcast channel after signing in with the officer passcode (a short-lived session; the admin token never reaches the browser). They can type or speak their questions and drafts in Khmer.
- **Secondary audience (web console):** district/provincial disaster management offices (PCDM), agricultural cooperatives and contract-farming exporters (e.g. AMRU Rice) scheduling combines ahead of regional surges, and NGO anticipatory-action programme staff.
- **Sellers, traders and the general public — public signal only.** Rice collectors, millers and dryers follow the same public Telegram broadcast channel and read-only console as everyone else. MekongPulse deliberately does not sell buyers a harvest-timing advantage: field evidence on Cambodian paddy markets documents a buyer-side information gap, inaccurate weighing and price pressure on distressed farmers, so seller-specific feeds, "verified buyer" access and distress rankings are ruled out by design (`research/sellers-market.md`). The sourced pitch is narrow: the price is published (CRF publishes district wet-paddy prices on Telegram every 1–3 days during harvest as JPG, no archive), the forward-looking commune harvest risk is not.
- **Tertiary audience (roadmap):** microfinance institutions (Amret, Sathapana, Prasac) wanting crop climate risk feeds for portfolio planning; export and batch APIs are Phase 2, not this release.
- **Early adopters**: 30 high-vulnerability communes within the Tonle Sap and Bassac flood corridors (e.g. communes of Koh Thom district in Kandal, Peam Chor district in Prey Veng, and Moung Ruessei district in Battambang).

### 1.3 Unique value proposition (UVP)

- **Core pitch**: The defensible slot is hazard × stage × spoken Khmer. Flood Hub and the MRC publish the hazard, IRRI-style tools deliver agronomy with no hazard trigger, and no product in Cambodia delivers agronomic instructions as spoken Khmer. MekongPulse joins public river telemetry and rain forecasts to each farmer's stored rice stage and delivers the resulting directive as a Khmer voice note, shareable by relay people through the public Telegram channel and a Khmer-first commune page, with a read-only coordination console and an officer assistant (draft → publish) for commune and district officials and extension advisors.
- **Analogy**: "An AI agronomist in every farmer's phone, and a command picture for every commune chief."

### 1.4 Proposed solution

1. **Autonomous Hydro-Meteorological Ingestion Loop**: Continuously polls live 15-minute water levels, rates of rise, and temperature from key MRC stations (`020102` Prek Kdam, `033401` Chaktomuk, `033402` Koh Khel, `019802` Kompong Cham) combined with Open-Meteo 7-day precipitation forecasts.
2. **Spatial Elevation Inundation Reasoner**: Maps gauge surge velocities against the 2025 MEF administrative gazetteer (1,661 communes) to calculate time-to-inundation and assign 4 standardized risk tiers (Normal, Advisory, Warning, Danger).
3. **Per-Farmer Stage Profiles, Collected Once**: The farmer picks a rice stage once per season in Telegram, using plain-language Khmer labels; the choice is stored on the commune subscription and reused for every alert. Farmers who never answer fall back to the commune season default, which resolves to the harvest-protective ripening posture (INV-03) until planting-date onboarding lands; a month-aware default is the Phase 2 refinement.
4. **Stage-Aware Agronomic Directives**: The deterministic engine combines risk tier, forecast rain, soil moisture, and the stored stage to issue field commands: emergency combine mobilization (ripening stage) versus chemical fertilizer hold (tillering/vegetative stage in heavy rain) versus sluice preparation (warning and above).
5. **Vernacular Spoken Khmer Audio**: Gemini synthesizes respectful Khmer voice notes directly playable on low-cost smartphones without reading barriers, delivered as Telegram voice notes and playable from the web console for loudspeaker sharing. Voice notes are content-addressed from bucketed telemetry, so repeated and shared views reuse the MP3 while the risk situation is materially unchanged.
6. **Officials' Coordination Console (web)**: A read-only basin view for commune chiefs, district committees and NGO partners: commune risk map with zero external map tiles (instant load on weak networks), station hydrographs, risk register, and the Khmer voice bulletin with playback for community broadcast.
7. **Verification & Ground-Truth Layer**: Every risk row opens to its deterministic provenance — reading source and age, 4-check QC over the stored station series (gaps, stuck values, spikes, range), heuristic cross-checks (rainfall agreement, upstream coherence), a confidence label with stable reason ids, a 5-step bilingual evidence chain, and the MRC-style limitations notice (no LLM in the trust path; `research/farmer-reach.md` §6). Relay people and officials file ground-truth reports ("did water reach the fields?") from Telegram or the web.
8. **Officer Assistant with Actions (dedicated web page + Telegram)**: A first-class traced agentic assistant — its own page at `/{locale}/assistant` with header, bottom-nav, and dashboard entry points — for officials and extension advisors. It grounds answers in station evidence, drafts deterministic bilingual status updates, accepts typed or spoken Khmer questions (server-side transcription), and, once the officer signs in with the passcode, posts updates to the public Telegram channel. Replies render as formatted markdown, the conversation survives a refresh, and channel-post failures explain the setup step instead of showing a raw Telegram error. A deterministic bilingual daily digest summarises tier counts, elevated communes and stale readings for the broadcast channel and the bot's DM.

### 1.5 Channels and delivery

- **Farmer delivery — relay-mediated.** Farmers are reached through relay people: commune chiefs, extension officers, co-op staff, and family members forward spoken Khmer voice bullets and play the shareable commune page aloud. The interactive Telegram bot (`@MekongPulseBot`) carries the same Khmer audio, the rice-stage onboarding, and the ground-truth `/report` flow; it is a fan-out and verification surface, not an assumption of direct farmer adoption (`research/farmer-reach.md`).
- **Official channel — automated hazard broadcasts and a daily digest**: Sentinel alerts pushed to subscribed users and the public Telegram broadcast channel for commune/agency re-dissemination, now with a bilingual daily digest (admin-guarded `POST /api/v1/digest/send`; bot `/digest`) and a commune-page link on every escalation post. Cell broadcast, SMS and IVR remain with NCDM and EWS 1294; MekongPulse does not duplicate them.
- **Web — coordination, verification and the officer assistant**: the basin risk map answers which communes are escalating, on what station evidence, what directive was issued, and what ground truth has been reported from the field. Public read-only, with visible data sources and thresholds for journalists, NGOs and anticipatory-action partners; officials and extension advisors use the dedicated officer assistant page (draft → publish after passcode sign-in; typed or spoken Khmer input). A public, Khmer-first commune page (`/{locale}/commune?code=XXXXXX`) carries the evidence summary, the voice bulletin and field reports for relay playout. The chosen crop stage is kept in `?stage=`, so a shared link reproduces the same briefing and reuses the same cached voice note.

### 1.6 Financial model

- **Revenue model**:
  - B2G & NGO Resilience Licensing: $500/year per district disaster committee for priority alert dispatch and subscriber coverage reporting.
  - Commercial Cooperative Subscription: $20/month per agricultural cooperative for combine harvest coordination feeds.
  - Microfinance Anticipatory Underwriting API: $1.50 per query assessing harvest climate risk for microloan originations.
- **Fixed infrastructure costs**: Google Cloud Run (min-instances=1) ~$15/month; Google Cloud Storage & Firestore ~$5/month.
- **Variable costs**: Gemini 3 Flash (text bulletin polish + TTS voice synthesis) ~$0.08 per 1,000 alerts; external APIs $0.00 (MRC and Open-Meteo open APIs are free). Marginal cost per commune alert batch < $0.002 USD.

### 1.7 Key metrics (OKRs)

- **North Star metric**: Hectares of standing rice protected through proactive harvest acceleration or fertilizer postponement.
- **Baseline**: 0 (New project kickoff).
- **Target (90 days)**: 2,500 hectares protected across 30 active early-adopter communes.
- **Activation metric**: 300 farmers with a stored crop-stage profile across the 30 communes (set once per season in the bot).
- **Secondary technical metrics**: Warning lead time: 36 to 72 hours; Telegram bot query turnaround < 3.0s (p95); spoken Khmer voice duration 30 to 60 seconds.

### 1.8 Unfair advantage

- **Zero-hardware infrastructure**: Requires zero custom river buoys or vulnerable physical sensors. Uses verified, permanent intergovernmental telemetry.
- **National administrative gazetteer integration**: Instant spatial geocoding for all 1,661 Cambodian communes using official 2025 MEF datasets.
- **Spoken Khmer vernacular delivery**: Overcomes low literacy through instant Gemini speech synthesis; no surveyed product delivers agronomic instructions as spoken Khmer.
- **Hazard × stage × Khmer combination**: Flood Hub, MRC/One Mekong and EWS 1294 stop at the hazard; Rice Crop Manager, RiceAdvice and AKILIMO stop at agronomy with no hazard trigger; ChivCheat covers cashew disease. None joins river-flood forecasting to per-farmer stage advice (survey in `research/landscape.md`).

---

## 2. Product Requirements Document (PRD)

### 2.1 Executive summary

MekongPulse is an autonomous early warning and agronomic preservation system deployed on Google Cloud Run. It solves the "last-mile actionability gap" of large-scale hydrological models (such as Google Flood Hub and the Mekong River Commission) by translating raw meter river heights into hyper-local, stage-specific crop preservation directives, delivered as natural spoken Khmer voice notes through relay people and a Khmer-first public commune page, backed by a deterministic evidence layer and ground-truth field reports, with a read-only web console and a traced officer assistant for commune and district officials and extension advisors.

### 2.2 Objectives and success metrics

| Metric name                     | Baseline                      | Target                              | Measurement method                                      |
| ------------------------------- | ----------------------------- | ----------------------------------- | ------------------------------------------------------- |
| Early warning lead time         | 0 to 12 hours (word of mouth) | 36 to 72 hours                      | Inundation prediction timestamp vs physical dike breach |
| Agricultural loss reduction     | US$405–500/ha production cost at risk | >= 65% crop value salvaged          | Post-flood cooperative harvest survey                   |
| Telegram location query latency | N/A                           | < 3.0 seconds (p95)                 | Telemetry from pin share to audio/card dispatch         |
| Vernacular audio accessibility  | 0% (Text PDF bulletins)       | 100% of alerts accompanied by audio | Automated verification probe on alert dispatch          |

### 2.3 Explicit non-goals (out of scope)

The system MUST NOT attempt to solve the following items in this release:

1. **Custom Physical Sensor Hardware**: The system does not build or maintain physical IoT river buoys, ultrasonic sensors, or weather stations. It strictly consumes existing open public APIs.
2. **2D Hydrodynamic Floodplain Simulation**: The system does not run full Navier-Stokes numerical fluid simulations; it uses empirical rate-of-rise hydraulic head equations.
3. **Emergency Evacuation Dispatch**: The system does not replace national 119 emergency services or manage disaster rescue boats; it focuses on anticipatory agronomic preservation and commune early notice.
4. **Desktop Native Application**: The system is delivered via Telegram and responsive web; native desktop binaries are out of scope.
5. **Farmer-Facing Web Personalization**: The web console MUST NOT collect or require per-farmer crop data, and it serves officials and the public read-only. Rice-stage profiles are collected only in the Telegram bot.
6. **National Alert Duplication**: The system does not build an SMS/IVR/cell-broadcast stack. Those channels belong to NCDM and EWS 1294; MekongPulse feeds official dissemination instead of duplicating it.
7. **Seller/Buyer Advantage Products**: No seller-specific feeds, "verified buyer" access, distress/opportunity commune rankings or harvest-timing products sold to traders. Risk signals are published publicly to reduce information asymmetry, never sold to the already-advantaged side of the market (`research/sellers-market.md`).
8. **Parallel Damage-Reporting Pipeline**: No competing loss-and-damage capture, official acknowledgement flows or evacuation tooling. Loss-and-damage data already flows CCDM → DCDM → PCDM → NCDM through KoBoToolbox and WFP PRISM; an unapproved parallel record creates conflicting numbers (`research/gov-workflow.md`).

### 2.4 Functional requirements matrix

| Requirement ID | Name                              | Priority | Actor            | Input Contract                                           | Expected State Change / Output                                                                            |
| -------------- | --------------------------------- | -------- | ---------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| FR-01          | Autonomous Telemetry Polling      | P0       | System           | Scheduled cron trigger (every 15 mins)                   | Ingests live water levels from MRC stations (`020102`, `033401`, `033402`, `019802`); persists time-series snapshot |
| FR-02          | Catchment Weather Forecasting     | P0       | System           | Commune coordinate bounding boxes                        | Pulls Open-Meteo 7-day precipitation and 0-7cm soil saturation                                            |
| FR-03          | Spatial Inundation Classification | P0       | System           | Water rise rate + MEF elevation gazetteer                | Assigns commune risk tier: `NORMAL`, `ADVISORY`, `WARNING`, or `DANGER`                                   |
| FR-04          | Stage-Aware Agronomic Directive Generation | P0 | System           | Risk tier + forecast rain/soil moisture + farmer's stored crop stage (set once in Telegram; commune default when unset) | Generates field directive: Emergency Harvest, Fertilizer Hold, Sluice Open                                |
| FR-05          | Gemini Khmer Vernacular Synthesis | P1       | System           | Technical risk and agronomic parameters                  | Synthesizes polite, culturally respectful Khmer text bulletin and 30–60s audio note                       |
| FR-06          | Telegram Bot Location Interaction | P1       | PER-002          | Telegram user shares GPS location pin                    | Resolves nearest commune, returns risk badge, directive card, and playable voice note within 3.0s; asks for the rice stage once when no profile is stored |
| FR-07          | Autonomous Sentinel Background Patrol | P0   | Sentinel Agent   | 15-minute background patrol trigger                      | Evaluates every station-mapped commune (1,544 of the 1,661-commune gazetteer; 117 have no mapped station) against risk escalation triggers; dispatches stage-grouped unsolicited broadcast alerts with voice |
| FR-08          | Conversational ReAct Advisor Agent| P1       | User (retargeted: officials, extension advisors) | Natural language text or voice query in Telegram         | Google ADK ReAct loop invokes domain tools dynamically; returns stateful bilingual agronomic counsel     |
| FR-09          | Commune Subscription Management   | P1       | User, Chief      | Telegram `/subscribe <commune>` or inline button click   | Records chat ID to commune binding in PostgreSQL, stores the crop-stage profile, and pushes alerts scored with the stored stage |
| FR-10          | Officials' Coordination Console   | P1       | PER-001, PER-003, public | Web browser (static export on Firebase Hosting)          | Renders basin risk map, station hydrographs, commune risk register, printable status summary, CSV export, alert dispatch log, and playable Khmer bulletin, read-only; the officer assistant lives on its own page (FR-13); collects no per-farmer data |
| FR-11          | Deterministic Verification & Evidence Layer | P1 | Public, PER-001, PER-004 | Commune code (`GET /api/v1/communes/{code}/evidence`) | Returns a provenance payload: reading source and freshness, 4-check QC block (gaps, stuck, spike, range), heuristic cross-checks (rainfall agreement, upstream coherence), confidence label with stable reason ids, 5-step bilingual evidence chain, and the MRC-style limitations notice; no LLM in any verdict |
| FR-12          | Ground-Truth Field Reporting Loop | P1       | PER-001, PER-004, relay people | Telegram `/report` flow or `POST /api/v1/communes/{code}/reports` | Records a `water_reached` / `no_water` / `other` report with optional note and reporter label (source `telegram` or `web`); `GET /api/v1/communes/{code}/reports` lists it; shown in the web console, the commune page, and the bot |
| FR-13          | Officer Assistant (agentic, signed-in, voice-enabled) | P1 | PER-001, PER-004 | Dedicated `/{locale}/assistant` page; `POST /api/v1/officer/login`, `POST /api/v1/advisor`, `POST /api/v1/advisor/transcribe`; Telegram drafts | One traced agentic turn returns `{reply, tool_calls, actions}`; tools include `get_commune_evidence`, `draft_status_update` (deterministic bilingual text), and `publish_to_channel` (a real channel post, officer session required; Telegram stays draft-only). Passcode sign-in issues a 12 h session; spoken Khmer input is transcribed server-side; replies render as markdown and the 60-message thread persists locally |
| FR-14          | Bilingual Daily Digest            | P1       | System, public   | Admin-guarded `POST /api/v1/digest/send`; bot `/digest`  | Posts a Khmer-first bilingual digest (tier counts, top elevated communes with lead times, stale-telemetry line, dashboard link) to the public Telegram channel; `/digest` returns it in a Telegram DM |
| FR-15          | Khmer-First Bilingual Web & Commune Page | P1 | Public, relay people | `/{locale}/commune?code=XXXXXX` (`km` default, `en` toggle) | Renders the public commune page: one-tap voice bulletin with text fallback when audio is null, crop-stage chips, evidence summary, field reports, and share; console dialogs link to the full page |

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
  And if no crop-stage profile is stored, the bot MUST ask for the stage once and persist it with the subscription
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
  And commune "080404" (Kaoh Thum Ka) escalates from "🟡 ADVISORY" to "🟠 WARNING"
  And the last alert sent to commune "080404" was over 6 hours ago
  When the Sentinel agent evaluates the state transition
  Then it MUST autonomously synthesize a spoken Khmer voice alert via Gemini
  And it MUST push the alert card and voice note to all Telegram users subscribed to "080404"
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
  Then the system MUST trigger directive "HOLD_CHEMICAL_FERTILIZER"
  And the advice text MUST explicitly state that chemical applications will be washed away
  And the stage MUST come from the farmer's stored profile, not asked again per alert
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

#### AC-07: Crop-Stage Onboarding Asked Once (Bot Flow)

```gherkin
Scenario: Farmer subscribes without a stored crop stage
  Given a Telegram user subscribing to a commune with no stored crop stage
  When the bot confirms the subscription
  Then it MUST ask for the rice stage once using Khmer inline options
  And it MUST store the answer on the subscription
  And later alerts and the ReAct advisor MUST reuse the stored stage without asking again
  And `/crop <commune>` (or the change-stage button) MUST update the stored stage
```

#### AC-08: Officials' Console Serves Coordination Without Farmer Input

```gherkin
Scenario: Commune chief and district officer coordinate from the web console
  Given a commune chief in Koh Thom district and a district disaster officer
  When either opens the web console during an escalation to WARNING
  Then the console MUST render the basin risk map, station hydrographs, commune risk register, printable status summary, CSV export, and alert dispatch log, read-only
  And it MUST NOT prompt for a crop stage or any per-farmer data
  And the commune's Khmer voice bulletin MUST be playable for loudspeaker sharing
```

#### AC-09: Evidence Behind a Commune Warning Is Deterministic

```gherkin
Scenario: Official opens the evidence behind a commune warning
  Given a commune at ADVISORY or above with a stored station series
  When the commune's evidence payload is requested
  Then the response MUST include the station reading source and age, the 4-check QC block, both heuristic cross-checks, a confidence label with stable reason ids, the 5-step bilingual evidence chain, and the limitations notice
  And no LLM MUST be involved in producing any QC verdict or confidence label
  And a check that cannot run MUST be reported as "unavailable" rather than guessed
```

#### AC-10: Ground-Truth Report Filed from Telegram

```gherkin
Scenario: Relay person files a ground-truth report from Telegram
  Given a Telegram user with a subscribed commune
  When they send /report, choose the commune, and answer "water reached" / "no water" / "other"
  Then the report MUST be stored with the reporter label and source "telegram"
  And officials MUST see it in the commune's report list on the console and the commune page
  And the same report MUST be filable via POST /api/v1/communes/{code}/reports with source "web"
```

#### AC-11: Publish Action Requires Officer Sign-In

```gherkin
Scenario: Officer publishes a status update through the assistant
  Given the officer assistant page or Telegram
  When an officer asks it to draft a status update for a set of communes
  Then the assistant MUST return a deterministic bilingual draft built from stored risk rows only
  And publishing MUST require a valid officer session obtained from POST /api/v1/officer/login (passcode → 12 h signed session); scripts MAY instead use the legacy X-Officer-Token admin header
  And without a session the publish action MUST return "denied" or "unavailable" and nothing MUST be posted
  And with a session the post MUST appear on the public broadcast channel and its status MUST be reported back
```

#### AC-12: Daily Digest Reaches the Broadcast Channel

```gherkin
Scenario: Daily digest is posted and readable
  Given telemetry for the day has been synced
  When the admin-guarded digest trigger runs, or a user sends /digest to the bot
  Then the public channel MUST receive the Khmer digest followed by the English digest
  And the digest MUST contain tier counts, elevated communes with lead times where present, a stale-telemetry line when any station is degraded, and the dashboard link
  And with Telegram not configured the endpoint MUST return "unavailable" instead of failing the run
```

#### AC-13: Commune Page Plays Aloud for Relay Playback

```gherkin
Scenario: Relay person plays the commune page aloud
  Given the public commune page at /{locale}/commune?code=XXXXXX
  When it loads on a shared phone
  Then a one-tap Listen control MUST play the Khmer voice bulletin for the selected rice stage
  And if audio is unavailable (null), the page MUST show the Khmer text bulletin instead of a broken player
  And the page MUST show the evidence summary and the commune's field reports, and offer a share action
```

#### AC-14: Spoken Khmer Question Is Transcribed

```gherkin
Scenario: Officer speaks a question on the assistant page
  Given a browser with microphone access on /{locale}/assistant
  When the officer records a Khmer question (up to 60 s) and stops
  Then the clip MUST be sent to POST /api/v1/advisor/transcribe and the returned Khmer text MUST be placed in the composer for review before sending
  And a denied microphone, an oversized clip, or an unavailable transcription service MUST surface friendly bilingual guidance without breaking the chat
  And cancelling a recording MUST discard it without calling the API
```

### 2.6 Edge cases and boundary conditions

- **Upstream Telemetry Outage**: If a specific MRC river station endpoint goes offline or times out, the ingestion service falls back to the nearest adjacent station with an empirical hydrologic correction factor.
- **Extreme Local Cloudburst with Low River Level**: When local rainfall is severe (>80mm/24h) but the river mainstream is calm, the system classifies the risk as `🟡 ADVISORY (LOCAL_FLASH_FLOOD)` rather than river overflow.
- **Low-Bandwidth Mobile Network**: If Telegram voice audio download fails or times out, the client automatically falls back to lightweight raw text and unicode risk indicators.
- **Farmer With No Stored Crop Stage**: The engine evaluates with the commune season default (ripening posture, harvest-protective per INV-03), and the bot asks for the stage once on the next interaction; the answer persists with the subscription. A month-aware default is Phase 2.
- **TTS Quota Exhausted**: When voice synthesis is unavailable (quota, safety block, transient API error), assessments and the commune page return the text bulletin with a null audio field; the listener path degrades to text and no request fails.
- **Evidence With a Short Series**: QC checks that cannot run on the available window report "unavailable" and contribute no confidence reason; the confidence label records only checks that actually ran, and the evidence chain still states the reading's source and age.

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
  - Interactive Telegram Bot interface supporting inline keyboard navigation, location sharing, direct audio note streaming, the ground-truth `/report` flow, and the `/digest` digest. The bot is the only place rice-stage profiles are collected (once per season); it serves relay people and officials as a broadcast/fan-out surface.
  - Responsive web console for officials and the public, read-only: Leaflet basin map with switchable Esri Light Gray, OpenStreetMap and OpenTopoMap basemaps (overlays render over the neutral canvas when tiles are slow), station hydrographs, commune risk register, Khmer voice bulletin playback, and the deterministic evidence panel. The officer assistant has its own page (`/{locale}/assistant`, draft → publish after passcode sign-in, typed or spoken Khmer).
  - Public commune page (`/{locale}/commune?code=XXXXXX`, Khmer default with an English toggle): one-tap voice bulletin with a text fallback when audio is null, crop-stage chips, evidence summary, field reports, and share — designed for a relay person to open and play aloud.
- **Hardware Interfaces**: Google Cloud Run serverless execution container (2 vCPU, 2 GiB RAM, Generation 2 environment).
- **Software Interfaces**:
  - Mekong River Commission Telemetry API: `https://api.mrcmekong.org/api/v1/time-series/telemetry/recent/measurement/{stationId}`.
  - Open-Meteo Weather API: `https://api.open-meteo.com/v1/forecast`.
  - MEF Administrative Gazetteer: JSON/GeoJSON repository containing coordinates and elevations for 1,661 Cambodian communes.
  - Telegram Bot API: Webhook and polling handlers for `@MekongPulseBot`.
  - Google Gemini 3 Flash family on Vertex AI / API key path: `gemini-3.8-flash` for bulletin text and the ADK advisor, `gemini-3.8-flash-tts` for 24 kHz spoken Khmer voice synthesis.

### 3.3 Non-functional requirements (NFRs)

| NFR ID | Category     | Metric Target                                                  | Verification Method                                      |
| ------ | ------------ | -------------------------------------------------------------- | -------------------------------------------------------- |
| NFR-01 | Latency      | p95 < 3,000ms for Telegram bot location query response         | Simulated webhook load tests via Locust                  |
| NFR-02 | Reliability  | Ingestion success rate >= 99.5% with adjacent-station fallback | Automated unit tests simulating station HTTP 500 outages |
| NFR-03 | Availability | >= 99.9% uptime on Google Cloud Run                            | Synthetic Google Cloud Monitoring probes                 |
| NFR-04 | Cost         | Marginal cost < $0.002 per commune alert dispatch              | Cloud billing telemetry over 5,000 simulated dispatches  |

### 3.4 Delivery tiers (Scope Hammering)

- **Tier 1 (Walking Skeleton / Hackathon MVP)**: Live MRC API polling for Prek Kdam and Chaktomuk stations; spatial elevation lookup for top 10 flood-prone communes in Kandal and Kampong Cham; Telegram bot responding to location pins with text risk card and agronomic advice; Cloud Run deployment with health probe.
- **Tier 2 (Target Competition Scope)**: Full 1,661 commune MEF gazetteer integration; spoken Khmer voice note audio generation via Gemini 3 Flash TTS; Next.js web console with an interactive Leaflet basin map and switchable basemaps; Cloud Scheduler cron job polling telemetry every 15 minutes.
- **Tier 3 (Deferred / Phase 2 Roadmap)**: Officials' console add-ons over existing data only. Shipped in 0.4.0: printable basin status summary (tier counts, station status, top elevated communes, limited to fields the engine actually holds), CSV export of commune risk states, and the alert dispatch log over existing escalation records. Shipped in 0.6.0: the deterministic evidence/verification layer (FR-11), the text ground-truth reporting loop (FR-12, Telegram + web), the officer assistant with its officer-session publish action (FR-13), the bilingual daily digest (FR-14), and the Khmer-first bilingual web with the public commune page (FR-15). Shipped in 0.7.0: the dedicated assistant page with passcode sign-in and server-side Khmer voice input. Remaining: SitRep household, hectare, casualty and evacuation fields (needs an official data partner) and commune subscriber coverage as aggregate counts only (ranked #3 in `research/features-scan.md` §2). Public harvest-urgency layer (commune × ripening stage × 36–72h risk window, rendered from existing engine outputs) published to the broadcast channel and console — public signal, never a buyer feed. Planting-date onboarding (ask once, derive stage automatically through the season; ranked #1). Upstream→downstream crest-arrival lag display (pairs existing station series; ranked #5). Photo-attached field reports (optional photo on the shipped text-only loop) and crowdsourced community dike-breach reporting, only with a named validation partner (ranked #2). Social-media posting (Facebook) for the digest and bulletins — Facebook/Messenger/TikTok carry the rural reach Telegram cannot (`research/farmer-reach.md` §1–2). Anticipatory-action readiness/activation triggers with a partner webhook (WFP-style 7-day readiness / 3-day activation; ranked #6). Post-flood recovery directives (ranked #8). Subscription into official NCDM cell-broadcast dissemination once the standard lands. MFI portfolio credit scoring API for climate insurance underwriting. Rationale and sources: `research/features-scan.md`, `research/gov-workflow.md`, `research/sellers-market.md`, `research/farmer-reach.md`.

---

## 4. User Personas & Journey Maps

### 4.1 User personas (attribute schema)

#### Persona 1: PER-001 (Commune Chief / CDMC Chair)

```yaml
persona_id: PER-001
role_name: Commune Chief (Mekhum) & CDMC Chair
demographics:
  name: Dara Meas
  age: 54
  location: Kaoh Thum Ka commune (080404), Koh Thom district, Kandal Province (Bassac River Basin)
  responsibility: 7 villages, 4,200 residents, 1,800 ha cultivated paddy
technical_proficiency: Medium
device_profile: Smartphone (OPPO Reno, 1080p, 4G Data)
primary_interfaces:
  - "Telegram Groups (District & Commune Administration)"
  - "Web console (read-only, for situational awareness and verification)"
  - "Officer assistant (dedicated web page and Telegram) — evidence checks, status drafting, typed or spoken Khmer input, and publishing after sign-in"
rbac_permissions:
  - "alerts:forward"
  - "commune:status:read"
  - "commune:status:publish (officer session)"
jobs_to_be_done:
  - "Receive 48-hour advance notice before upstream Bassac river waters overtop village levees."
  - "Verify a warning against its evidence chain and field reports before forwarding it."
  - "Forward verified audio flood alerts directly to village chiefs and loudspeaker operators, played from the bot or the console."
  - "Draft and publish bilingual status updates to the public channel from the officer assistant."
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
  location: Kaoh Sampov commune (140605), Peam Chor district, Prey Veng Province
  holding_size: 3.0 hectares (wet-season Phka Rumduol jasmine paddy)
technical_proficiency: Low
literacy: Low text literacy; heavily prefers audio voice messages
device_profile: Low-cost Android Smartphone (Xiaomi Redmi 9A, 720p, 3G/4G Data)
primary_interfaces:
  - "Spoken Khmer voice bulletins relayed by people she trusts (commune chief, extension officer, co-op staff, family), played over loudspeakers or shared phones"
  - "The Khmer-first commune page, opened and played aloud by a relay person"
excluded_interfaces:
  - "Direct app installs, accounts, or text chat — most surveyed farmers cannot install new apps, and fact-checking is the weakest measured competence (`research/farmer-reach.md` §4)"
rbac_permissions:
  - "alerts:receive"
  - "location:query"
  - "profile:crop_stage:write"
  - "reports:file (via relay person)"
jobs_to_be_done:
  - "Hear a clear spoken Khmer voice note — forwarded by her commune chief or played on the co-op phone — advising whether to harvest early or hold fertilizer."
  - "Know whether water is coming to her field, by location pin or commune lookup someone she trusts runs in the bot."
  - "Have her rice stage set once per season so every forwarded alert and the commune page match her field."
  - "Protect her $4,700 microfinance loan investment from sudden submersion."
pain_points:
  - "Cannot read complex technical hydrographs or French/English scientific bulletins."
  - "Suffered total crop loss in 2022 due to an unannounced overnight flood."
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
  - "Public basin risk map and commune risk register (read-only)"
  - "Automated CSV risk export (Phase 2, not in this release)"
rbac_permissions:
  - "communes:risk_map:read"
jobs_to_be_done:
  - "Monitor flood risk across loan portfolio communes to plan anticipatory payment grace periods."
  - "Identify communes needing emergency harvest credit lines ahead of flood crests (per-commune view now; export in Phase 2)."
```

#### Persona 4: PER-004 (Extension Advisor / Co-op Agri-Support Officer)

```yaml
persona_id: PER-004
role_name: Extension Advisor / Co-op Agri-Support Officer
demographics:
  name: Chanthou Pich
  age: 29
  location: District agriculture office, Prey Veng Province
  portfolio: ~400 farming households across 6 communes
technical_proficiency: High
device_profile: Laptop (web console) and smartphone (Telegram)
primary_interfaces:
  - "Officer assistant (dedicated web page and Telegram) — evidence checks, status drafting, channel publishing"
  - "Public commune page for member playout and field-report follow-up"
rbac_permissions:
  - "commune:status:read"
  - "commune:status:publish (officer session)"
  - "reports:read:all"
jobs_to_be_done:
  - "Verify a warning against the station evidence and QC state before advising members."
  - "Draft and publish plain-language bilingual updates without inventing readings."
  - "Collect ground-truth water-reached reports from member communes after an event."
```

### 4.2 End-to-end journey map matrix

Two tracks share one engine. Farmer-reach (JRN-03..07) is relay-mediated: the bot and the commune page carry the Khmer audio, and relay people forward or play it (`research/farmer-reach.md` §7). The official track (JRN-08..09) uses the read-only web console; the verification and officer flows (JRN-10..13) add the evidence layer, ground-truth reports, the officer assistant, and the digest. No farmer data is collected on the console, and no crop-stage prompt exists outside the bot.

| Step ID | User Phase   | Actor   | Action                                                       | Touchpoint / Route      | Expected State Change                        | Failure Recovery Path                              |
| ------- | ------------ | ------- | ------------------------------------------------------------ | ----------------------- | -------------------------------------------- | -------------------------------------------------- |
| JRN-01  | Ingestion    | System  | Scheduled cron pulls 15-min telemetry from MRC stations      | `GET api.mrcmekong.org` | Hydro time-series updated in Firestore       | Falls back to adjacent station if 500 error        |
| JRN-02  | Evaluation   | System  | Spatial reasoner correlates rise velocity with MEF elevation | Spatial Reasoner        | Commune risk tier updated (`WARNING`)        | Uses conservative elevation buffer if data missing |
| JRN-03  | Query        | PER-002 | Sends live GPS location pin in Telegram                      | `@MekongPulseBot`       | Nearest commune resolved (e.g. `140605`)     | Prompts text search if GPS pin is out of Cambodia  |
| JRN-04  | Stage onboarding | PER-002 | Picks her rice stage from Khmer inline buttons, once per season | `@MekongPulseBot` (inline keyboard) | Stage stored on the commune subscription | Unanswered: commune default (ripening) applies and the bot asks once more on the next interaction |
| JRN-05  | Directives   | System  | Engine combines risk tier, forecast rain, and the stored stage | Agri-Advisor            | Directs emergency harvest (ripening) or fertilizer hold (tillering/vegetative, heavy rain) | Defaults to protective harvest advice (INV-03)     |
| JRN-06  | Dispatch     | System  | Gemini synthesizes the text card and Khmer voice note        | Telegram Webhook        | Sends risk badge, directive, and audio note  | Sends raw text card if audio synthesis times out   |
| JRN-07  | Listening    | PER-002 | Taps play on the 30–60s spoken Khmer voice note              | Telegram Audio Player   | Farmer hears the harvest or fertilizer directive in Khmer | Replay available; bot text fallback while audio loads |
| JRN-08  | Mobilization | PER-001 | Verifies the escalation on the console, then plays the bulletin over the village loudspeaker | Web console + Loudspeaker Station | Community mobilizes combine harvesters | Telegram group announcement backup                 |
| JRN-09  | Coordination | PER-001, PER-003 | Reviews escalating communes, station evidence, and ground-truth field reports | Web console (`/`, read-only) | Risk map, hydrographs, and risk register rendered | Leaflet map renders commune and station overlays over a neutral canvas; basemaps switch between Esri Light Gray, OSM and OpenTopoMap |
| JRN-10  | Verification | PER-001, PER-004 | Opens the evidence behind an escalation (QC, confidence, chain, limitations) | Evidence panel / `/{locale}/commune?code=…` | Warning accepted, amended with a field report, or held back | Checks that did not run show "unavailable"; confidence reasons name what actually held |
| JRN-11  | Ground truth | Relay person | Files "did water reach the fields?" via `/report` or the web form | `@MekongPulseBot` / `POST /api/v1/communes/{code}/reports` | Report stored with reporter label and source; visible to officials on the console and commune page | Unreachable API → clear error, report retriable; no partial record |
| JRN-12  | Officer action | PER-001, PER-004 | Asks the assistant to draft, then to publish, a status update | Officer assistant page (signed in); Telegram for drafts | Bilingual draft returned from stored rows; publish posts to the public channel with its status traced | No officer session → drafts stay private, publish returns "denied" |
| JRN-13  | Broadcast | System, relay people | Digest posts to the channel; relay people follow the commune link and play it aloud | Public Telegram channel / commune page | Tier picture and commune detail reach the relay layer | Telegram not configured → digest returns "unavailable"; the page still loads |

---

## 5. Google Cloud AI Builder Cup 2026 alignment

MekongPulse is submitted to the Google Cloud AI Builder Cup 2026 (JAPAC region) under the **Sustainability & Social Impact** theme. The official theme definition is an "AI-powered solution that addresses a meaningful environmental or societal challenge" through "improving resource efficiency, increasing accessibility, strengthening resilience, supporting communities, or enabling more informed and sustainable decision-making." MekongPulse maps to all five: resilience (anticipatory flood warning for communes), accessibility (spoken Khmer for low-literacy users), resource efficiency (fertilizer not washed away, harvest saved before the crest), communities (commune-level coverage and loudspeaker broadcasting), and informed decisions (stage-aware directives for farmers, station evidence for officials).

### 5.1 Judging rubric mapping

| Criterion (weight) | MekongPulse evidence |
| ---------------- | -------------------- |
| Technical Merit & Gen AI Implementation (40%) | Autonomous multi-agent pipeline (ingestion, spatial reasoner, agronomic engine, sentinel patrol, ADK ReAct advisor with the officer assistant's traced tool calls and officer-gated channel actions); Gemini 3 Flash load-bearing in bulletin polish and TTS voice synthesis while QC, evidence, and confidence stay deterministic by design (no LLM in the trust path); deterministic validation bound by the four system invariants; GCP deployment path (Cloud Run + Cloud Scheduler + Firestore) with the live demo on Firebase Hosting; 15-minute scheduler. |
| Problem Alignment & Impact (25%) | Named beneficiaries and targets: 30 early-adopter communes, 300 farmers with stored stage profiles, 2,500 ha protected in 90 days; quantified problem with cited flood losses; measurable 36–72 hour warning lead time; public signal for traders, officials and journalists without selling anyone a timing advantage. |
| Innovation & Creativity (25%) | The hazard × stage × spoken Khmer combination, sourced as a market gap: Flood Hub and MRC stop at the hazard, Rice Crop Manager/RiceAdvice stop at agronomy with no hazard trigger, and no surveyed product delivers agronomic instructions as spoken Khmer. |
| User Experience & Solution Design (10%) | Voice-first, relay-mediated delivery (Khmer voice bullets and a one-tap commune page for playout); read-only officials' console with an interactive Leaflet map and the officer assistant (draft → publish, collapsible tool trace); risk overlays render even when basemap tiles are slow; Khmer-first labels throughout with an English toggle; staged fallbacks when audio or telemetry fails. |

### 5.2 Submission constraints checklist

- Live URL on Google Cloud Run or Firebase Hosting; no third-party cloud in the submitted path.
- Demo video ≤ 3:00 minutes (official documents conflict between "3" and "3–4" minutes; submit under 3).
- Public GitHub repository with fresh in-window code.
- English PDF deck covering problem, impact, feasibility, and scalability.
- Google AI requirement: Gemini family in both the text and voice paths.

Evidence pack for the deck: `research/competition.md` (rules, rubric and themes from primary sources), `research/landscape.md` (competitive gap and farmer-channel evidence), `research/cambodia-context.md` (fact-check of the report's figures), `research/features-scan.md` (comparable systems and candidate features), `research/farmer-reach.md` (channels, digital competence, and the relay-mediated design), `research/sellers-market.md` (paddy-market evidence and the public-signal design constraint), `research/gov-workflow.md` (NCDM reporting chain and officials' console roadmap).

Deployment note: the console runs on Firebase Hosting; the API runs the same container image the Cloud Run deploy script ships (`projects/scripts/deploy_gcp.sh`), currently also operated self-hosted for the demo, so the submitted path can be served entirely from GCP by enabling billing and running the deploy script once.
