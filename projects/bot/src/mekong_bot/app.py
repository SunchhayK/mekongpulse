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
    service = BotService(settings, pipeline, repo)
    register_handlers(application, service)
    application.bot_data["service"] = service
    return application
