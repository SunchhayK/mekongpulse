"""Application wiring smoke tests (offline: no network, no polling)."""

from __future__ import annotations

from mekong_bot.app import build_application
from mekong_bot.service import BotService


def test_build_application_returns_none_without_token(settings, pipeline, repo):
    assert build_application(settings, pipeline=pipeline, repo=repo) is None


def test_build_application_registers_handlers_and_service(settings, pipeline, repo):
    with_token = settings.model_copy(update={"telegram_bot_token": "123456:TEST-TOKEN"})
    application = build_application(with_token, pipeline=pipeline, repo=repo)
    assert application is not None
    assert isinstance(application.bot_data["service"], BotService)
    handlers = application.handlers[0]
    commands = {
        command
        for handler in handlers
        for command in getattr(handler, "commands", set())
    }
    assert {"start", "subscribe", "unsubscribe", "mysubs", "risk", "report", "digest"} <= commands
