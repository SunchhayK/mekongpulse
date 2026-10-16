"""Shared test helpers: synthetic MRC/Open-Meteo payloads and mock transports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

# Fixed clock so every generated series is deterministic.
BASE_TIME = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)

STATION_META: dict[str, dict] = {
    "019802": {"name": "Kompong Cham", "river": "Mekong", "alarm": 15.2, "flood": 16.2},
    "020102": {"name": "Prek Kdam", "river": "Tonlesap", "alarm": 9.5, "flood": 10.0},
    "033401": {"name": "Chaktomuk", "river": "Bassac", "alarm": 10.5, "flood": 12.0},
    "033402": {"name": "Koh Khel", "river": "Bassac", "alarm": 7.9, "flood": 8.4},
}


def mrc_payload(
    station_id: str,
    *,
    level: float | None = None,
    rate_m_per_hr: float = 0.0,
    hours: float = 6.0,
    step_min: int = 15,
    rain: float = 0.0,
) -> dict:
    """Synthetic payload shaped exactly like the live MRC measurement response."""
    meta = STATION_META[station_id]
    if level is None:
        level = (meta["alarm"] + meta["flood"]) / 2  # midpoint by default
    steps = int(hours * 60 / step_min)
    measurements = []
    for i in range(steps + 1):
        at = BASE_TIME - timedelta(minutes=step_min * (steps - i))
        value = level - rate_m_per_hr * (steps - i) * step_min / 60.0
        measurements.append(
            {"d": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "w": round(value, 3), "r": rain}
        )
    return {
        "station": {
            "stationId": station_id,
            "name": meta["name"],
            "river": meta["river"],
            "latitude": 11.5,
            "longitude": 105.0,
            "alarmStage": meta["alarm"],
            "floodStage": meta["flood"],
            "waterLevel": measurements[-1]["w"],
            "lastMeasurement": measurements[-1]["d"],
        },
        "measurements": measurements,
    }


def mrc_transport(handlers: dict[str, dict | int]) -> httpx.MockTransport:
    """Mock transport for the MRC API: station id path suffix -> payload or status."""

    async def handler(request: httpx.Request) -> httpx.Response:
        station_id = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        entry = handlers.get(station_id)
        if entry is None:
            return httpx.Response(404, json={"error": "unknown station"})
        if isinstance(entry, int):
            return httpx.Response(entry)
        return httpx.Response(200, json=entry)

    return httpx.MockTransport(handler)


def weather_payload(rain_first_48h_mm_per_hr: float = 0.0, soil: float = 0.30, days: int = 8) -> dict:
    hours = days * 24
    return {
        "hourly": {
            "time": [(BASE_TIME + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)],
            "precipitation": [rain_first_48h_mm_per_hr] * 48 + [0.0] * (hours - 48),
            "soil_moisture_0_to_7cm": [soil] * hours,
        }
    }


def weather_transport(payload: dict | None = None) -> httpx.MockTransport:
    body = payload or weather_payload()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def healthy_handlers(
    levels: dict[str, float] | None = None,
    rates: dict[str, float] | None = None,
) -> dict[str, dict]:
    """All four stations serving data; defaults sit far below alarm stage."""
    default_levels = {"019802": 12.5, "020102": 6.5, "033401": 7.8, "033402": 5.2}
    merged = {**default_levels, **(levels or {})}
    out = {}
    for sid, level in merged.items():
        out[sid] = mrc_payload(sid, level=level, rate_m_per_hr=(rates or {}).get(sid, 0.0))
    return out
