"""Officials' console: alert dispatch log (FR-10) and weekly stage-advance reminders (IMP-10)."""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from mekong_shared.agronomy import stage_for_planting_date
from mekong_shared.logging_utils import log_event
from mekong_shared.models import CropType, RiskTier

from ..deps import require_admin

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
digest_router = APIRouter(prefix="/api/v1/digest", tags=["digest"])


class AlertLogEntry(BaseModel):
    id: int | str | None = None
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


def _chat_id(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


@digest_router.post("/stage-advance", dependencies=[Depends(require_admin)])
async def stage_advance(request: Request) -> dict:
    """Weekly rice growth-stage check: prompt farmers on Telegram to confirm advancement."""
    repo = request.app.state.repo
    gazetteer = request.app.state.pipeline.gazetteer
    telegram_app = getattr(request.app.state, "telegram_app", None)
    today = date.today()

    subs = await repo.list_all_subscriptions()
    advancements: list[dict] = []
    prompted = 0

    for sub in subs:
        if sub.crop_type != CropType.RICE or sub.planting_date is None:
            continue
        recommended = stage_for_planting_date(sub.planting_date, today=today)
        if sub.crop_stage == recommended:
            continue

        commune = gazetteer.get(sub.commune_id)
        commune_label = (
            f"{commune.name_kh} ({commune.name_en})" if commune is not None else sub.commune_id
        )
        entry = {
            "chat_id": sub.telegram_chat_id,
            "commune_code": sub.commune_id,
            "current_stage": sub.crop_stage.value if sub.crop_stage else None,
            "recommended_stage": recommended.value,
            "planting_date": sub.planting_date.isoformat(),
            "prompted": False,
        }

        if telegram_app is not None:
            text = (
                f"🌾 ការអាប់ដេតដំណាក់កាលស្រូវ — {commune_label}\n"
                f"ផ្អែកតាមថ្ងៃដាំ ({sub.planting_date.isoformat()}) ស្រូវរបស់អ្នកអាចឈានដល់ដំណាក់កាល "
                f"«{recommended.label_kh}» ({recommended.label_en})។\n"
                f"Based on your planting date ({sub.planting_date.isoformat()}), your rice may now "
                f"be at {recommended.label_en}. Tap below to update your alerts:"
            )
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                f"✅ បញ្ជាក់ {recommended.label_kh} / Confirm {recommended.label_en}",
                                callback_data=f"stage_confirm:{sub.commune_id}:{recommended.value}",
                            )
                        ]
                    ]
                )
            except Exception:  # noqa: BLE001
                markup = None

            try:
                await telegram_app.bot.send_message(
                    chat_id=_chat_id(sub.telegram_chat_id),
                    text=text,
                    reply_markup=markup,
                )
                entry["prompted"] = True
                prompted += 1
            except Exception as exc:  # noqa: BLE001 - one bad chat must not abort batch
                log.warning(
                    "stage-advance prompt failed for chat %s: %s", sub.telegram_chat_id, exc
                )

        advancements.append(entry)

    log_event(
        log,
        "STAGE_ADVANCE_RUN",
        trace_id=getattr(request.state, "trace_id", None),
        checked=len(subs),
        candidates=len(advancements),
        prompted=prompted,
    )
    return {
        "checked": len(subs),
        "candidates": len(advancements),
        "prompted": prompted,
        "advancements": advancements,
    }
