"""Firestore Native repository adapter (production).

Collections mirror the ERD; observations live in a per-station subcollection
(`observations/{station_id}/points/{recorded_at}`) so hydrograph range queries
need no composite index. The sync client is wrapped in `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .config import DATA_DIR_DEFAULT
from .models import (
    AgentRun,
    AgentRunStatus,
    Commune,
    CommuneCalibration,
    CommuneRisk,
    ConversationTurn,
    CropType,
    FieldReport,
    FloodReason,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    Subscription,
    TelemetryWarning,
    WeatherSnapshot,
)
from .stations import StationConfig, load_stations

_BATCH_LIMIT = 450


async def _run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    return date.fromisoformat(str(val))


def _subscription_from_dict(data: dict[str, Any]) -> Subscription:
    raw_crop_type = data.get("crop_type") or CropType.RICE.value
    return Subscription(
        id=data.get("id"),
        telegram_chat_id=data["telegram_chat_id"],
        commune_id=data["commune_id"],
        crop_type=CropType(raw_crop_type),
        crop_stage=data.get("crop_stage"),
        planting_date=_parse_date(data.get("planting_date")),
        subscribed_at=data.get("subscribed_at"),
        last_notified_at=data.get("last_notified_at"),
        last_notified_risk_tier=RiskTier(data["last_notified_risk_tier"])
        if data.get("last_notified_risk_tier")
        else None,
    )


def _commune_risk_from_dict(code: str, data: dict[str, Any]) -> CommuneRisk:
    return CommuneRisk(
        commune_code=code,
        commune_name_kh=data.get("name_kh", ""),
        commune_name_en=data.get("name_en", ""),
        province=data.get("province_en"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        tier=RiskTier(data["current_risk_tier"]),
        score=int(data.get("risk_score", 0)),
        reason=FloodReason(data.get("risk_reason", "NONE")),
        lead_time_hours=data.get("lead_time_hours"),
        drivers=list(data.get("risk_drivers", [])),
        station_id=data.get("risk_station_id"),
        station_level_m=data.get("station_level_m"),
        forecast_tier=RiskTier(data["forecast_tier"]) if data.get("forecast_tier") else None,
        forecast_lead_days=data.get("forecast_lead_days"),
        estimated=bool(data.get("risk_estimated", False)),
        updated_at=data.get("risk_updated_at", datetime.now(timezone.utc)),
    )


class FirestoreRepository:
    def __init__(
        self,
        project: str | None,
        *,
        data_dir: Path | str | None = None,
        client: Any = None,
        fs_module: Any = None,
    ) -> None:
        if client is not None:
            self._client = client
            if fs_module is not None:
                self._fs = fs_module
            else:
                from google.cloud import firestore

                self._fs = firestore
        else:
            from google.cloud import firestore

            self._client = firestore.Client(project=project)
            self._fs = firestore
        self._data_dir = Path(data_dir) if data_dir is not None else DATA_DIR_DEFAULT

    async def init(self) -> None:
        # Firestore is schemaless; nothing to create. Verify connectivity cheaply.
        await _run(self._client.collection("meta").document("health").get)

    async def close(self) -> None:
        await _run(self._client.close)

    def _col(self, name: str):
        return self._client.collection(name)

    async def _batched(self, pairs: list[tuple[Any, dict]], *, merge: bool) -> None:
        for i in range(0, len(pairs), _BATCH_LIMIT):
            batch = self._client.batch()
            for ref, payload in pairs[i : i + _BATCH_LIMIT]:
                batch.set(ref, payload, merge=merge)
            await _run(batch.commit)

    # --- telemetry -------------------------------------------------------------
    async def seed_stations(self, stations: list[StationConfig]) -> None:
        pairs = [(self._col("hydro_stations").document(s.id), s.model_dump()) for s in stations]
        await self._batched(pairs, merge=True)

    async def save_observation(self, snapshot: StationSnapshot) -> None:
        doc_id = snapshot.recorded_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ref = (
            self._col("hydro_observations")
            .document(snapshot.station_id)
            .collection("points")
            .document(doc_id)
        )
        await _run(
            ref.set,
            {
                "station_id": snapshot.station_id,
                "recorded_at": snapshot.recorded_at,
                "water_level_m": snapshot.level_m,
                "rate_of_rise_m_per_hr": snapshot.rate_of_rise_m_per_hr,
                "rainfall_mm": snapshot.rain_mm,
                "is_stale_fallback": snapshot.is_stale_fallback,
                "source": snapshot.source,
                "fetched_at": self._fs.SERVER_TIMESTAMP,
            },
        )

    async def _station_meta(self, station_id: str) -> dict | None:
        doc = await _run(self._col("hydro_stations").document(station_id).get)
        return doc.to_dict() if doc.exists else None

    async def latest_observation(self, station_id: str) -> StationSnapshot | None:
        meta = await self._station_meta(station_id)
        if not meta:
            return None
        points = self._col("hydro_observations").document(station_id).collection("points")
        query = points.order_by("recorded_at", direction=self._fs.Query.DESCENDING).limit(1)
        docs = await _run(lambda: list(query.stream()))
        if not docs:
            return None
        data = docs[0].to_dict()
        fetched = data.get("fetched_at") or data["recorded_at"]
        staleness = int((datetime.now(timezone.utc) - fetched).total_seconds() // 60)
        return StationSnapshot(
            station_id=station_id,
            name=meta.get("name_en") or station_id,
            river=meta.get("river") or "unknown",
            level_m=data["water_level_m"],
            alarm_stage_m=meta["alarm_stage_m"],
            flood_stage_m=meta["flood_stage_m"],
            rate_of_rise_m_per_hr=data.get("rate_of_rise_m_per_hr", 0.0),
            recorded_at=data["recorded_at"],
            rain_mm=data.get("rainfall_mm"),
            is_stale_fallback=data.get("is_stale_fallback", False),
            source=data.get("source", "live"),
            staleness_minutes=staleness,
        )

    async def telemetry_series(
        self, station_id: str, hours: int
    ) -> list[tuple[datetime, float, float | None]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        points = self._col("hydro_observations").document(station_id).collection("points")
        query = (
            points.where(filter=self._fs.FieldFilter("recorded_at", ">=", cutoff))
            .order_by("recorded_at")
        )
        docs = await _run(lambda: list(query.stream()))
        out: list[tuple[datetime, float, float | None]] = []
        for d in docs:
            data = d.to_dict()
            out.append((data["recorded_at"], data["water_level_m"], data.get("rainfall_mm")))
        return out

    async def save_failover_offset(
        self, station_id: str, fallback_id: str, offset_m: float
    ) -> None:
        await _run(
            self._col("station_failover_offsets").document(station_id).set,
            {
                "station_id": station_id,
                "fallback_id": fallback_id,
                "offset_m": offset_m,
                "computed_at": self._fs.SERVER_TIMESTAMP,
            },
        )

    async def get_failover_offset(self, station_id: str) -> float | None:
        doc = await _run(self._col("station_failover_offsets").document(station_id).get)
        return doc.to_dict().get("offset_m") if doc.exists else None

    async def last_sync_age_minutes(self) -> int | None:
        station_ids = list(load_stations(str(self._data_dir)).keys())
        min_age_sec: float | None = None
        now = datetime.now(timezone.utc)
        for s in station_ids:
            points = self._col("hydro_observations").document(s).collection("points")
            query = points.order_by("recorded_at", direction=self._fs.Query.DESCENDING).limit(1)
            docs = await _run(lambda q=query: list(q.stream()))
            if docs:
                data = docs[0].to_dict()
                fetched = data.get("fetched_at") or data["recorded_at"]
                age_sec = max(0.0, (now - fetched).total_seconds())
                if min_age_sec is None or age_sec < min_age_sec:
                    min_age_sec = age_sec
        return int(min_age_sec // 60) if min_age_sec is not None else None

    # --- weather ------------------------------------------------------------------
    async def save_weather(self, forecast: WeatherSnapshot) -> None:
        await _run(
            self._col("weather_forecasts").document(forecast.province_code).set,
            forecast.model_dump(mode="json"),
        )

    async def latest_weather_by_province(self) -> dict[str, WeatherSnapshot]:
        docs = await _run(lambda: list(self._col("weather_forecasts").stream()))
        out: dict[str, WeatherSnapshot] = {}
        for doc in docs:
            data = doc.to_dict()
            out[data["province_code"]] = WeatherSnapshot(**data)
        return out

    # --- communes & risk ------------------------------------------------------------
    async def seed_communes(self, communes: list[Commune]) -> int:
        pairs = [
            (self._col("communes").document(c.code), c.model_dump(mode="json")) for c in communes
        ]
        await self._batched(pairs, merge=True)
        return len(communes)

    async def commune_count(self) -> int:
        query = self._col("communes").count()
        result = await _run(query.get)
        return int(result[0][0].value)

    async def get_commune(self, code: str) -> Commune | None:
        doc = await _run(self._col("communes").document(code).get)
        if not doc.exists:
            return None
        data = doc.to_dict()
        return Commune(**{k: v for k, v in data.items() if k in Commune.model_fields})

    async def list_communes(self) -> list[Commune]:
        docs = await _run(lambda: list(self._col("communes").stream()))
        return [
            Commune(**{k: v for k, v in d.to_dict().items() if k in Commune.model_fields})
            for d in docs
        ]

    async def save_commune_risks(self, risks: list[CommuneRisk]) -> None:
        pairs = []
        for r in risks:
            payload: dict[str, Any] = {
                "current_risk_tier": r.tier.value,
                "risk_score": r.score,
                "risk_reason": r.reason.value,
                "lead_time_hours": r.lead_time_hours,
                "risk_drivers": r.drivers,
                "risk_station_id": r.station_id,
                "station_level_m": r.station_level_m,
                "forecast_tier": r.forecast_tier.value if r.forecast_tier else None,
                "forecast_lead_days": r.forecast_lead_days,
                "risk_estimated": r.estimated,
                "risk_updated_at": r.updated_at,
                "has_risk": True,
            }
            if r.lat is not None:
                payload["lat"] = r.lat
            if r.lng is not None:
                payload["lng"] = r.lng
            pairs.append((self._col("communes").document(r.commune_code), payload))
        await self._batched(pairs, merge=True)

    async def risk_map(self, province: str | None = None) -> list[CommuneRisk]:
        query = self._col("communes").where(filter=self._fs.FieldFilter("has_risk", "==", True))
        if province:
            query = query.where(filter=self._fs.FieldFilter("province_en", "==", province.strip()))
        docs = await _run(lambda: list(query.stream()))
        risks = [_commune_risk_from_dict(doc.id, doc.to_dict()) for doc in docs]
        risks.sort(key=lambda r: (-r.score, r.commune_code))
        return risks

    async def get_commune_risk(self, code: str) -> CommuneRisk | None:
        doc = await _run(self._col("communes").document(code).get)
        if not doc.exists:
            return None
        data = doc.to_dict()
        if not data.get("current_risk_tier"):
            return None
        return _commune_risk_from_dict(code, data)

    # --- subscriptions ------------------------------------------------------------------
    async def upsert_subscription(
        self,
        chat_id: str,
        commune_id: str,
        crop_stage: str | None,
        crop_type: str = "RICE",
        planting_date: date | None = None,
    ) -> Subscription:
        doc_id = f"{chat_id}_{commune_id}"
        ref = self._col("commune_subscriptions").document(doc_id)
        existing = await _run(ref.get)
        payload: dict[str, Any] = {
            "telegram_chat_id": chat_id,
            "commune_id": commune_id,
            "crop_type": CropType(crop_type).value,
            "subscribed_at": self._fs.SERVER_TIMESTAMP,
        }
        if crop_stage or not existing.exists:
            payload["crop_stage"] = crop_stage
        if planting_date is not None:
            payload["planting_date"] = planting_date.isoformat()
        elif not existing.exists:
            payload["planting_date"] = None
        await _run(ref.set, payload, merge=True)
        doc = await _run(ref.get)
        return _subscription_from_dict(doc.to_dict())

    async def remove_subscription(self, chat_id: str, commune_id: str) -> bool:
        ref = self._col("commune_subscriptions").document(f"{chat_id}_{commune_id}")
        doc = await _run(ref.get)
        if not doc.exists:
            return False
        await _run(ref.delete)
        return True

    async def _subscriptions_where(self, field: str, value: str) -> list[Subscription]:
        query = self._col("commune_subscriptions").where(
            filter=self._fs.FieldFilter(field, "==", value)
        )
        docs = await _run(lambda: list(query.stream()))
        return [_subscription_from_dict(doc.to_dict()) for doc in docs]

    async def subscriptions_for_commune(self, commune_id: str) -> list[Subscription]:
        return await self._subscriptions_where("commune_id", commune_id)

    async def subscriptions_for_chat(self, chat_id: str) -> list[Subscription]:
        return await self._subscriptions_where("telegram_chat_id", chat_id)

    async def list_all_subscriptions(self) -> list[Subscription]:
        docs = await _run(lambda: list(self._col("commune_subscriptions").stream()))
        return [_subscription_from_dict(doc.to_dict()) for doc in docs]

    async def touch_notified(
        self, chat_id: str, commune_id: str, tier: RiskTier, at: datetime
    ) -> None:
        await _run(
            self._col("commune_subscriptions").document(f"{chat_id}_{commune_id}").set,
            {
                "last_notified_at": self._fs.SERVER_TIMESTAMP,
                "last_notified_risk_tier": tier.value,
            },
            merge=True,
        )

    # --- sentinel -------------------------------------------------------------------------
    async def save_patrol_run(self, run: PatrolRun) -> PatrolRun:
        payload = run.model_dump(mode="json", exclude={"id"})
        _, ref = await _run(self._col("sentinel_patrol_runs").add, payload)
        return run.model_copy(update={"id": ref.id})

    async def save_sentinel_alert(self, alert: SentinelAlert) -> None:
        await _run(
            self._col("sentinel_alerts").add,
            alert.model_dump(mode="json", exclude={"id"}),
        )

    async def last_sentinel_alert(self, commune_id: str) -> SentinelAlert | None:
        query = (
            self._col("sentinel_alerts")
            .where(filter=self._fs.FieldFilter("commune_id", "==", commune_id))
            .order_by("dispatched_at", direction=self._fs.Query.DESCENDING)
            .limit(1)
        )
        docs = await _run(lambda: list(query.stream()))
        if not docs:
            return None
        doc = docs[0]
        raw = {k: v for k, v in doc.to_dict().items() if k in SentinelAlert.model_fields}
        raw.setdefault("id", doc.id)
        return SentinelAlert(**raw)

    async def recent_sentinel_alerts(self, limit: int = 50) -> list[SentinelAlert]:
        query = (
            self._col("sentinel_alerts")
            .order_by("dispatched_at", direction=self._fs.Query.DESCENDING)
            .limit(limit)
        )
        docs = await _run(lambda: list(query.stream()))
        out: list[SentinelAlert] = []
        for doc in docs:
            raw = {k: v for k, v in doc.to_dict().items() if k in SentinelAlert.model_fields}
            raw.setdefault("id", doc.id)
            out.append(SentinelAlert(**raw))
        return out

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
        await _run(
            self._col("alert_dispatches").add,
            {
                "commune_id": commune_id,
                "risk_tier": tier.value,
                "directive_type": directive_family,
                "khmer_bulletin_text": bulletin_kh,
                "audio_storage_uri": audio_uri,
                "audio_duration_seconds": audio_duration,
                "recipients_count": recipients,
                "dispatched_at": self._fs.SERVER_TIMESTAMP,
            },
        )

    async def save_telemetry_warning(self, warning: TelemetryWarning) -> None:
        await _run(
            self._col("telemetry_warnings").add, warning.model_dump(mode="json")
        )

    # --- advisor ----------------------------------------------------------------------------
    async def append_turn(self, chat_id: str, role: str, content: str) -> None:
        await _run(
            self._col("conversation_turns").add,
            {"chat_id": chat_id, "role": role, "content": content,
             "created_at": self._fs.SERVER_TIMESTAMP},
        )

    async def recent_turns(self, chat_id: str, limit: int = 12) -> list[ConversationTurn]:
        query = (
            self._col("conversation_turns")
            .where(filter=self._fs.FieldFilter("chat_id", "==", chat_id))
            .order_by("created_at", direction=self._fs.Query.DESCENDING)
            .limit(limit)
        )
        docs = await _run(lambda: list(query.stream()))
        return [
            ConversationTurn(
                chat_id=d.to_dict()["chat_id"],
                role=d.to_dict()["role"],
                content=d.to_dict()["content"],
                created_at=d.to_dict().get("created_at"),
            )
            for d in reversed(docs)
        ]

    # --- field reports ------------------------------------------------------------------------
    async def add_field_report(self, report: FieldReport) -> FieldReport:
        await _run(
            self._col("field_reports").document(report.id).set,
            report.model_dump(mode="json"),
        )
        return report

    async def list_field_reports(
        self, commune_code: str | None = None, limit: int = 20
    ) -> list[FieldReport]:
        query = self._col("field_reports")
        if commune_code:
            query = query.where(filter=self._fs.FieldFilter("commune_code", "==", commune_code))
        query = query.order_by("reported_at", direction=self._fs.Query.DESCENDING).limit(limit)
        docs = await _run(lambda: list(query.stream()))
        return [
            FieldReport(**{k: v for k, v in d.to_dict().items() if k in FieldReport.model_fields})
            for d in docs
        ]

    # --- watch runs ----------------------------------------------------------------
    async def add_agent_run(self, run: AgentRun) -> AgentRun:
        await _run(
            self._col("agent_runs").document(run.id).set,
            run.model_dump(mode="json"),
        )
        return run

    async def update_agent_run(self, run: AgentRun) -> None:
        await _run(
            self._col("agent_runs").document(run.id).set,
            run.model_dump(mode="json"),
        )

    async def claim_agent_run_for_publish(self, run_id: str) -> AgentRun | None:
        ref = self._col("agent_runs").document(run_id)

        def _tx() -> AgentRun | None:
            transaction = self._client.transaction()

            @self._fs.transactional
            def _claim(tx) -> AgentRun | None:
                snap = ref.get(transaction=tx)
                if not getattr(snap, "exists", False):
                    return None
                data = snap.to_dict()
                if data.get("status") != AgentRunStatus.PENDING_APPROVAL.value:
                    return None
                updated = dict(data)
                updated["status"] = AgentRunStatus.PUBLISHING.value
                tx.set(ref, updated)
                return AgentRun.model_validate(updated)

            return _claim(transaction)

        return await _run(_tx)

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        doc = await _run(self._col("agent_runs").document(run_id).get)
        if not getattr(doc, "exists", False):
            return None
        return AgentRun.model_validate(doc.to_dict())

    async def list_agent_runs(
        self, *, status: str | None = None, limit: int = 20
    ) -> list[AgentRun]:
        query = self._col("agent_runs")
        if status:
            query = query.where(filter=self._fs.FieldFilter("status", "==", status))
        query = query.order_by("created_at", direction=self._fs.Query.DESCENDING).limit(limit)
        docs = await _run(lambda: list(query.stream()))
        return [AgentRun.model_validate(d.to_dict()) for d in docs]

    # --- calibration ---------------------------------------------------------------
    async def save_commune_calibration(self, cal: CommuneCalibration) -> None:
        await _run(
            self._col("commune_calibrations").document(cal.commune_code).set,
            cal.model_dump(mode="json"),
        )

    async def list_commune_calibrations(self) -> dict[str, CommuneCalibration]:
        docs = await _run(lambda: list(self._col("commune_calibrations").stream()))
        out: dict[str, CommuneCalibration] = {}
        for doc in docs:
            cal = CommuneCalibration.model_validate(doc.to_dict())
            out[cal.commune_code] = cal
        return out
