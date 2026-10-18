"""Officer assistant API: agentic advisor turns + digest trigger.

`POST /api/v1/advisor` runs the shared advisor engine with tool-call tracing
and officer-gated actions (publishing); `POST /api/v1/digest/send` posts the
deterministic bilingual digest to the public Telegram channel and is
admin-guarded like /telemetry/sync (cron-friendly: missing Telegram config is
an "unavailable" status, not an error).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from mekong_shared.adk_agent import AdvisorCall, AdvisorUnavailable, answer_detailed
from mekong_shared.adk_tools import TELEGRAM_MESSAGE_LIMIT, AdvisorToolContext, AdvisorTools
from mekong_shared.digest import build_digest
from mekong_shared.logging_utils import log_event
from mekong_shared.models import ConversationTurn

from ..deps import require_admin
from ..problems import problem

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1", tags=["officer"])

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 6


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AdvisorRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    locale: Literal["km", "en"] = "km"
    commune_code: str | None = None


def _channel_publisher(request: Request):
    """Publisher closure for the public channel; None when Telegram is not wired."""
    settings = request.app.state.settings
    channel = settings.telegram_broadcast_channel_id
    telegram_app = getattr(request.app.state, "telegram_app", None)
    if telegram_app is None or not channel:
        return None

    async def publish(text: str) -> dict:
        message = await telegram_app.bot.send_message(chat_id=channel, text=text)
        return {"message_id": getattr(message, "message_id", None)}

    return publish


def _actions(calls: list[AdvisorCall]) -> list[dict]:
    """Translate publish_to_channel traces (summary "status: detail") into actions."""
    actions: list[dict] = []
    for call in calls:
        if call.name != "publish_to_channel":
            continue
        status, _, detail = call.summary.partition(":")
        actions.append(
            {
                "type": "telegram_post",
                "status": status.strip(),
                "detail": detail.strip() or None,
            }
        )
    return actions


def _officer_prompt(body: AdvisorRequest, pipeline) -> str:
    """Prefix the officer's message with grounded request context."""
    hints = [f"Officer locale: {body.locale}"]
    if body.commune_code:
        commune = pipeline.gazetteer.get(body.commune_code)
        if commune is not None:
            hints.append(
                f"focus commune {commune.code} {commune.name_kh} ({commune.name_en})"
            )
        else:
            hints.append(f"focus commune code {body.commune_code}")
    return f"[Officer context: {'; '.join(hints)}]\n{body.message}"


@router.post("/advisor")
async def advisor(
    request: Request,
    body: AdvisorRequest,
    x_officer_token: str | None = Header(default=None),
) -> dict:
    """One traced advisor turn; publishing requires the officer token."""
    settings = request.app.state.settings
    pipeline = request.app.state.pipeline
    authorized = settings.admin_token is not None and x_officer_token == settings.admin_token

    context = AdvisorToolContext(
        pipeline,
        authorized=authorized,
        publisher=_channel_publisher(request),
    )
    history = [
        ConversationTurn(chat_id="officer", role=turn.role, content=turn.content)
        for turn in body.history
    ]
    try:
        outcome = await answer_detailed(
            AdvisorTools(context), history, _officer_prompt(body, pipeline), settings
        )
    except AdvisorUnavailable as exc:
        return problem(
            503,
            "Advisor unavailable",
            str(exc),
            type_suffix="advisor-unavailable",
            trace_id=getattr(request.state, "trace_id", None),
        )

    log_event(
        log,
        "ADVISOR_ANSWERED",
        trace_id=getattr(request.state, "trace_id", None),
        tool_calls=len(outcome.calls),
        authorized=authorized,
    )
    return {
        "reply": outcome.text,
        "tool_calls": [
            {"name": call.name, "status": call.status, "summary": call.summary}
            for call in outcome.calls
        ],
        "actions": _actions(outcome.calls),
    }


@router.post("/digest/send", dependencies=[Depends(require_admin)])
async def send_digest(request: Request) -> dict:
    """Build the bilingual digest and post it to the public channel."""
    settings = request.app.state.settings
    khmer, english = await build_digest(request.app.state.repo, settings)
    preview = khmer[:200]

    publisher = _channel_publisher(request)
    if publisher is None:
        return {"status": "unavailable", "digest_preview": preview}

    message = f"{khmer}\n\n{english}"[:TELEGRAM_MESSAGE_LIMIT]
    try:
        await publisher(message)
    except Exception as exc:  # noqa: BLE001 - cron-friendly: report, never fail the run
        log_event(
            log,
            "DIGEST_SEND_FAILED",
            trace_id=getattr(request.state, "trace_id", None),
            error=str(exc),
        )
        return {"status": "error", "detail": str(exc), "digest_preview": preview}

    log_event(log, "DIGEST_SENT", trace_id=getattr(request.state, "trace_id", None))
    return {"status": "posted", "digest_preview": preview}
