"""Firestore Native repository adapter (production).

Collections mirror the ERD; observations live in a per-station subcollection
(`observations/{station_id}/points/{recorded_at}`) so hydrograph range queries
need no composite index. The sync client is wrapped in `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .models import (
    Commune,
    CommuneRisk,
    ConversationTurn,
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

_BATCH_LIMIT = 450


async def _run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)


class FirestoreRepository:
    def __init__(self, project: str | None) -> None:
        from google.cloud import firestore

        self._client = firestore.Client(project=project)
        self._fs = firestore

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
        return [(d.to_dict()["recorded_at"], d.to_dict()["water_level_m"], None) for d in docs]

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
        latest = 0.0
        for s in ("019802", "020102", "033401", "033402"):
            points = self._col("hydro_observations").document(s).collection("points")
            query = points.order_by("recorded_at", direction=self._fs.Query.DESCENDING).limit(1)
            docs = await _run(lambda q=query: list(q.stream()))
            if docs:
                fetched = docs[0].to_dict().get("fetched_at") or docs[0].to_dict()["recorded_at"]
                latest = max(latest, (datetime.now(timezone.utc) - fetched).total_seconds())
        return int(latest // 60) if latest else None

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
            payload = {
                "current_risk_tier": r.tier.value,
                "risk_score": r.score,
                "risk_reason": r.reason.value,
                "lead_time_hours": r.lead_time_hours,
                "risk_drivers": r.drivers,
                "risk_station_id": r.station_id,
                "risk_estimated": r.estimated,
                "risk_updated_at": r.updated_at,
                "has_risk": True,
            }
            pairs.append((self._col("communes").document(r.commune_code), payload))
        await self._batched(pairs, merge=True)

    async def risk_map(self, province: str | None = None) -> list[CommuneRisk]:
        query = self._col("communes").where(filter=self._fs.FieldFilter("has_risk", "==", True))
        if province:
            query = query.where(filter=self._fs.FieldFilter("province_en", "==", province.strip()))
        docs = await _run(lambda: list(query.stream()))
        risks = []
        for doc in docs:
            data = doc.to_dict()
            risks.append(
                CommuneRisk(
                    commune_code=doc.id,
                    commune_name_kh=data.get("name_kh", ""),
                    commune_name_en=data.get("name_en", ""),
                    province=data.get("province_en"),
                    tier=RiskTier(data["current_risk_tier"]),
                    score=int(data.get("risk_score", 0)),
                    reason=FloodReason(data.get("risk_reason", "NONE")),
                    lead_time_hours=data.get("lead_time_hours"),
                    drivers=list(data.get("risk_drivers", [])),
                    station_id=data.get("risk_station_id"),
                    estimated=bool(data.get("risk_estimated", False)),
                    updated_at=data.get("risk_updated_at", datetime.now(timezone.utc)),
                )
            )
        risks.sort(key=lambda r: (-r.score, r.commune_code))
        return risks

    async def get_commune_risk(self, code: str) -> CommuneRisk | None:
        doc = await _run(self._col("communes").document(code).get)
        if not doc.exists:
            return None
        data = doc.to_dict()
        if not data.get("current_risk_tier"):
            return None
        return CommuneRisk(
            commune_code=code,
            commune_name_kh=data.get("name_kh", ""),
            commune_name_en=data.get("name_en", ""),
            province=data.get("province_en"),
            tier=RiskTier(data["current_risk_tier"]),
            score=int(data.get("risk_score", 0)),
            reason=FloodReason(data.get("risk_reason", "NONE")),
            lead_time_hours=data.get("lead_time_hours"),
            drivers=list(data.get("risk_drivers", [])),
            station_id=data.get("risk_station_id"),
            estimated=bool(data.get("risk_estimated", False)),
            updated_at=data.get("risk_updated_at", datetime.now(timezone.utc)),
        )

    # --- subscriptions ------------------------------------------------------------------
    async def upsert_subscription(
        self, chat_id: str, commune_id: str, crop_stage: str | None
    ) -> Subscription:
        doc_id = f"{chat_id}_{commune_id}"
        ref = self._col("commune_subscriptions").document(doc_id)
        existing = await _run(ref.get)
        payload = {
            "telegram_chat_id": chat_id,
            "commune_id": commune_id,
            "subscribed_at": self._fs.SERVER_TIMESTAMP,
        }
        if crop_stage or not existing.exists:
            payload["crop_stage"] = crop_stage
        await _run(ref.set, payload, merge=True)
        doc = await _run(ref.get)
        data = doc.to_dict()
        return Subscription(
            telegram_chat_id=chat_id,
            commune_id=commune_id,
            crop_stage=data.get("crop_stage"),
            subscribed_at=data.get("subscribed_at"),
            last_notified_at=data.get("last_notified_at"),
            last_notified_risk_tier=RiskTier(data["last_notified_risk_tier"])
            if data.get("last_notified_risk_tier")
            else None,
        )

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
        out = []
        for doc in docs:
            data = doc.to_dict()
            out.append(
                Subscription(
                    telegram_chat_id=data["telegram_chat_id"],
                    commune_id=data["commune_id"],
                    crop_stage=data.get("crop_stage"),
                    subscribed_at=data.get("subscribed_at"),
                    last_notified_at=data.get("last_notified_at"),
                    last_notified_risk_tier=RiskTier(data["last_notified_risk_tier"])
                    if data.get("last_notified_risk_tier")
                    else None,
                )
            )
        return out

    async def subscriptions_for_commune(self, commune_id: str) -> list[Subscription]:
        return await self._subscriptions_where("commune_id", commune_id)

    async def subscriptions_for_chat(self, chat_id: str) -> list[Subscription]:
        return await self._subscriptions_where("telegram_chat_id", chat_id)

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
        return SentinelAlert(**{k: v for k, v in docs[0].to_dict().items() if k in SentinelAlert.model_fields})

    async def recent_sentinel_alerts(self, limit: int = 50) -> list[SentinelAlert]:
        query = (
            self._col("sentinel_alerts")
            .order_by("dispatched_at", direction=self._fs.Query.DESCENDING)
            .limit(limit)
        )
        docs = await _run(lambda: list(query.stream()))
        return [
            SentinelAlert(**{k: v for k, v in doc.to_dict().items() if k in SentinelAlert.model_fields})
            for doc in docs
        ]

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
