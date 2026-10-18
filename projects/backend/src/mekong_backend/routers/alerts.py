"""Officials' console: alert dispatch log (FR-10)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mekong_shared.models import RiskTier

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertLogEntry(BaseModel):
    id: int | None = None
    commune_code: str
    commune_name_kh: str
    commune_name_en: str
    province: str | None = None
    station_id: str | None = None
    risk_tier: RiskTier
    lead_time_hours: int | None = None
    directive_title: str
    bulletin_text: str
    audio_url: str | None = None
    dispatched_at: datetime
    recipients_count: int


@router.get("/log")
async def alert_log(request: Request, limit: int = 50) -> list[AlertLogEntry]:
    repo = request.app.state.repo
    gazetteer = request.app.state.pipeline.gazetteer
    alerts = await repo.recent_sentinel_alerts(limit=max(1, min(limit, 200)))
    entries = []
    for alert in alerts:
        commune = gazetteer.get(alert.commune_id)
        entries.append(
            AlertLogEntry(
                id=alert.id,
                commune_code=alert.commune_id,
                commune_name_kh=commune.name_kh if commune else "",
                commune_name_en=commune.name_en if commune else "",
                province=commune.province_en if commune else None,
                station_id=alert.station_id,
                risk_tier=alert.risk_tier,
                lead_time_hours=alert.lead_time_hours,
                directive_title=alert.directive_title,
                bulletin_text=alert.bulletin_text,
                audio_url=alert.audio_url,
                dispatched_at=alert.dispatched_at,
                recipients_count=alert.recipients_count,
            )
        )
    return entries
