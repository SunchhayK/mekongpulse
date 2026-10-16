"""Telemetry read APIs + the sync trigger used by Cloud Scheduler."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from mekong_shared.logging_utils import log_event
from mekong_shared.stations import load_stations

from ..deps import require_admin

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


class StationTelemetry(BaseModel):
    station_id: str
    name: str
    river: str
    level_m: float
    alarm_stage_m: float
    flood_stage_m: float
    rate_of_rise_m_per_hr: float
    recorded_at: str
    is_stale_fallback: bool
    source: str
    staleness_minutes: int | None = None


@router.get("/latest")
async def latest(request: Request) -> list[StationTelemetry]:
    """Latest reading per station, in roster order."""
    settings = request.app.state.settings
    repo = request.app.state.repo
    roster = load_stations(str(settings.data_dir))
    out: list[StationTelemetry] = []
    for station_id in roster:
        snapshot = await repo.latest_observation(station_id)
        if snapshot is None:
            continue
        out.append(
            StationTelemetry(
                station_id=snapshot.station_id,
                name=snapshot.name,
                river=snapshot.river,
                level_m=snapshot.level_m,
                alarm_stage_m=snapshot.alarm_stage_m,
                flood_stage_m=snapshot.flood_stage_m,
                rate_of_rise_m_per_hr=snapshot.rate_of_rise_m_per_hr,
                recorded_at=snapshot.recorded_at.isoformat(),
                is_stale_fallback=snapshot.is_stale_fallback,
                source=snapshot.source,
                staleness_minutes=snapshot.staleness_minutes,
            )
        )
    return out


@router.get("/hydrograph/{station_id}")
async def hydrograph(station_id: str, request: Request, hours: int = 168) -> dict:
    repo = request.app.state.repo
    points = await repo.telemetry_series(station_id, hours=hours)
    return {
        "station_id": station_id,
        "hours": hours,
        "points": [
            {"t": t.isoformat(), "level_m": level, "rain_mm": rain} for t, level, rain in points
        ],
    }


@router.post("/sync", dependencies=[Depends(require_admin)])
async def run_sync(request: Request, force_fallback: bool = False) -> dict:
    """Poll MRC + weather, re-score every commune, persist results."""
    pipeline = request.app.state.pipeline
    summary, transitions = await pipeline.sync(force_fallback=force_fallback)
    log_event(
        log,
        "TELEMETRY_SYNC_COMPLETE",
        trace_id=getattr(request.state, "trace_id", None),
        stations_polled=summary.stations_polled,
        stations_failed=summary.stations_failed,
        communes_evaluated=summary.communes_evaluated,
        duration_ms=summary.duration_ms,
    )
    return {
        "stations_polled": summary.stations_polled,
        "stations_failed": summary.stations_failed,
        "warnings": [w.model_dump(mode="json") for w in summary.warnings],
        "communes_evaluated": summary.communes_evaluated,
        "communes_skipped": summary.communes_skipped,
        "risk_counts": summary.risk_counts,
        "worst_tier": summary.worst_tier.value if summary.worst_tier else None,
        "transitions": len(transitions),
        "duration_ms": summary.duration_ms,
    }
