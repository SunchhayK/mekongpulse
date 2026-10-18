"""In-memory repository adapter.

Used by the test-suite and by `REPOSITORY_BACKEND=memory` offline demos
(`ENVIRONMENT=development` with no PostgreSQL running). Implements the full
`Repository` protocol; not for production use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import (
    AgentRun,
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


class MemoryRepository:
    def __init__(self) -> None:
        self.stations: dict[str, StationConfig] = {}
        self.observations: dict[str, list[StationSnapshot]] = {}
        self.offsets: dict[str, float] = {}
        self.weather: dict[str, WeatherSnapshot] = {}
        self.communes: dict[str, Commune] = {}
        self.risks: dict[str, CommuneRisk] = {}
        self.subscriptions: dict[tuple[str, str], Subscription] = {}
        self.patrol_runs: list[PatrolRun] = []
        self.sentinel_alerts: list[SentinelAlert] = []
        self.dispatches: list[dict] = []
        self.warnings: list[TelemetryWarning] = []
        self.turns: dict[str, list[ConversationTurn]] = {}
        self.field_reports: list[FieldReport] = []
        self.agent_runs: dict[str, AgentRun] = {}
        self._sub_seq = 0

    async def init(self) -> None:  # pragma: no cover - trivially in-memory
        pass

    async def close(self) -> None:  # pragma: no cover
        pass

    # --- telemetry ------------------------------------------------------------
    async def seed_stations(self, stations: list[StationConfig]) -> None:
        for s in stations:
            self.stations[s.id] = s

    async def save_observation(self, snapshot: StationSnapshot) -> None:
        points = self.observations.setdefault(snapshot.station_id, [])
        points[:] = [p for p in points if p.recorded_at != snapshot.recorded_at]
        points.append(snapshot)
        points.sort(key=lambda p: p.recorded_at)

    async def latest_observation(self, station_id: str) -> StationSnapshot | None:
        points = self.observations.get(station_id) or []
        return points[-1] if points else None

    async def telemetry_series(
        self, station_id: str, hours: int
    ) -> list[tuple[datetime, float, float | None]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [
            (p.recorded_at, p.level_m, None)
            for p in self.observations.get(station_id, [])
            if p.recorded_at >= cutoff
        ]

    async def save_failover_offset(
        self, station_id: str, fallback_id: str, offset_m: float
    ) -> None:
        self.offsets[station_id] = offset_m

    async def get_failover_offset(self, station_id: str) -> float | None:
        return self.offsets.get(station_id)

    async def last_sync_age_minutes(self) -> int | None:
        newest: datetime | None = None
        for points in self.observations.values():
            for p in points:
                if newest is None or p.recorded_at > newest:
                    newest = p.recorded_at
        if newest is None:
            return None
        return int((datetime.now(timezone.utc) - newest).total_seconds() // 60)

    # --- weather ----------------------------------------------------------------
    async def save_weather(self, forecast: WeatherSnapshot) -> None:
        self.weather[forecast.province_code] = forecast

    async def latest_weather_by_province(self) -> dict[str, WeatherSnapshot]:
        return dict(self.weather)

    # --- communes & risk ------------------------------------------------------------
    async def seed_communes(self, communes: list[Commune]) -> int:
        for c in communes:
            self.communes[c.code] = c
        return len(communes)

    async def commune_count(self) -> int:
        return len(self.communes)

    async def get_commune(self, code: str) -> Commune | None:
        return self.communes.get(code)

    async def list_communes(self) -> list[Commune]:
        return list(self.communes.values())

    async def save_commune_risks(self, risks: list[CommuneRisk]) -> None:
        for r in risks:
            self.risks[r.commune_code] = r

    async def risk_map(self, province: str | None = None) -> list[CommuneRisk]:
        values = list(self.risks.values())
        if province:
            needle = province.strip().lower()
            values = [
                r for r in values
                if (r.province or "").lower().find(needle) >= 0
            ]
        return sorted(values, key=lambda r: (-r.score, r.commune_code))

    async def get_commune_risk(self, code: str) -> CommuneRisk | None:
        return self.risks.get(code)

    # --- subscriptions ---------------------------------------------------------------
    async def upsert_subscription(
        self, chat_id: str, commune_id: str, crop_stage: str | None
    ) -> Subscription:
        key = (chat_id, commune_id)
        existing = self.subscriptions.get(key)
        if existing is None:
            self._sub_seq += 1
            sub = Subscription(
                id=self._sub_seq,
                telegram_chat_id=chat_id,
                commune_id=commune_id,
                crop_stage=crop_stage,
                subscribed_at=datetime.now(timezone.utc),
            )
        else:
            sub = existing.model_copy(
                update={"crop_stage": crop_stage or existing.crop_stage}
            )
        self.subscriptions[key] = sub
        return sub

    async def remove_subscription(self, chat_id: str, commune_id: str) -> bool:
        return self.subscriptions.pop((chat_id, commune_id), None) is not None

    async def subscriptions_for_commune(self, commune_id: str) -> list[Subscription]:
        return [s for (chat, cid), s in self.subscriptions.items() if cid == commune_id]

    async def subscriptions_for_chat(self, chat_id: str) -> list[Subscription]:
        return [s for (chat, cid), s in self.subscriptions.items() if chat == chat_id]

    async def touch_notified(
        self, chat_id: str, commune_id: str, tier: RiskTier, at: datetime
    ) -> None:
        key = (chat_id, commune_id)
        if key in self.subscriptions:
            self.subscriptions[key] = self.subscriptions[key].model_copy(
                update={"last_notified_at": at, "last_notified_risk_tier": tier}
            )

    # --- sentinel ------------------------------------------------------------------------
    async def save_patrol_run(self, run: PatrolRun) -> PatrolRun:
        saved = run.model_copy(update={"id": len(self.patrol_runs) + 1})
        self.patrol_runs.append(saved)
        return saved

    async def save_sentinel_alert(self, alert: SentinelAlert) -> None:
        saved = alert.model_copy(update={"id": len(self.sentinel_alerts) + 1})
        self.sentinel_alerts.append(saved)

    async def last_sentinel_alert(self, commune_id: str) -> SentinelAlert | None:
        matches = [a for a in self.sentinel_alerts if a.commune_id == commune_id]
        if not matches:
            return None
        return max(matches, key=lambda a: a.dispatched_at)

    async def recent_sentinel_alerts(self, limit: int = 50) -> list[SentinelAlert]:
        by_newest = sorted(self.sentinel_alerts, key=lambda a: a.dispatched_at, reverse=True)
        return by_newest[:limit]

    async def save_alert_dispatch(
        self,
        commune_id: str,
        tier: RiskTier,
        directive_family: str,
        bulletin_kh: str,
        audio_uri: str | None,
        audio_duration: float | None,
        recipients: int,
    ) -> None:
        self.dispatches.append(
            {
                "commune_id": commune_id,
                "risk_tier": tier.value,
                "directive_type": directive_family,
                "khmer_bulletin_text": bulletin_kh,
                "audio_storage_uri": audio_uri,
                "audio_duration_seconds": audio_duration,
                "recipients_count": recipients,
                "dispatched_at": datetime.now(timezone.utc),
            }
        )

    async def save_telemetry_warning(self, warning: TelemetryWarning) -> None:
        self.warnings.append(warning)

    # --- advisor ---------------------------------------------------------------------------
    async def append_turn(self, chat_id: str, role: str, content: str) -> None:
        self.turns.setdefault(chat_id, []).append(
            ConversationTurn(
                chat_id=chat_id, role=role, content=content,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def recent_turns(self, chat_id: str, limit: int = 12) -> list[ConversationTurn]:
        return (self.turns.get(chat_id) or [])[-limit:]

    # --- field reports ---------------------------------------------------------------------
    async def add_field_report(self, report: FieldReport) -> FieldReport:
        self.field_reports.append(report)
        return report

    async def list_field_reports(
        self, commune_code: str | None = None, limit: int = 20
    ) -> list[FieldReport]:
        reports = [
            r for r in self.field_reports
            if commune_code is None or r.commune_code == commune_code
        ]
        reports.sort(key=lambda r: r.reported_at, reverse=True)  # newest first
        return reports[:limit]

    async def add_agent_run(self, run: AgentRun) -> AgentRun:
        self.agent_runs[run.id] = run
        return run

    async def update_agent_run(self, run: AgentRun) -> None:
        self.agent_runs[run.id] = run

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        return self.agent_runs.get(run_id)

    async def list_agent_runs(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[AgentRun]:
        runs = [
            r for r in self.agent_runs.values()
            if status is None or r.status.value == status
        ]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]
