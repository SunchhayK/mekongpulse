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
  assess: (communeCode: string, cropStage: CropStage = "RIPENING") =>
    request<Assessment>(`/api/v1/communes/${communeCode}/assess`, {
      method: "POST",
      body: JSON.stringify({ crop_stage: cropStage }),
    }),
  search: (query: string) =>
    request<SearchHit[]>(`/api/v1/communes/search?q=${encodeURIComponent(query)}`),
  resolve: (lat: number, lng: number) =>
    request<ResolvedCommune>(`/api/v1/communes/resolve?lat=${lat}&lng=${lng}`),
};
