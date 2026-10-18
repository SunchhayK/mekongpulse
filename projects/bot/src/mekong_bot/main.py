"""Dev/staging polling entrypoint: `uv run python -m mekong_bot.main`.

Production uses the webhook route in the backend instead; this process is for
local development where there is no public HTTPS endpoint.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import BotCommand

from mekong_shared.config import get_settings
from mekong_shared.logging_utils import configure_logging, log_event
from mekong_shared.pipeline import Pipeline
from mekong_shared.repository import create_audio_store, create_repository

from .app import build_application

log = logging.getLogger("mekongpulse.bot")

BOT_COMMANDS = [
    BotCommand("start", "Start / ចាប់ផ្តើម"),
    BotCommand("watch", "🛡 Watch officer draft / ឃ្លាំមើល"),
    BotCommand("risk", "Risk + advice / ហានិភ័យ"),
    BotCommand("report", "Report water / រាយការណ៍ទឹក"),
    BotCommand("mysubs", "Your communes / ឃុំតាមដាន"),
    BotCommand("subscribe", "Follow a commune / តាមដានឃុំ"),
    BotCommand("digest", "Daily digest / របាយការណ៍ប្រចាំថ្ងៃ"),
    BotCommand("help", "Commands / ជំនួយ"),
]


async def run_polling() -> None:
    settings = get_settings()
    logger = configure_logging("mekong-bot")
    repo = create_repository(settings)
    await repo.init()
    pipeline = Pipeline(settings=settings, repo=repo, audio_store=create_audio_store(settings))
    await pipeline.ensure_seeded()

    application = build_application(settings, pipeline=pipeline, repo=repo)
    if application is None:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set; cannot start polling.")

    await application.initialize()
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        log_event(logger, "BOT_COMMANDS_REGISTERED", count=len(BOT_COMMANDS))
    except Exception as exc:  # noqa: BLE001 - the menu must never block polling
        log.warning("could not register the command menu: %s", exc)
    await application.start()
    assert application.updater is not None
    await application.updater.start_polling(drop_pending_updates=True)
    log_event(logger, "BOT_POLLING_STARTED", environment=settings.environment)
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await repo.close()
        log_event(logger, "BOT_POLLING_STOPPED")


def main() -> None:
    try:
        asyncio.run(run_polling())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
