"""Telegram webhook ingress.

Telegram calls this endpoint in production; the secret-token header is checked
against TELEGRAM_WEBHOOK_SECRET (required in production). Updates are handed to
the python-telegram-bot Application which never runs its own poller here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from mekong_shared.logging_utils import log_event

from ..problems import problem

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(tags=["telegram"])


def _deserialize_update(payload: dict, bot):
    from telegram import Update

    return Update.de_json(payload, bot)


@router.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: Request):
    settings = request.app.state.settings
    trace_id = getattr(request.state, "trace_id", None)
    secret = settings.telegram_webhook_secret

    if settings.is_production and not secret:
        return problem(
            503,
            "Webhook secret not configured",
            "TELEGRAM_WEBHOOK_SECRET must be set in production.",
            type_suffix="misconfigured",
            trace_id=trace_id,
        )
    if secret:
        provided = request.headers.get("x-telegram-bot-api-secret-token")
        if provided != secret:
            log_event(log, "TELEGRAM_WEBHOOK_REJECTED", trace_id=trace_id)
            return problem(
                401,
                "Invalid webhook secret",
                None,
                type_suffix="unauthorized",
                trace_id=trace_id,
            )

    telegram_app = request.app.state.telegram_app
    if telegram_app is None:
        return problem(
            503,
            "Telegram bot not configured",
            "Set TELEGRAM_BOT_TOKEN to enable the bot.",
            type_suffix="telegram-unavailable",
            trace_id=trace_id,
        )

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - malformed body from upstream
        return problem(
            400, "Malformed update payload", None, type_suffix="bad-request", trace_id=trace_id
        )

    try:
        update = _deserialize_update(payload, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as exc:  # noqa: BLE001 - always 200 so Telegram stops retrying
        log_event(log, "TELEGRAM_UPDATE_FAILED", trace_id=trace_id, error=str(exc))
    return {"ok": True}
