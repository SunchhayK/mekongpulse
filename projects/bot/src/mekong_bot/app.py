"""PTB Application builder shared by the webhook (backend) and polling (dev)."""

from __future__ import annotations

from telegram.ext import Application

from mekong_shared.config import Settings
from mekong_shared.pipeline import Pipeline
from mekong_shared.repository import Repository

from .handlers import register_handlers
from .service import BotService


def build_application(
    settings: Settings, *, pipeline: Pipeline, repo: Repository
) -> Application | None:
    """Builds the bot application; None when no token is configured."""
    if not settings.telegram_bot_token:
        return None
    application = Application.builder().token(settings.telegram_bot_token).build()

    async def _publish(text: str) -> dict:
        channel = settings.telegram_broadcast_channel_id
        if not channel:
            return {"status": "unavailable"}
        try:
            message = await application.bot.send_message(chat_id=channel, text=text)
        except Exception as exc:  # noqa: BLE001 - surfaced as a value to the officer
            return {"status": "error", "detail": str(exc)[:200]}
        return {"message_id": getattr(message, "message_id", None)}

    service = BotService(settings, pipeline, repo, publisher=_publish)
    register_handlers(application, service)
    application.bot_data["service"] = service
    return application
