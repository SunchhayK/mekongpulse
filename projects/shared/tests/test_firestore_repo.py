"""Unit tests for FirestoreRepository (BUG-01, BUG-02, BUG-04, BUG-07, BUG-08, BUG-12, IMP-07, IMP-10)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from mekong_shared.firestore_repo import FirestoreRepository
from mekong_shared.models import (
    AgentRun,
    AgentRunStatus,
    Commune,
    CommuneCalibration,
    CommuneRisk,
    CropType,
    FieldReport,
    FieldReportStatus,
    FloodReason,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
)
from mekong_shared.stations import StationConfig


class _FakeFieldFilter:
    def __init__(self, field: str, op: str, value: Any) -> None:
        self.field = field
        self.op = op
        self.value = value


class _FakeQueryEnum:
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


class _FakeFirestoreModule:
    SERVER_TIMESTAMP = "__SERVER_TIMESTAMP__"
    FieldFilter = _FakeFieldFilter
    Query = _FakeQueryEnum

    @staticmethod
    def transactional(fn):
        def _wrapper(tx, *args, **kwargs):
            return fn(tx, *args, **kwargs)

        return _wrapper


class _FakeSnap:
    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data or {})


class _FakeDocRef:
    def __init__(self, store: dict[str, dict[str, Any]], col_path: str, doc_id: str) -> None:
        self._store = store
        self._col_path = col_path
        self.id = doc_id
        self._key = f"{col_path}/{doc_id}"

    def _resolve(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            k: (now if v == _FakeFirestoreModule.SERVER_TIMESTAMP else v)
            for k, v in payload.items()
        }

    def set(self, payload: dict[str, Any], merge: bool = False) -> None:
        resolved = self._resolve(payload)
        if merge and self._key in self._store:
            merged = dict(self._store[self._key])
            merged.update(resolved)
            self._store[self._key] = merged
        else:
            self._store[self._key] = resolved

    def get(self, transaction: Any = None) -> _FakeSnap:
        return _FakeSnap(self.id, self._store.get(self._key))

    def delete(self) -> None:
        self._store.pop(self._key, None)

    def collection(self, sub: str) -> "_FakeCollection":
        return _FakeCollection(self._store, f"{self._key}/{sub}")


class _FakeQuery:
    def __init__(
        self,
        store: dict[str, dict[str, Any]],
        col_path: str,
        *,
        filters: list[_FakeFieldFilter] | None = None,
        order: tuple[str, str] | None = None,
        limit_n: int | None = None,
        recorder: list[dict[str, Any]] | None = None,
    ) -> None:
        self._store = store
        self._col_path = col_path
        self._filters = list(filters or [])
        self._order = order
        self._limit = limit_n
        self._recorder = recorder

    def where(self, *, filter: _FakeFieldFilter) -> "_FakeQuery":
        return _FakeQuery(
            self._store,
            self._col_path,
            filters=[*self._filters, filter],
            order=self._order,
            limit_n=self._limit,
            recorder=self._recorder,
        )

    def order_by(self, field: str, direction: str = _FakeQueryEnum.ASCENDING) -> "_FakeQuery":
        return _FakeQuery(
            self._store,
            self._col_path,
            filters=self._filters,
            order=(field, direction),
            limit_n=self._limit,
            recorder=self._recorder,
        )

    def limit(self, n: int) -> "_FakeQuery":
        return _FakeQuery(
            self._store,
            self._col_path,
            filters=self._filters,
            order=self._order,
            limit_n=n,
            recorder=self._recorder,
        )

    def stream(self):
        if self._recorder is not None:
            self._recorder.append(
                {
                    "collection": self._col_path,
                    "filters": [(f.field, f.op, f.value) for f in self._filters],
                    "order": self._order,
                    "limit": self._limit,
                }
            )
        prefix = f"{self._col_path}/"
        rows: list[_FakeSnap] = []
        for key, data in self._store.items():
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            if "/" in rest:
                continue
            ok = True
            for f in self._filters:
                val = data.get(f.field)
                if f.op == "==" and val != f.value:
                    ok = False
                elif f.op == ">=" and (val is None or val < f.value):
                    ok = False
            if ok:
                rows.append(_FakeSnap(rest, data))
        if self._order is not None:
            field, direction = self._order
            rows.sort(
                key=lambda s: s.to_dict().get(field),
                reverse=(direction == _FakeQueryEnum.DESCENDING),
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)


class _FakeCollection(_FakeQuery):
    def __init__(self, store: dict[str, dict[str, Any]], col_path: str, recorder=None) -> None:
        super().__init__(store, col_path, recorder=recorder)
        self._seq = 0

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, self._col_path, doc_id)

    def add(self, payload: dict[str, Any]):
        self._seq += 1
        doc_id = f"auto_{len(self._store) + self._seq}"
        ref = self.document(doc_id)
        ref.set(payload)
        return (None, ref)


class _FakeBatch:
    def __init__(self) -> None:
        self._ops: list[tuple[_FakeDocRef, dict[str, Any], bool]] = []

    def set(self, ref: _FakeDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        self._ops.append((ref, payload, merge))

    def commit(self) -> None:
        for ref, payload, merge in self._ops:
            ref.set(payload, merge=merge)


class _FakeTransaction:
    def set(self, ref: _FakeDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        ref.set(payload, merge=merge)


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.recorded_queries: list[dict[str, Any]] = []

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.store, name, recorder=self.recorded_queries)

    def batch(self) -> _FakeBatch:
        return _FakeBatch()

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    def close(self) -> None:
        pass


def _make_repo() -> tuple[FirestoreRepository, _FakeFirestoreClient]:
    client = _FakeFirestoreClient()
    repo = FirestoreRepository(project="test-proj", client=client, fs_module=_FakeFirestoreModule)
    return repo, client


async def test_bug01_risk_map_and_get_commune_risk_populate_coords_and_level():
    repo, _ = _make_repo()
    now = datetime.now(timezone.utc)
    await repo.seed_communes(
        [
            Commune(
                code="080404",
                name_kh="កោះធំ ក",
                name_en="Kaoh Thum Ka",
                province_en="Kandal",
                lat=11.21,
                lng=105.05,
            )
        ]
    )
    await repo.save_commune_risks(
        [
            CommuneRisk(
                commune_code="080404",
                commune_name_kh="កោះធំ ក",
                commune_name_en="Kaoh Thum Ka",
                province="Kandal",
                lat=11.21,
                lng=105.05,
                tier=RiskTier.WARNING,
                score=72,
                reason=FloodReason.RIVER_PULSE,
                station_id="033402",
                station_level_m=7.85,
                forecast_tier=RiskTier.DANGER,
                forecast_lead_days=4,
                updated_at=now,
            )
        ]
    )

    rows = await repo.risk_map()
    assert len(rows) == 1
    assert rows[0].lat == pytest.approx(11.21)
    assert rows[0].lng == pytest.approx(105.05)
    assert rows[0].station_level_m == pytest.approx(7.85)
    assert rows[0].forecast_tier == RiskTier.DANGER
    assert rows[0].forecast_lead_days == 4

    single = await repo.get_commune_risk("080404")
    assert single is not None
    assert single.lat == pytest.approx(11.21)
    assert single.lng == pytest.approx(105.05)
    assert single.station_level_m == pytest.approx(7.85)


async def test_bug02_string_patrol_run_id_roundtrips_through_sentinel_alerts():
    repo, _ = _make_repo()
    now = datetime.now(timezone.utc)
    saved_run = await repo.save_patrol_run(
        PatrolRun(
            run_at=now,
            stations_polled=9,
            communes_evaluated=1661,
            alerts_dispatched_count=1,
            execution_duration_ms=420,
        )
    )
    assert isinstance(saved_run.id, str)

    await repo.save_sentinel_alert(
        SentinelAlert(
            patrol_run_id=saved_run.id,
            commune_id="080404",
            station_id="033402",
            risk_tier=RiskTier.DANGER,
            lead_time_hours=6,
            directive_title="Emergency harvest",
            bulletin_text="ខេត្តកណ្តាល",
            dispatched_at=now,
            recipients_count=10,
        )
    )

    last = await repo.last_sentinel_alert("080404")
    assert last is not None
    assert last.patrol_run_id == saved_run.id
    assert isinstance(last.id, str)

    recent = await repo.recent_sentinel_alerts(limit=10)
    assert len(recent) == 1
    assert recent[0].patrol_run_id == saved_run.id


async def test_bug04_claim_agent_run_for_publish_is_atomic():
    repo, _ = _make_repo()
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id="run-1",
        commune_code="080404",
        current_tier=RiskTier.DANGER,
        status=AgentRunStatus.PENDING_APPROVAL,
        draft_khmer="សេចក្តីប្រកាស",
        created_at=now,
    )
    await repo.add_agent_run(run)

    first = await repo.claim_agent_run_for_publish("run-1")
    second = await repo.claim_agent_run_for_publish("run-1")

    assert first is not None
    assert first.status == AgentRunStatus.PUBLISHING
    assert second is None


async def test_bug07_list_field_reports_and_agent_runs_push_order_and_limit():
    repo, client = _make_repo()
    now = datetime.now(timezone.utc)
    for i in range(3):
        await repo.add_field_report(
            FieldReport(
                id=f"rep-{i}",
                commune_code="080404",
                status=FieldReportStatus.WATER_REACHED,
                source="web",
                reported_at=now - timedelta(minutes=i),
            )
        )
        await repo.add_agent_run(
            AgentRun(
                id=f"run-{i}",
                commune_code="080404",
                current_tier=RiskTier.WARNING,
                status=AgentRunStatus.PENDING_APPROVAL,
                draft_khmer="draft",
                created_at=now - timedelta(minutes=i),
            )
        )

    client.recorded_queries.clear()
    reports = await repo.list_field_reports(commune_code="080404", limit=2)
    runs = await repo.list_agent_runs(status=AgentRunStatus.PENDING_APPROVAL.value, limit=2)

    assert len(reports) == 2
    assert len(runs) == 2
    assert client.recorded_queries[0]["order"] == ("reported_at", "DESCENDING")
    assert client.recorded_queries[0]["limit"] == 2
    assert client.recorded_queries[1]["order"] == ("created_at", "DESCENDING")
    assert client.recorded_queries[1]["limit"] == 2


async def test_bug08_last_sync_age_minutes_returns_min_and_handles_zero():
    repo, client = _make_repo()
    now = datetime.now(timezone.utc)
    # Station 033401 synced right now (0 seconds ago), 019802 synced 3 hours ago
    client.store["hydro_observations/033401/points/t1"] = {
        "station_id": "033401",
        "recorded_at": now,
        "water_level_m": 6.5,
        "fetched_at": now,
    }
    client.store["hydro_observations/019802/points/t1"] = {
        "station_id": "019802",
        "recorded_at": now - timedelta(hours=3),
        "water_level_m": 10.2,
        "fetched_at": now - timedelta(hours=3),
    }

    age = await repo.last_sync_age_minutes()
    assert age == 0


async def test_bug12_rain_mm_persisted_and_read():
    repo, _ = _make_repo()
    now = datetime.now(timezone.utc)
    await repo.seed_stations(
        [
            StationConfig(
                id="033401",
                name_en="Chaktomuk",
                river="Bassac",
                lat=11.563,
                lng=104.9353,
                alarm_stage_m=10.5,
                flood_stage_m=12.0,
            )
        ]
    )
    await repo.save_observation(
        StationSnapshot(
            station_id="033401",
            name="Chaktomuk",
            river="Bassac",
            level_m=8.2,
            alarm_stage_m=10.5,
            flood_stage_m=12.0,
            rate_of_rise_m_per_hr=0.02,
            recorded_at=now,
            rain_mm=14.5,
        )
    )

    latest = await repo.latest_observation("033401")
    assert latest is not None
    assert latest.rain_mm == pytest.approx(14.5)

    series = await repo.telemetry_series("033401", hours=24)
    assert len(series) == 1
    assert series[0][2] == pytest.approx(14.5)


async def test_imp07_and_imp10_subscriptions_and_calibrations():
    repo, _ = _make_repo()
    sub = await repo.upsert_subscription(
        "chat-1",
        "080404",
        "TILLERING",
        crop_type="VEGETABLES",
        planting_date=date(2026, 6, 15),
    )
    assert sub.crop_type == CropType.VEGETABLES
    assert sub.planting_date == date(2026, 6, 15)

    all_subs = await repo.list_all_subscriptions()
    assert len(all_subs) == 1
    assert all_subs[0].planting_date == date(2026, 6, 15)

    cal = CommuneCalibration(
        commune_code="080404",
        levee_margin_m=0.45,
        lead_time_multiplier=0.9,
        sample_size=12,
        updated_at=datetime.now(timezone.utc),
    )
    await repo.save_commune_calibration(cal)
    loaded = await repo.list_commune_calibrations()
    assert "080404" in loaded
    assert loaded["080404"].levee_margin_m == pytest.approx(0.45)
