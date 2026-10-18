"""Domain models (ERD §3.1, PRD §2.4, DESIGN contract).

Pure pydantic models with zero framework dependencies; shared by the FastAPI
gateway, the bot, and the sentinel patrol.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RiskTier(StrEnum):
    NORMAL = "NORMAL"
    ADVISORY = "ADVISORY"
    WARNING = "WARNING"
    DANGER = "DANGER"

    @property
    def emoji(self) -> str:
        return {"NORMAL": "🟢", "ADVISORY": "🟡", "WARNING": "🟠", "DANGER": "🔴"}[self.value]

    @property
    def label_kh(self) -> str:
        return {
            "NORMAL": "ធម្មតា",
            "ADVISORY": "ប្រុងប្រយ័ត្ន",
            "WARNING": "ព្រមាន",
            "DANGER": "គ្រោះថ្នាក់",
        }[self.value]

    @property
    def label_en(self) -> str:
        return self.value

    @property
    def severity(self) -> int:
        return list(RiskTier).index(self)

    def at_least(self, other: "RiskTier") -> bool:
        return self.severity >= other.severity


class FloodReason(StrEnum):
    NONE = "NONE"
    RIVER_PULSE = "RIVER_PULSE"
    RIVER_OVERFLOW = "RIVER_OVERFLOW"
    LOCAL_FLASH_FLOOD = "LOCAL_FLASH_FLOOD"


class CropStage(StrEnum):
    """Rice growth stages (FR-04). Day ranges are days post-planting."""

    TILLERING = "TILLERING"
    VEGETATIVE = "VEGETATIVE"
    FLOWERING = "FLOWERING"
    RIPENING = "RIPENING"

    @property
    def label_kh(self) -> str:
        return {
            "TILLERING": "បែកកូន",
            "VEGETATIVE": "លូតលាស់",
            "FLOWERING": "ចេញផ្កា",
            "RIPENING": "ទុំ",
        }[self.value]

    @property
    def label_en(self) -> str:
        return self.value.title()


class Urgency(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Directive(BaseModel):
    """One actionable agronomic field command."""

    action_code: str  # e.g. EMERGENCY_HARVEST_ACCELERATION
    family: str  # ERD directive_type: HARVEST | FERTILIZER_HOLD | SLUICE_OPEN | MONITOR
    title_en: str
    title_kh: str
    instruction_en: str
    instruction_kh: str
    urgency: Urgency
    priority: int = 100  # lower first


class StationSnapshot(BaseModel):
    """One reading of a river gauge (grounded telemetry, INV-01)."""

    station_id: str
    name: str
    river: str
    level_m: float
    alarm_stage_m: float
    flood_stage_m: float
    rate_of_rise_m_per_hr: float
    recorded_at: datetime
    is_stale_fallback: bool = False
    source: str = "live"  # live | fallback | cache
    fallback_offset_m: float | None = None
    staleness_minutes: int | None = None

    @property
    def margin_to_alarm_m(self) -> float:
        return round(self.alarm_stage_m - self.level_m, 3)

    @property
    def margin_to_flood_m(self) -> float:
        return round(self.flood_stage_m - self.level_m, 3)


class WeatherSnapshot(BaseModel):
    """Catchment forecast, aggregated per province (FR-02)."""

    province_code: str
    latitude: float
    longitude: float
    precipitation_48h_mm: float
    precipitation_7d_mm: float
    max_rain_24h_mm: float
    soil_moisture_pct: float
    fetched_at: datetime


class Commune(BaseModel):
    """One row of the 2025 MEF gazetteer (1,661 communes)."""

    code: str
    name_kh: str
    name_en: str
    district_code: str | None = None
    district_kh: str | None = None
    district_en: str | None = None
    province_code: str | None = None
    province_kh: str | None = None
    province_en: str | None = None
    lat: float | None = None
    lng: float | None = None
    ground_elevation_m: float | None = None
    nearest_station_id: str | None = None
    distance_to_station_km: float | None = None
    has_boundary: bool = False


class CommuneRisk(BaseModel):
    """Spatial inundation classification output (FR-03)."""

    commune_code: str
    commune_name_kh: str
    commune_name_en: str
    province: str | None = None
    lat: float | None = None  # centroid, used by the web GIS map
    lng: float | None = None
    tier: RiskTier
    score: int = Field(ge=0, le=100)
    reason: FloodReason = FloodReason.NONE
    lead_time_hours: int | None = None
    drivers: list[str] = Field(default_factory=list)
    station_id: str | None = None
    station_level_m: float | None = None
    estimated: bool = False  # true when telemetry came from fallback/cache
    updated_at: datetime


class AudioRef(BaseModel):
    uri: str  # storage uri (local path key or gs:// uri)
    url: str  # playable URL
    duration_seconds: float | None = None
    mime_type: str = "audio/mpeg"


class AssessmentResult(BaseModel):
    """OpenAPI §4.1 AssessmentResult plus dashboard extras."""

    commune_code: str
    commune_name_kh: str
    commune_name_en: str
    risk_tier: RiskTier
    score: int
    lead_time_hours: int | None
    directive: str  # primary action code
    directives: list[Directive]
    khmer_bulletin: str
    english_bulletin: str
    audio: AudioRef | None = None
    estimated: bool = False
    generated_at: datetime


class Subscription(BaseModel):
    id: int | None = None
    telegram_chat_id: str
    commune_id: str
    crop_stage: CropStage | None = None
    subscribed_at: datetime | None = None
    last_notified_at: datetime | None = None
    last_notified_risk_tier: RiskTier | None = None


class TelemetryWarning(BaseModel):
    station_id: str
    kind: str  # e.g. HTTP_500, TIMEOUT, FALLBACK_USED, CACHE_USED
    detail: str
    created_at: datetime


class PatrolRun(BaseModel):
    id: int | None = None
    run_at: datetime
    stations_polled: int
    communes_evaluated: int
    alerts_dispatched_count: int
    execution_duration_ms: int


class SentinelAlert(BaseModel):
    id: int | None = None
    patrol_run_id: int | None = None
    commune_id: str
    station_id: str | None = None
    risk_tier: RiskTier
    lead_time_hours: int | None = None
    directive_title: str
    bulletin_text: str
    audio_url: str | None = None
    dispatched_at: datetime
    recipients_count: int = 0


class FieldReportStatus(StrEnum):
    """Ground-truth follow-up from officials (verification layer)."""

    WATER_REACHED = "water_reached"
    NO_WATER = "no_water"
    OTHER = "other"


class FieldReport(BaseModel):
    """One ground-truth report for a commune, filed by a person on the ground."""

    id: str  # uuid4 hex
    commune_code: str
    status: FieldReportStatus
    note: str | None = None
    reporter_label: str | None = None
    source: str  # telegram | web
    reported_at: datetime


class AgentRunStatus(StrEnum):
    """Watch-officer approval lifecycle."""

    PENDING_APPROVAL = "pending_approval"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class AgentRun(BaseModel):
    """One autonomous watch pass: evidence check, draft, human approval."""

    id: str  # uuid4 hex
    commune_code: str
    commune_name_kh: str | None = None
    commune_name_en: str | None = None
    trigger: str = "manual"  # manual | transition
    previous_tier: RiskTier | None = None
    current_tier: RiskTier
    status: AgentRunStatus = AgentRunStatus.PENDING_APPROVAL
    rationale: str = ""
    draft_khmer: str
    draft_english: str | None = None
    tool_calls: list[dict] = Field(default_factory=list)
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    rejected_at: datetime | None = None
    published_at: datetime | None = None
    published_message_id: int | None = None
    published_text: str | None = None
    error: str | None = None


class ConversationTurn(BaseModel):
    chat_id: str
    role: str  # user | assistant
    content: str
    created_at: datetime | None = None
