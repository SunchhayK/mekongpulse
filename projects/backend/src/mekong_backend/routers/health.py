"""Liveness probe + MRC station connectivity (Ops view)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    repo = request.app.state.repo
    age = await repo.last_sync_age_minutes()
    if age is None:
        connection = "UNKNOWN"
    elif age <= 30:
        connection = "CONNECTED"
    elif age <= settings.telemetry_stale_after_minutes:
        connection = "STALE"
    else:
        connection = "OFFLINE"
    return {
        "status": "HEALTHY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mrc_station_connection": connection,
        "environment": settings.environment,
        "repository": settings.repository_backend
        or ("firestore" if settings.use_firestore else "postgres"),
    }
