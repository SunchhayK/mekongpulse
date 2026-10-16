"""MRC telemetry client (FR-01 / INV-01 / INV-02).

Thin infrastructure client over the MRC open telemetry API. It never invents a
number: every level, stage, and timestamp comes from the live payload. Failover
logic lives in `pipeline.py`; this module owns fetching, parsing, rate-of-rise,
and the empirical hydraulic offset used when a station fails over.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import httpx
from pydantic import BaseModel

from .models import StationSnapshot


class MRCTelemetryError(Exception):
    """Raised when a station payload cannot be fetched or parsed."""


class Measurement(BaseModel):
    at: datetime
    level_m: float
    rain_mm: float | None = None


def _parse_dt(raw: str) -> datetime:
    raw = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise MRCTelemetryError(f"unparseable timestamp {raw!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))  # Mekong basin local time
    return dt.astimezone(timezone.utc)


class MRCTelemetryClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client = http_client

    async def _get(self, path: str) -> dict:
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            if self._client is not None:
                resp = await self._client.get(url)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise MRCTelemetryError(f"MRC request failed for {url}: {exc}") from exc
        except ValueError as exc:
            raise MRCTelemetryError(f"MRC returned non-JSON for {url}: {exc}") from exc

    @staticmethod
    def _measurements(payload: dict) -> list[Measurement]:
        rows = payload.get("measurements") or []
        out: list[Measurement] = []
        for row in rows:
            if row.get("w") is None or row.get("d") is None:
                continue
            out.append(
                Measurement(at=_parse_dt(str(row["d"])), level_m=float(row["w"]), rain_mm=row.get("r"))
            )
        out.sort(key=lambda m: m.at)
        if not out:
            raise MRCTelemetryError("payload contained no usable measurements")
        return out

    async def fetch_series(self, station_id: str) -> list[Measurement]:
        """Full recent time-series (15-min cadence, ~30 days on MRC)."""
        payload = await self._get(f"time-series/telemetry/recent/measurement/{station_id}")
        return self._measurements(payload)

    async def fetch_station(self, station_id: str) -> StationSnapshot:
        """Latest reading parsed from the same live payload (INV-01)."""
        payload = await self._get(f"time-series/telemetry/recent/measurement/{station_id}")
        station = payload.get("station") or {}
        if station.get("stationId") != station_id:
            raise MRCTelemetryError(f"station payload mismatch: {station.get('stationId')!r}")
        for field in ("alarmStage", "floodStage"):
            if station.get(field) is None:
                raise MRCTelemetryError(f"station {station_id} missing {field}")
        measurements = self._measurements(payload)
        latest = measurements[-1]
        return StationSnapshot(
            station_id=station_id,
            name=station.get("name") or station_id,
            river=station.get("river") or "unknown",
            level_m=round(latest.level_m, 3),
            alarm_stage_m=float(station["alarmStage"]),
            flood_stage_m=float(station["floodStage"]),
            rate_of_rise_m_per_hr=rate_of_rise_m_per_hr(measurements),
            recorded_at=latest.at,
            is_stale_fallback=False,
            source="live",
        )


def rate_of_rise_m_per_hr(measurements: list[Measurement], window_hours: float = 3.0) -> float:
    """Rate of rise over the trailing window, using the live 15-min series."""
    if len(measurements) < 2:
        return 0.0
    latest = measurements[-1]
    cutoff = latest.at - timedelta(hours=window_hours)
    earlier = next((m for m in measurements if m.at >= cutoff), measurements[0])
    span_hrs = (latest.at - earlier.at).total_seconds() / 3600.0
    if span_hrs < 0.5:  # too little signal to be meaningful
        return 0.0
    return round((latest.level_m - earlier.level_m) / span_hrs, 4)


def compute_hydraulic_offset(
    primary: list[Measurement],
    fallback: list[Measurement],
    *,
    min_samples: int = 24,
) -> float | None:
    """Empirical median difference primary - fallback on overlapping timestamps.

    Replaces the technical report's hardcoded 2.48 m constant with a value
    derived from the live paired 30-day series. Returns None when overlap is
    too sparse to be trusted.
    """
    fallback_by_minute = {m.at.replace(second=0, microsecond=0): m.level_m for m in fallback}
    diffs: list[float] = []
    for m in primary:
        key = m.at.replace(second=0, microsecond=0)
        if key in fallback_by_minute:
            diffs.append(m.level_m - fallback_by_minute[key])
    if len(diffs) < min_samples:
        return None
    return round(statistics.median(diffs), 3)
