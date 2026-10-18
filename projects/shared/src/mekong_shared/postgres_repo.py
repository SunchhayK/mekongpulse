"""PostgreSQL repository adapter (development, staging).

Tables mirror the ERD (§3.1) plus operational tables (failover offsets,
telemetry warnings, conversation turns). Schema is created idempotently on
init(); the local container is `pg_db` per the repo operating rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import asyncpg

from .models import (
    AgentRun,
    AgentRunStatus,
    Commune,
    CommuneRisk,
    ConversationTurn,
    FieldReport,
    FieldReportStatus,
    FloodReason,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    Subscription,
    TelemetryWarning,
    WeatherSnapshot,
)
from .stations import StationConfig

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hydro_stations(
  id text PRIMARY KEY,
  name text NOT NULL,
  name_kh text,
  river text NOT NULL,
  latitude double precision,
  longitude double precision,
  alarm_stage_m double precision NOT NULL,
  flood_stage_m double precision NOT NULL,
  zero_gauge_elevation_m double precision,
  fallback_id text
);
CREATE TABLE IF NOT EXISTS hydro_observations(
  id bigserial PRIMARY KEY,
  station_id text NOT NULL REFERENCES hydro_stations(id),
  recorded_at timestamptz NOT NULL,
  water_level_m double precision NOT NULL,
  rate_of_rise_m_per_hr double precision NOT NULL DEFAULT 0,
  rainfall_mm double precision,
  temperature_c double precision,
  is_stale_fallback boolean NOT NULL DEFAULT false,
  source text NOT NULL DEFAULT 'live',
  fetched_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (station_id, recorded_at)
);
CREATE INDEX IF NOT EXISTS idx_observations_station_time
  ON hydro_observations(station_id, recorded_at DESC);
CREATE TABLE IF NOT EXISTS station_failover_offsets(
  station_id text PRIMARY KEY,
  fallback_id text NOT NULL,
  offset_m double precision NOT NULL,
  samples integer,
  computed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS weather_forecasts(
  id bigserial PRIMARY KEY,
  province_code text NOT NULL,
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  forecast_time timestamptz NOT NULL,
  precipitation_48h_mm double precision NOT NULL,
  precipitation_7d_mm double precision NOT NULL,
  max_rain_24h_mm double precision NOT NULL,
  soil_moisture_pct double precision NOT NULL,
  fetched_at timestamptz NOT NULL,
  UNIQUE (province_code, forecast_time)
);
CREATE TABLE IF NOT EXISTS communes(
  code text PRIMARY KEY,
  name_kh text NOT NULL,
  name_en text NOT NULL,
  district_code text,
  district_kh text,
  district_en text,
  province_code text,
  province_kh text,
  province_en text,
  latitude double precision,
  longitude double precision,
  ground_elevation_m double precision,
  nearest_station_id text REFERENCES hydro_stations(id),
  distance_to_station_km double precision,
  has_boundary boolean NOT NULL DEFAULT false,
  current_risk_tier text,
  risk_score integer,
  risk_reason text,
  lead_time_hours integer,
  risk_drivers jsonb,
  risk_station_id text,
  risk_estimated boolean,
  risk_updated_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_communes_risk ON communes(current_risk_tier, province_en);
CREATE TABLE IF NOT EXISTS commune_subscriptions(
  id bigserial PRIMARY KEY,
  telegram_chat_id text NOT NULL,
  commune_id text NOT NULL REFERENCES communes(code),
  crop_stage text,
  subscribed_at timestamptz NOT NULL DEFAULT now(),
  last_notified_at timestamptz,
  last_notified_risk_tier text,
  UNIQUE (telegram_chat_id, commune_id)
);
CREATE TABLE IF NOT EXISTS sentinel_patrol_runs(
  id bigserial PRIMARY KEY,
  run_at timestamptz NOT NULL DEFAULT now(),
  stations_polled integer NOT NULL,
  communes_evaluated integer NOT NULL,
  alerts_dispatched_count integer NOT NULL,
  execution_duration_ms integer NOT NULL
);
CREATE TABLE IF NOT EXISTS sentinel_alerts(
  id bigserial PRIMARY KEY,
  patrol_run_id bigint REFERENCES sentinel_patrol_runs(id),
  commune_id text NOT NULL REFERENCES communes(code),
  station_id text,
  risk_tier text NOT NULL,
  lead_time_hours integer,
  directive_title text,
  bulletin_text text,
  audio_url text,
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  recipients_count integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sentinel_alerts_commune_time
  ON sentinel_alerts(commune_id, dispatched_at DESC);
CREATE TABLE IF NOT EXISTS alert_dispatches(
  id bigserial PRIMARY KEY,
  commune_id text NOT NULL,
  risk_tier text NOT NULL,
  directive_type text NOT NULL,
  khmer_bulletin_text text,
  audio_storage_uri text,
  audio_duration_seconds double precision,
  recipients_count integer NOT NULL DEFAULT 0,
  dispatched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS telemetry_warnings(
  id bigserial PRIMARY KEY,
  station_id text,
  kind text NOT NULL,
  detail text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversation_turns(
  id bigserial PRIMARY KEY,
  chat_id text NOT NULL,
  role text NOT NULL,
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_turns_chat ON conversation_turns(chat_id, id DESC);
CREATE TABLE IF NOT EXISTS field_reports(
  id text PRIMARY KEY,
  commune_code text NOT NULL REFERENCES communes(code),
  status text NOT NULL,
  note text,
  reporter_label text,
  source text NOT NULL DEFAULT 'web',
  reported_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_field_reports_commune_time
  ON field_reports(commune_code, reported_at DESC);
CREATE TABLE IF NOT EXISTS agent_runs(
  id text PRIMARY KEY,
  commune_code text NOT NULL,
  commune_name_kh text,
  commune_name_en text,
  trigger text NOT NULL,
  previous_tier text,
  current_tier text NOT NULL,
  status text NOT NULL,
  rationale text NOT NULL DEFAULT '',
  draft_khmer text NOT NULL,
  draft_english text,
  tool_calls jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  approved_at timestamptz,
  approved_by text,
  rejected_at timestamptz,
  published_at timestamptz,
  published_message_id bigint,
  published_text text,
  error text
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_time
  ON agent_runs(status, created_at DESC);
"""

_OBS_COLS = """
  o.recorded_at, o.water_level_m, o.rate_of_rise_m_per_hr, o.is_stale_fallback, o.source,
  o.fetched_at, s.id AS station_id, s.name, s.river, s.alarm_stage_m, s.flood_stage_m
"""

# Latest gauge reading per risk row -> CommuneRisk.station_level_m. Keeps the
# Postgres read path in parity with the in-memory repository, which retains the
# classify-time level.
_RISK_OBSERVATION_JOIN = """
  LEFT JOIN LATERAL (
    SELECT water_level_m FROM hydro_observations o
    WHERE o.station_id = c.risk_station_id
    ORDER BY o.recorded_at DESC LIMIT 1
  ) o ON true
"""


def _snapshot_from_row(row: asyncpg.Record) -> StationSnapshot:
    fetched = row["fetched_at"] or row["recorded_at"]
    staleness = int((datetime.now(timezone.utc) - fetched).total_seconds() // 60)
    source = row["source"] or "live"
    return StationSnapshot(
        station_id=row["station_id"],
        name=row["name"],
        river=row["river"],
        level_m=row["water_level_m"],
        alarm_stage_m=row["alarm_stage_m"],
        flood_stage_m=row["flood_stage_m"],
        rate_of_rise_m_per_hr=row["rate_of_rise_m_per_hr"],
        recorded_at=row["recorded_at"],
        is_stale_fallback=row["is_stale_fallback"],
        source=source,
        staleness_minutes=staleness,
    )


class PostgresRepository:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresRepository.init() has not been called")
        return self._pool

    # --- telemetry ----------------------------------------------------------
    async def seed_stations(self, stations: list[StationConfig]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO hydro_stations(id, name, name_kh, river, latitude, longitude,
                  alarm_stage_m, flood_stage_m, zero_gauge_elevation_m, fallback_id)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (id) DO UPDATE SET
                  name=EXCLUDED.name, name_kh=EXCLUDED.name_kh, river=EXCLUDED.river,
                  latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                  alarm_stage_m=EXCLUDED.alarm_stage_m, flood_stage_m=EXCLUDED.flood_stage_m,
                  zero_gauge_elevation_m=EXCLUDED.zero_gauge_elevation_m,
                  fallback_id=EXCLUDED.fallback_id
                """,
                [
                    (
                        s.id, s.name_en, s.name_kh, s.river, s.lat, s.lng,
                        s.alarm_stage_m, s.flood_stage_m, s.zero_gauge_elevation_m, s.fallback_id,
                    )
                    for s in stations
                ],
            )

    async def save_observation(self, snapshot: StationSnapshot) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hydro_observations(station_id, recorded_at, water_level_m,
                  rate_of_rise_m_per_hr, rainfall_mm, is_stale_fallback, source, fetched_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,now())
                ON CONFLICT (station_id, recorded_at) DO UPDATE SET
                  water_level_m=EXCLUDED.water_level_m,
                  rate_of_rise_m_per_hr=EXCLUDED.rate_of_rise_m_per_hr,
                  is_stale_fallback=EXCLUDED.is_stale_fallback, source=EXCLUDED.source,
                  fetched_at=now()
                """,
                snapshot.station_id, snapshot.recorded_at, snapshot.level_m,
                snapshot.rate_of_rise_m_per_hr, None, snapshot.is_stale_fallback, snapshot.source,
            )

    async def latest_observation(self, station_id: str) -> StationSnapshot | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_OBS_COLS}
                FROM hydro_observations o JOIN hydro_stations s ON s.id = o.station_id
                WHERE o.station_id = $1 ORDER BY o.recorded_at DESC LIMIT 1
                """,
                station_id,
            )
        return _snapshot_from_row(row) if row else None

    async def telemetry_series(
        self, station_id: str, hours: int
    ) -> list[tuple[datetime, float, float | None]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT recorded_at, water_level_m, rainfall_mm FROM hydro_observations
                WHERE station_id = $1 AND recorded_at >= now() - make_interval(hours => $2)
                ORDER BY recorded_at ASC
                """,
                station_id, hours,
            )
        return [(r["recorded_at"], r["water_level_m"], r["rainfall_mm"]) for r in rows]

    async def save_failover_offset(
        self, station_id: str, fallback_id: str, offset_m: float
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO station_failover_offsets(station_id, fallback_id, offset_m, computed_at)
                VALUES($1,$2,$3,now())
                ON CONFLICT (station_id) DO UPDATE SET
                  fallback_id=EXCLUDED.fallback_id, offset_m=EXCLUDED.offset_m,
                  computed_at=now()
                """,
                station_id, fallback_id, offset_m,
            )

    async def get_failover_offset(self, station_id: str) -> float | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT offset_m FROM station_failover_offsets WHERE station_id=$1", station_id
            )

    async def last_sync_age_minutes(self) -> int | None:
        async with self.pool.acquire() as conn:
            age = await conn.fetchval(
                "SELECT EXTRACT(EPOCH FROM (now() - max(fetched_at)))/60 FROM hydro_observations"
            )
        return int(age) if age is not None else None

    # --- weather ------------------------------------------------------------
    async def save_weather(self, forecast: WeatherSnapshot) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO weather_forecasts(province_code, latitude, longitude, forecast_time,
                  precipitation_48h_mm, precipitation_7d_mm, max_rain_24h_mm, soil_moisture_pct, fetched_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (province_code, forecast_time) DO UPDATE SET
                  precipitation_48h_mm=EXCLUDED.precipitation_48h_mm,
                  precipitation_7d_mm=EXCLUDED.precipitation_7d_mm,
                  max_rain_24h_mm=EXCLUDED.max_rain_24h_mm,
                  soil_moisture_pct=EXCLUDED.soil_moisture_pct, fetched_at=EXCLUDED.fetched_at
                """,
                forecast.province_code, forecast.latitude, forecast.longitude,
                forecast.fetched_at, forecast.precipitation_48h_mm,
                forecast.precipitation_7d_mm, forecast.max_rain_24h_mm,
                forecast.soil_moisture_pct, forecast.fetched_at,
            )

    async def latest_weather_by_province(self) -> dict[str, WeatherSnapshot]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (province_code) * FROM weather_forecasts
                ORDER BY province_code, fetched_at DESC
                """
            )
        return {
            r["province_code"]: WeatherSnapshot(
                province_code=r["province_code"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                precipitation_48h_mm=r["precipitation_48h_mm"],
                precipitation_7d_mm=r["precipitation_7d_mm"],
                max_rain_24h_mm=r["max_rain_24h_mm"],
                soil_moisture_pct=r["soil_moisture_pct"],
                fetched_at=r["fetched_at"],
            )
            for r in rows
        }

    # --- communes & risk ------------------------------------------------------
    async def seed_communes(self, communes: list[Commune]) -> int:
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO communes(code, name_kh, name_en, district_code, district_kh, district_en,
                  province_code, province_kh, province_en, latitude, longitude, ground_elevation_m,
                  nearest_station_id, distance_to_station_km, has_boundary)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT (code) DO UPDATE SET
                  name_kh=EXCLUDED.name_kh, name_en=EXCLUDED.name_en,
                  district_code=EXCLUDED.district_code, district_kh=EXCLUDED.district_kh,
                  district_en=EXCLUDED.district_en, province_code=EXCLUDED.province_code,
                  province_kh=EXCLUDED.province_kh, province_en=EXCLUDED.province_en,
                  latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                  ground_elevation_m=EXCLUDED.ground_elevation_m,
                  nearest_station_id=EXCLUDED.nearest_station_id,
                  distance_to_station_km=EXCLUDED.distance_to_station_km,
                  has_boundary=EXCLUDED.has_boundary
                """,
                [
                    (
                        c.code, c.name_kh, c.name_en, c.district_code, c.district_kh, c.district_en,
                        c.province_code, c.province_kh, c.province_en, c.lat, c.lng,
                        c.ground_elevation_m, c.nearest_station_id, c.distance_to_station_km,
                        c.has_boundary,
                    )
                    for c in communes
                ],
            )
        return len(communes)

    async def commune_count(self) -> int:
        async with self.pool.acquire() as conn:
            return int(await conn.fetchval("SELECT count(*) FROM communes"))

    async def get_commune(self, code: str) -> Commune | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM communes WHERE code=$1", code)
        return _commune_from_row(row) if row else None

    async def list_communes(self) -> list[Commune]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM communes ORDER BY code")
        return [_commune_from_row(r) for r in rows]

    async def save_commune_risks(self, risks: list[CommuneRisk]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                UPDATE communes SET current_risk_tier=$2, risk_score=$3, risk_reason=$4,
                  lead_time_hours=$5, risk_drivers=$6::jsonb, risk_station_id=$7,
                  risk_estimated=$8, risk_updated_at=$9
                WHERE code=$1
                """,
                [
                    (
                        r.commune_code, r.tier.value, r.score, r.reason.value, r.lead_time_hours,
                        json.dumps(r.drivers), r.station_id, r.estimated, r.updated_at,
                    )
                    for r in risks
                ],
            )

    async def risk_map(self, province: str | None = None) -> list[CommuneRisk]:
        query = f"""
            SELECT c.*, o.water_level_m AS station_level_m
            FROM communes c
            {_RISK_OBSERVATION_JOIN}
            WHERE c.current_risk_tier IS NOT NULL
        """
        args: list = []
        if province:
            query += " AND (c.province_en ILIKE $1 OR c.province_kh = $2)"
            args = [f"%{province.strip()}%", province.strip()]
        query += " ORDER BY c.risk_score DESC NULLS LAST, c.code"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [_risk_from_row(r) for r in rows]

    async def get_commune_risk(self, code: str) -> CommuneRisk | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT c.*, o.water_level_m AS station_level_m
                FROM communes c
                {_RISK_OBSERVATION_JOIN}
                WHERE c.code=$1 AND c.current_risk_tier IS NOT NULL
                """,
                code,
            )
        return _risk_from_row(row) if row else None

    # --- subscriptions ---------------------------------------------------------
    async def upsert_subscription(
        self, chat_id: str, commune_id: str, crop_stage: str | None
    ) -> Subscription:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO commune_subscriptions(telegram_chat_id, commune_id, crop_stage)
                VALUES($1,$2,$3)
                ON CONFLICT (telegram_chat_id, commune_id) DO UPDATE SET
                  crop_stage=COALESCE(EXCLUDED.crop_stage, commune_subscriptions.crop_stage)
                RETURNING *
                """,
                chat_id, commune_id, crop_stage,
            )
        return _subscription_from_row(row)

    async def remove_subscription(self, chat_id: str, commune_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM commune_subscriptions WHERE telegram_chat_id=$1 AND commune_id=$2",
                chat_id, commune_id,
            )
        return result.endswith(" 1")

    async def subscriptions_for_commune(self, commune_id: str) -> list[Subscription]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM commune_subscriptions WHERE commune_id=$1 ORDER BY id", commune_id
            )
        return [_subscription_from_row(r) for r in rows]

    async def subscriptions_for_chat(self, chat_id: str) -> list[Subscription]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM commune_subscriptions WHERE telegram_chat_id=$1 ORDER BY id", chat_id
            )
        return [_subscription_from_row(r) for r in rows]

    async def touch_notified(
        self, chat_id: str, commune_id: str, tier: RiskTier, at: datetime
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE commune_subscriptions SET last_notified_at=$3, last_notified_risk_tier=$4
                WHERE telegram_chat_id=$1 AND commune_id=$2
                """,
                chat_id, commune_id, at, tier.value,
            )

    # --- sentinel ----------------------------------------------------------------
    async def save_patrol_run(self, run: PatrolRun) -> PatrolRun:
        async with self.pool.acquire() as conn:
            run_id = await conn.fetchval(
                """
                INSERT INTO sentinel_patrol_runs(run_at, stations_polled, communes_evaluated,
                  alerts_dispatched_count, execution_duration_ms)
                VALUES($1,$2,$3,$4,$5) RETURNING id
                """,
                run.run_at, run.stations_polled, run.communes_evaluated,
                run.alerts_dispatched_count, run.execution_duration_ms,
            )
        return run.model_copy(update={"id": run_id})

    async def save_sentinel_alert(self, alert: SentinelAlert) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sentinel_alerts(patrol_run_id, commune_id, station_id, risk_tier,
                  lead_time_hours, directive_title, bulletin_text, audio_url, dispatched_at, recipients_count)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                alert.patrol_run_id, alert.commune_id, alert.station_id, alert.risk_tier.value,
                alert.lead_time_hours, alert.directive_title, alert.bulletin_text, alert.audio_url,
                alert.dispatched_at, alert.recipients_count,
            )

    async def last_sentinel_alert(self, commune_id: str) -> SentinelAlert | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM sentinel_alerts WHERE commune_id=$1
                ORDER BY dispatched_at DESC LIMIT 1
                """,
                commune_id,
            )
        return _sentinel_alert_from_row(row) if row else None

    async def recent_sentinel_alerts(self, limit: int = 50) -> list[SentinelAlert]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM sentinel_alerts ORDER BY dispatched_at DESC LIMIT $1", limit
            )
        return [_sentinel_alert_from_row(r) for r in rows]

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
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO alert_dispatches(commune_id, risk_tier, directive_type,
                  khmer_bulletin_text, audio_storage_uri, audio_duration_seconds, recipients_count)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                """,
                commune_id, tier.value, directive_family, bulletin_kh, audio_uri,
                audio_duration, recipients,
            )

    async def save_telemetry_warning(self, warning: TelemetryWarning) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO telemetry_warnings(station_id, kind, detail, created_at) VALUES($1,$2,$3,$4)",
                warning.station_id, warning.kind, warning.detail, warning.created_at,
            )

    # --- advisor ---------------------------------------------------------------
    async def append_turn(self, chat_id: str, role: str, content: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO conversation_turns(chat_id, role, content) VALUES($1,$2,$3)",
                chat_id, role, content,
            )

    async def recent_turns(self, chat_id: str, limit: int = 12) -> list[ConversationTurn]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM conversation_turns WHERE chat_id=$1 ORDER BY id DESC LIMIT $2",
                chat_id, limit,
            )
        return [
            ConversationTurn(chat_id=r["chat_id"], role=r["role"], content=r["content"],
                             created_at=r["created_at"])
            for r in reversed(rows)
        ]

    # --- field reports ------------------------------------------------------------
    async def add_field_report(self, report: FieldReport) -> FieldReport:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO field_reports(id, commune_code, status, note, reporter_label,
                  source, reported_at)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                """,
                report.id, report.commune_code, report.status.value, report.note,
                report.reporter_label, report.source, report.reported_at,
            )
        return report

    async def list_field_reports(
        self, commune_code: str | None = None, limit: int = 20
    ) -> list[FieldReport]:
        query = "SELECT * FROM field_reports"
        args: list = []
        if commune_code:
            query += " WHERE commune_code=$1"
            args.append(commune_code)
        query += f" ORDER BY reported_at DESC LIMIT ${len(args) + 1}"
        args.append(limit)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [_field_report_from_row(r) for r in rows]

    # --- watch runs ----------------------------------------------------------------
    async def add_agent_run(self, run: AgentRun) -> AgentRun:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_runs(id, commune_code, commune_name_kh, commune_name_en,
                  trigger, previous_tier, current_tier, status, rationale, draft_khmer,
                  draft_english, tool_calls, created_at, approved_at, approved_by,
                  rejected_at, published_at, published_message_id, published_text, error)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13,$14,$15,$16,$17,$18,$19,$20)
                """,
                run.id, run.commune_code, run.commune_name_kh, run.commune_name_en,
                run.trigger,
                run.previous_tier.value if run.previous_tier else None,
                run.current_tier.value, run.status.value, run.rationale, run.draft_khmer,
                run.draft_english, json.dumps(run.tool_calls), run.created_at,
                run.approved_at, run.approved_by, run.rejected_at, run.published_at,
                run.published_message_id, run.published_text, run.error,
            )
        return run

    async def update_agent_run(self, run: AgentRun) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_runs SET status=$2, rationale=$3, draft_khmer=$4,
                  draft_english=$5, tool_calls=$6::jsonb, approved_at=$7, approved_by=$8,
                  rejected_at=$9, published_at=$10, published_message_id=$11,
                  published_text=$12, error=$13
                WHERE id=$1
                """,
                run.id, run.status.value, run.rationale, run.draft_khmer,
                run.draft_english, json.dumps(run.tool_calls), run.approved_at,
                run.approved_by, run.rejected_at, run.published_at,
                run.published_message_id, run.published_text, run.error,
            )

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agent_runs WHERE id=$1", run_id)
        return _agent_run_from_row(row) if row else None

    async def list_agent_runs(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[AgentRun]:
        query = "SELECT * FROM agent_runs"
        args: list = []
        if status:
            query += " WHERE status=$1"
            args.append(status)
        query += f" ORDER BY created_at DESC LIMIT ${len(args) + 1}"
        args.append(limit)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [_agent_run_from_row(r) for r in rows]


def _commune_from_row(row: asyncpg.Record) -> Commune:
    return Commune(
        code=row["code"], name_kh=row["name_kh"], name_en=row["name_en"],
        district_code=row["district_code"], district_kh=row["district_kh"],
        district_en=row["district_en"], province_code=row["province_code"],
        province_kh=row["province_kh"], province_en=row["province_en"],
        lat=row["latitude"], lng=row["longitude"],
        ground_elevation_m=row["ground_elevation_m"],
        nearest_station_id=row["nearest_station_id"],
        distance_to_station_km=row["distance_to_station_km"],
        has_boundary=bool(row["has_boundary"]),
    )


def _risk_from_row(row: asyncpg.Record) -> CommuneRisk:
    drivers = row["risk_drivers"]
    if isinstance(drivers, str):
        drivers = json.loads(drivers)
    return CommuneRisk(
        commune_code=row["code"],
        commune_name_kh=row["name_kh"],
        commune_name_en=row["name_en"],
        province=row["province_en"],
        lat=row["latitude"],
        lng=row["longitude"],
        tier=RiskTier(row["current_risk_tier"]),
        score=int(row["risk_score"] or 0),
        reason=FloodReason(row["risk_reason"]) if row["risk_reason"] else FloodReason.NONE,
        lead_time_hours=row["lead_time_hours"],
        drivers=list(drivers or []),
        station_id=row["risk_station_id"],
        station_level_m=row["station_level_m"],
        estimated=bool(row["risk_estimated"]),
        updated_at=row["risk_updated_at"],
    )


def _subscription_from_row(row: asyncpg.Record) -> Subscription:
    return Subscription(
        id=row["id"],
        telegram_chat_id=row["telegram_chat_id"],
        commune_id=row["commune_id"],
        crop_stage=row["crop_stage"],
        subscribed_at=row["subscribed_at"],
        last_notified_at=row["last_notified_at"],
        last_notified_risk_tier=RiskTier(row["last_notified_risk_tier"])
        if row["last_notified_risk_tier"] else None,
    )


def _sentinel_alert_from_row(row: asyncpg.Record) -> SentinelAlert:
    return SentinelAlert(
        id=row["id"], patrol_run_id=row["patrol_run_id"], commune_id=row["commune_id"],
        station_id=row["station_id"], risk_tier=RiskTier(row["risk_tier"]),
        lead_time_hours=row["lead_time_hours"], directive_title=row["directive_title"] or "",
        bulletin_text=row["bulletin_text"] or "", audio_url=row["audio_url"],
        dispatched_at=row["dispatched_at"], recipients_count=row["recipients_count"],
    )


def _field_report_from_row(row: asyncpg.Record) -> FieldReport:
    return FieldReport(
        id=row["id"], commune_code=row["commune_code"],
        status=FieldReportStatus(row["status"]), note=row["note"],
        reporter_label=row["reporter_label"], source=row["source"],
        reported_at=row["reported_at"],
    )


def _agent_run_from_row(row: asyncpg.Record) -> AgentRun:
    tool_calls = row["tool_calls"]
    if isinstance(tool_calls, str):
        tool_calls = json.loads(tool_calls)
    return AgentRun(
        id=row["id"],
        commune_code=row["commune_code"],
        commune_name_kh=row["commune_name_kh"],
        commune_name_en=row["commune_name_en"],
        trigger=row["trigger"],
        previous_tier=RiskTier(row["previous_tier"]) if row["previous_tier"] else None,
        current_tier=RiskTier(row["current_tier"]),
        status=AgentRunStatus(row["status"]),
        rationale=row["rationale"] or "",
        draft_khmer=row["draft_khmer"],
        draft_english=row["draft_english"],
        tool_calls=list(tool_calls or []),
        created_at=row["created_at"],
        approved_at=row["approved_at"],
        approved_by=row["approved_by"],
        rejected_at=row["rejected_at"],
        published_at=row["published_at"],
        published_message_id=row["published_message_id"],
        published_text=row["published_text"],
        error=row["error"],
    )
