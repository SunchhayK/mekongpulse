"""Persistence boundary: one repository interface, two adapters.

Development/staging run on the local PostgreSQL container (`pg_db`); production
runs on Firestore Native + Cloud Storage. The active adapter is chosen from
ENVIRONMENT in the factory below, so no application code branches on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .config import Settings
from .models import (
    AgentRun,
    AudioRef,
    Commune,
    CommuneRisk,
    ConversationTurn,
    FieldReport,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    Subscription,
    TelemetryWarning,
    WeatherSnapshot,
)
from .stations import StationConfig


class Repository(Protocol):
    async def init(self) -> None: ...
    async def close(self) -> None: ...

    # --- telemetry ---------------------------------------------------------
    async def seed_stations(self, stations: list[StationConfig]) -> None: ...
    async def save_observation(self, snapshot: StationSnapshot) -> None: ...
    async def latest_observation(self, station_id: str) -> StationSnapshot | None: ...
    async def telemetry_series(
        self, station_id: str, hours: int
    ) -> list[tuple[datetime, float, float | None]]: ...
    async def save_failover_offset(
        self, station_id: str, fallback_id: str, offset_m: float
    ) -> None: ...
    async def get_failover_offset(self, station_id: str) -> float | None: ...
    async def last_sync_age_minutes(self) -> int | None: ...

    # --- weather -----------------------------------------------------------
    async def save_weather(self, forecast: WeatherSnapshot) -> None: ...
    async def latest_weather_by_province(self) -> dict[str, WeatherSnapshot]: ...

    # --- communes & risk ----------------------------------------------------
    async def seed_communes(self, communes: list[Commune]) -> int: ...
    async def commune_count(self) -> int: ...
    async def get_commune(self, code: str) -> Commune | None: ...
    async def list_communes(self) -> list[Commune]: ...
    async def save_commune_risks(self, risks: list[CommuneRisk]) -> None: ...
    async def risk_map(self, province: str | None = None) -> list[CommuneRisk]: ...
    async def get_commune_risk(self, code: str) -> CommuneRisk | None: ...

    # --- subscriptions -------------------------------------------------------
    async def upsert_subscription(
        self, chat_id: str, commune_id: str, crop_stage: str | None
    ) -> Subscription: ...
    async def remove_subscription(self, chat_id: str, commune_id: str) -> bool: ...
    async def subscriptions_for_commune(self, commune_id: str) -> list[Subscription]: ...
    async def subscriptions_for_chat(self, chat_id: str) -> list[Subscription]: ...
    async def touch_notified(
        self, chat_id: str, commune_id: str, tier: RiskTier, at: datetime
    ) -> None: ...

    # --- sentinel ------------------------------------------------------------
    async def save_patrol_run(self, run: PatrolRun) -> PatrolRun: ...
    async def save_sentinel_alert(self, alert: SentinelAlert) -> None: ...
    async def last_sentinel_alert(self, commune_id: str) -> SentinelAlert | None: ...
    async def recent_sentinel_alerts(self, limit: int = 50) -> list[SentinelAlert]: ...
    async def save_alert_dispatch(
        self,
        commune_id: str,
        tier: RiskTier,
        directive_family: str,
        bulletin_kh: str,
        audio_uri: str | None,
        audio_duration: float | None,
        recipients: int,
    ) -> None: ...
    async def save_telemetry_warning(self, warning: TelemetryWarning) -> None: ...

    # --- advisor -------------------------------------------------------------
    async def append_turn(self, chat_id: str, role: str, content: str) -> None: ...
    async def recent_turns(self, chat_id: str, limit: int = 12) -> list[ConversationTurn]: ...

    # --- field reports ---------------------------------------------------------
    async def add_field_report(self, report: FieldReport) -> FieldReport: ...
    async def list_field_reports(
        self, commune_code: str | None = None, limit: int = 20
    ) -> list[FieldReport]: ...

    # --- watch runs ------------------------------------------------------------
    async def add_agent_run(self, run: AgentRun) -> AgentRun: ...
    async def update_agent_run(self, run: AgentRun) -> None: ...
    async def get_agent_run(self, run_id: str) -> AgentRun | None: ...
    async def list_agent_runs(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[AgentRun]: ...


class AudioStoreProtocol(Protocol):
    async def put(self, key: str, data: bytes, mime_type: str = "audio/mpeg") -> AudioRef: ...
    async def head(self, key: str) -> AudioRef | None: ...
    async def get(self, key_or_uri: str) -> bytes: ...


def create_repository(settings: Settings) -> Repository:
    backend = settings.repository_backend or ("firestore" if settings.is_production else "postgres")
    if backend == "memory":
        from .memory_repo import MemoryRepository

        return MemoryRepository()
    if backend == "firestore":
        from .firestore_repo import FirestoreRepository

        return FirestoreRepository(project=settings.firestore_project or settings.vertex_project)
    from .postgres_repo import PostgresRepository

    return PostgresRepository(settings.database_url)


def create_audio_store(settings: Settings) -> AudioStoreProtocol:
    if settings.is_production:
        from .audio_store import GCSAudioStore

        return GCSAudioStore(settings.gcs_bucket, settings.gcs_public_base)
    from .audio_store import LocalAudioStore

    return LocalAudioStore(settings.audio_dir, settings.public_base_url)
