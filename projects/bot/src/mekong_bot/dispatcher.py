"""Sentinel -> Telegram dispatch: subscriber fan-out + public channel post."""

from __future__ import annotations

import logging
from io import BytesIO

from mekong_shared.models import SentinelAlert, Subscription
from mekong_shared.pipeline import Pipeline

log = logging.getLogger("mekongpulse.bot")

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
DEFAULT_WEB_BASE_URL = "https://ai-builder-cup-9f8cd.web.app"  # fallback if settings lacks web_base_url


def _chat_id(value: str | int):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


async def _audio_bytes(pipeline: Pipeline, url: str) -> bytes | None:
    """Fetch local-store audio so dev/staging works without a public URL."""
    marker = "/audio/"
    index = url.find(marker)
    if index < 0 or pipeline.audio_store is None:
        return None
    key = url[index + len(marker) :].split("?", 1)[0]
    try:
        return await pipeline.audio_store.get(f"local:{key}")
    except Exception:  # noqa: BLE001 - audio is best-effort, text always goes out
        return None


def make_telegram_dispatcher(pipeline: Pipeline, bot):
    """Returns the Sentinel dispatcher callable bound to a PTB Bot."""
    settings = pipeline.settings

    async def _send_alert(chat_id, alert: SentinelAlert) -> None:
        text = alert.bulletin_text[:MESSAGE_LIMIT]
        if alert.audio_url:
            if alert.audio_url.startswith("https://"):
                await bot.send_voice(
                    chat_id=chat_id, voice=alert.audio_url, caption=text[:CAPTION_LIMIT]
                )
                return
            data = await _audio_bytes(pipeline, alert.audio_url)
            if data:
                await bot.send_voice(
                    chat_id=chat_id, voice=BytesIO(data), caption=text[:CAPTION_LIMIT]
                )
                return
        await bot.send_message(chat_id=chat_id, text=text)

    async def dispatch(
        alert: SentinelAlert,
        subscribers: list[Subscription],
        post_to_channel: bool = True,
    ) -> int:
        delivered = 0
        for sub in subscribers:
            try:
                await _send_alert(_chat_id(sub.telegram_chat_id), alert)
                delivered += 1
            except Exception as exc:  # noqa: BLE001 - one bad chat must not stop the run
                log.warning("alert delivery failed for chat %s: %s", sub.telegram_chat_id, exc)

        channel = settings.telegram_broadcast_channel_id if post_to_channel else None
        if channel:
            base = getattr(settings, "web_base_url", None) or DEFAULT_WEB_BASE_URL
            link = f"\n\n{base.rstrip('/')}/km/commune?code={alert.commune_id}"
            try:
                await bot.send_message(
                    chat_id=_chat_id(channel),
                    text=alert.bulletin_text[: MESSAGE_LIMIT - len(link)] + link,
                )
            except Exception as exc:  # noqa: BLE001 - channel post is best-effort
                log.warning("broadcast channel post failed: %s", exc)
        return delivered

    return dispatch
