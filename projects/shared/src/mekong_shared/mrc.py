"""MRC telemetry client (FR-01 / INV-01 / INV-02 / BUG-10 / BUG-12).

Thin infrastructure client over the MRC open telemetry API. It never invents a
number: every level, stage, and timestamp comes from the live payload. Failover
logic lives in `pipeline.py`; this module owns fetching, parsing, lightweight
pre-classification QC, smoothed rate-of-rise, and the empirical hydraulic offset
used when a station fails over.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

import httpx
from pydantic import BaseModel

from .models import StationSnapshot

# Lightweight pre-classification QC bounds (aligned with evidence.py)
QC_RANGE_LOW_MARGIN_M = 10.0
QC_RANGE_HIGH_MARGIN_M = 3.0
QC_SPIKE_REJECT_M = 1.0
QC_SHORT_SPIKE_REJECT_M = 0.5
QC_SHORT_SPIKE_MAX_HOURS = 0.5
QC_SPIKE_MAX_INTERVAL_HOURS = 3.0


class MRCTelemetryError(Exception):
    """Raised when a station payload cannot be fetched or parsed."""


class MRCValidationError(MRCTelemetryError):
    """Raised when a live reading fails range or spike QC validation."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


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


def validate_latest_reading(
    measurements: list[Measurement],
    alarm_stage_m: float,
    flood_stage_m: float,
) -> None:
    """Validate latest gauge reading for implausible range or single-tick spikes.

    Raises `MRCValidationError` with kind `QC_OUT_OF_RANGE` or `QC_SPIKE_REJECTED`
    so `Pipeline.poll_station()` rejects the reading and falls back to the
    adjacent station before persisting or classifying risk.
    """
    if not measurements:
        raise MRCTelemetryError("no measurements to validate")

    latest = measurements[-1]
    low = alarm_stage_m - QC_RANGE_LOW_MARGIN_M
    high = flood_stage_m + QC_RANGE_HIGH_MARGIN_M
    if latest.level_m < low or latest.level_m > high:
        raise MRCValidationError(
            f"latest level {latest.level_m:.3f}m outside plausible range [{low:.2f}, {high:.2f}]m",
            kind="QC_OUT_OF_RANGE",
        )

    if len(measurements) >= 2:
        prev = measurements[-2]
        span_h = (latest.at - prev.at).total_seconds() / 3600.0
        step = abs(latest.level_m - prev.level_m)
        if 0 < span_h <= QC_SPIKE_MAX_INTERVAL_HOURS:
            if step >= QC_SPIKE_REJECT_M or (
                span_h <= QC_SHORT_SPIKE_MAX_HOURS and step >= QC_SHORT_SPIKE_REJECT_M
            ):
                raise MRCValidationError(
                    f"implausible single-tick step of {step:.3f}m over {span_h * 60:.0f} min",
                    kind="QC_SPIKE_REJECTED",
                )


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
            rain = row.get("r")
            out.append(
                Measurement(
                    at=_parse_dt(str(row["d"])),
                    level_m=float(row["w"]),
                    rain_mm=float(rain) if rain is not None else None,
                )
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
        alarm_stage = float(station["alarmStage"])
        flood_stage = float(station["floodStage"])
        measurements = self._measurements(payload)
        validate_latest_reading(measurements, alarm_stage, flood_stage)
        latest = measurements[-1]
        return StationSnapshot(
            station_id=station_id,
            name=station.get("name") or station_id,
            river=station.get("river") or "unknown",
            level_m=round(latest.level_m, 3),
            alarm_stage_m=alarm_stage,
            flood_stage_m=flood_stage,
            rate_of_rise_m_per_hr=rate_of_rise_m_per_hr(measurements),
            rain_mm=round(latest.rain_mm, 3) if latest.rain_mm is not None else None,
            recorded_at=latest.at,
            is_stale_fallback=False,
            source="live",
        )


def rate_of_rise_m_per_hr(measurements: list[Measurement], window_hours: float = 3.0) -> float:
    """Smoothed rate of rise over the trailing window, using the live 15-min series.

    Uses 3-point median endpoints when at least 5 readings exist in the trailing
    window so a single noisy sensor tick (e.g. +0.30 m on the latest 15-min
    reading) cannot trigger false RIVER_PULSE WARNING alerts, while genuine
    sustained rises (>=2 consecutive elevated ticks or steady ramps) still
    report the true slope.
    """
    if len(measurements) < 2:
        return 0.0
    latest = measurements[-1]
    cutoff = latest.at - timedelta(hours=window_hours)
    window = [m for m in measurements if m.at >= cutoff]
    if len(window) < 2:
        window = measurements[-2:]

    if len(window) >= 5:
        start_level = statistics.median(m.level_m for m in window[:3])
        end_level = statistics.median(m.level_m for m in window[-3:])
        span_hrs = (window[-2].at - window[1].at).total_seconds() / 3600.0
        if span_hrs < 0.5:
            return 0.0
        return round((end_level - start_level) / span_hrs, 4)

    earlier = window[0]
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
