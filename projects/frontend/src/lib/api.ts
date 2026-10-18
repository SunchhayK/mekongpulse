// Typed client for the MekongPulse FastAPI gateway.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export type FloodRiskTier = "NORMAL" | "ADVISORY" | "WARNING" | "DANGER";
export type CropStage = "TILLERING" | "VEGETATIVE" | "FLOWERING" | "RIPENING";

export interface Health {
  status: string;
  timestamp: string;
  mrc_station_connection: "CONNECTED" | "STALE" | "OFFLINE" | "UNKNOWN";
  environment: string;
  repository: string;
}

export interface StationTelemetry {
  station_id: string;
  name: string;
  river: string;
  level_m: number;
  alarm_stage_m: number;
  flood_stage_m: number;
  rate_of_rise_m_per_hr: number;
  recorded_at: string;
  is_stale_fallback: boolean;
  source: string;
  staleness_minutes: number | null;
}

export interface CommuneRiskRow {
  commune_code: string;
  commune_name_kh: string;
  commune_name_en: string;
  province: string | null;
  lat: number | null;
  lng: number | null;
  tier: FloodRiskTier;
  score: number;
  reason: string;
  lead_time_hours: number | null;
  drivers: string[];
  station_id: string | null;
  station_level_m: number | null;
  estimated: boolean;
  updated_at: string;
}

export interface HydroPoint {
  t: string;
  level_m: number;
  rain_mm: number | null;
}

export interface Directive {
  action_code: string;
  family: string;
  title_en: string;
  title_kh: string;
  instruction_en: string;
  instruction_kh: string;
  urgency: string;
  priority: number;
}

export interface AudioRef {
  uri: string;
  url: string;
  duration_seconds: number | null;
  mime_type: string;
}

export interface Assessment {
  commune_code: string;
  commune_name_kh: string;
  commune_name_en: string;
  risk_tier: FloodRiskTier;
  score: number;
  lead_time_hours: number | null;
  directive: string;
  directives: Directive[];
  khmer_bulletin: string;
  english_bulletin: string;
  audio: AudioRef | null;
  estimated: boolean;
  generated_at: string;
}

export interface SearchHit {
  commune_code: string;
  name_kh: string;
  name_en: string;
  district_en: string | null;
  province_en: string | null;
  lat: number | null;
  lng: number | null;
  has_boundary: boolean;
}

export interface ResolvedCommune {
  commune_code: string;
  name_kh: string;
  name_en: string;
  district_en: string | null;
  province_en: string | null;
  nearest_station_id: string | null;
  lat: number | null;
  lng: number | null;
  method: string;
}

export interface AlertLogEntry {
  id: number | null;
  commune_code: string;
  commune_name_kh: string;
  commune_name_en: string;
  province: string | null;
  station_id: string | null;
  risk_tier: FloodRiskTier;
  lead_time_hours: number | null;
  directive_title: string;
  bulletin_text: string;
  audio_url: string | null;
  dispatched_at: string;
  recipients_count: number;
}

/* --- Evidence layer (GET /api/v1/communes/{code}/evidence) --------------- */

export type EvidenceConfidence = "high" | "medium" | "low";
export type EvidenceQCStatus = "pass" | "warn" | "fail" | "unavailable";
export type EvidenceCrossCheckStatus = "agree" | "disagree" | "unavailable";
export type EvidenceFreshness = "fresh" | "recent" | "stale";

export interface EvidenceQCCheck {
  id: "gaps" | "stuck" | "spike" | "range";
  status: EvidenceQCStatus;
  detail: string;
  detail_kh: string;
}

export interface EvidenceQCBlock {
  status: EvidenceQCStatus;
  checks: EvidenceQCCheck[];
}

export interface EvidenceCrossCheck {
  id: "rainfall_agreement" | "upstream_coherence";
  status: EvidenceCrossCheckStatus;
  detail: string;
  detail_kh: string;
}

export interface EvidenceStation {
  station_id: string;
  name: string;
  distance_km: number | null;
  source: string;
  recorded_at: string;
  age_minutes: number;
  freshness: EvidenceFreshness;
  level_m: number;
  rate_of_rise_m_per_hr: number;
  alarm_stage_m: number;
  flood_stage_m: number;
}

export interface EvidenceChainStep {
  id: "reading" | "change" | "threshold" | "tier" | "directive";
  text_en: string;
  text_kh: string;
}

export interface EvidencePayload {
  commune_code: string;
  commune_name_kh: string;
  commune_name_en: string;
  generated_at: string;
  risk_tier: FloodRiskTier;
  score: number;
  confidence: EvidenceConfidence;
  confidence_reasons: string[];
  station: EvidenceStation;
  qc: EvidenceQCBlock;
  cross_checks: EvidenceCrossCheck[];
  evidence_chain: EvidenceChainStep[];
  limitations: { text_en: string; text_kh: string };
}

/* --- Field reports (GET /api/v1/communes/{code}/reports) ------------------- */

export type FieldReportStatus = "water_reached" | "no_water" | "other";

export interface FieldReport {
  id: string;
  commune_code: string;
  status: FieldReportStatus;
  note: string | null;
  reporter_label: string | null;
  source: string;
  reported_at: string;
}

export interface FieldReportList {
  reports: FieldReport[];
}

/* --- Officer assistant (POST /api/v1/advisor) ------------------------------ */

export interface AdvisorHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

/** Signed-in officer session (POST /api/v1/officer/login). */
export interface OfficerSession {
  session: string;
  expires_at: string;
}

export interface TranscribeRequest {
  audio_base64: string;
  mime_type: string;
  locale_hint: "km" | "en";
}

export interface AdvisorToolCall {
  name: string;
  status: string;
  summary: string;
}

export interface AdvisorAction {
  type: string;
  status: string;
  detail: string | null;
}

export interface AdvisorReply {
  reply: string;
  tool_calls: AdvisorToolCall[];
  actions: AdvisorAction[];
}

export interface AdvisorRequest {
  message: string;
  history: AdvisorHistoryTurn[];
  locale: "km" | "en";
  commune_code?: string;
}

export type AgentRunStatus = "pending_approval" | "published" | "rejected" | "failed";

export interface AgentRunToolCall {
  name: string;
  status: string;
  summary: string;
}

export interface AgentRun {
  id: string;
  commune_code: string;
  commune_name_kh: string | null;
  commune_name_en: string | null;
  trigger: "manual" | "transition" | string;
  previous_tier: FloodRiskTier | null;
  current_tier: FloodRiskTier;
  status: AgentRunStatus;
  rationale: string;
  draft_khmer: string;
  draft_english: string | null;
  tool_calls: AgentRunToolCall[];
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
  rejected_at: string | null;
  published_at: string | null;
  published_message_id: number | null;
  published_text: string | null;
  error: string | null;
}

export class ApiError extends Error {
  status: number;
  problemType?: string;
  title?: string;

  constructor(status: number, title?: string, detail?: string, problemType?: string) {
    super(detail || title || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.problemType = problemType;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let title: string | undefined;
    let detail: string | undefined;
    let problemType: string | undefined;
    try {
      const problem = await response.json();
      title = problem.title;
      detail = problem.detail;
      problemType = problem.type;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, title, detail, problemType);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/v1/health"),
  stations: () => request<StationTelemetry[]>("/api/v1/telemetry/latest"),
  hydrograph: (stationId: string, hours = 168) =>
    request<{ station_id: string; hours: number; points: HydroPoint[] }>(
      `/api/v1/telemetry/hydrograph/${stationId}?hours=${hours}`,
    ),
  riskMap: (province?: string) =>
    request<CommuneRiskRow[]>(
      `/api/v1/communes/risk-map${province ? `?province=${encodeURIComponent(province)}` : ""}`,
    ),
  assess: (
    communeCode: string,
    cropStage?: CropStage,
    options?: { force?: boolean; session?: string },
  ) =>
    request<Assessment>(`/api/v1/communes/${communeCode}/assess`, {
      method: "POST",
      // The Khmer voice bulletin is the product's core output for low-literacy
      // listeners; synthesis adds ~20-40s and the dialog waits for it.
      body: JSON.stringify({
        ...(cropStage ? { crop_stage: cropStage } : {}),
        with_audio: true,
        ...(options?.force ? { force: true } : {}),
      }),
      ...(options?.force && options.session
        ? { headers: { authorization: `Bearer ${options.session}` } }
        : {}),
    }),
  search: (query: string) =>
    request<SearchHit[]>(`/api/v1/communes/search?q=${encodeURIComponent(query)}`),
  resolve: (lat: number, lng: number) =>
    request<ResolvedCommune>(`/api/v1/communes/resolve?lat=${lat}&lng=${lng}`),
  alertLog: (limit = 50) =>
    request<AlertLogEntry[]>(`/api/v1/alerts/log?limit=${limit}`),
  evidence: (communeCode: string) =>
    request<EvidencePayload>(`/api/v1/communes/${communeCode}/evidence`),
  reports: (communeCode: string, limit = 20) =>
    request<FieldReportList>(`/api/v1/communes/${communeCode}/reports?limit=${limit}`),
  advisor: (body: AdvisorRequest, session?: string) =>
    request<AdvisorReply>("/api/v1/advisor", {
      method: "POST",
      body: JSON.stringify(body),
      // Publishing actions require a signed-in officer session; asked
      // read-only, the advisor answers without one.
      ...(session ? { headers: { authorization: `Bearer ${session}` } } : {}),
    }),
  officerLogin: (passcode: string) =>
    request<OfficerSession>("/api/v1/officer/login", {
      method: "POST",
      body: JSON.stringify({ passcode }),
    }),
  // Server-side Khmer ASR: browser speech APIs do not cover Khmer.
  transcribe: (body: TranscribeRequest) =>
    request<{ text: string }>("/api/v1/advisor/transcribe", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  watchRuns: (session: string, limit = 10) =>
    request<{ runs: AgentRun[] }>(`/api/v1/watch/runs?limit=${limit}`, {
      headers: { authorization: `Bearer ${session}` },
    }),
  watchRun: (session: string, communeCode?: string | null) =>
    request<{ run: AgentRun }>("/api/v1/watch/runs", {
      method: "POST",
      body: JSON.stringify(communeCode ? { commune_code: communeCode } : {}),
      headers: { authorization: `Bearer ${session}` },
    }),
  approveRun: (
    session: string,
    runId: string,
    khmerText?: string,
    englishText?: string,
  ) =>
    request<{ run: AgentRun }>(`/api/v1/watch/runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        ...(khmerText ? { khmer_text: khmerText } : {}),
        ...(englishText ? { english_text: englishText } : {}),
      }),
      headers: { authorization: `Bearer ${session}` },
    }),
  rejectRun: (session: string, runId: string) =>
    request<{ run: AgentRun }>(`/api/v1/watch/runs/${runId}/reject`, {
      method: "POST",
      body: JSON.stringify({}),
      headers: { authorization: `Bearer ${session}` },
    }),
};
