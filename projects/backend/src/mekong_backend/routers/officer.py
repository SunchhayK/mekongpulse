"""Officer assistant API: sign-in, agentic advisor turns, voice input, digest.

`POST /api/v1/officer/login` exchanges the officer passcode for a short-lived
signed session (the admin token never reaches the browser). `POST
/api/v1/advisor` runs the shared advisor engine with tool-call tracing and
officer-gated actions (publishing), authorized by the session bearer token or
the legacy X-Officer-Token header kept for scripts. `POST
/api/v1/advisor/transcribe` turns a recorded voice clip into text (no auth:
the chat itself is open). `POST /api/v1/digest/send` posts the deterministic
bilingual digest to the public Telegram channel and is admin-guarded like
/telemetry/sync (cron-friendly: missing Telegram config is an "unavailable"
status, not an error). `GET /api/v1/telegram/channel` is an admin diagnostic
that verifies the bot can see the configured broadcast channel.
"""

from __future__ import annotations

import base64
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from mekong_shared.adk_agent import AdvisorCall, AdvisorUnavailable, answer_detailed
from mekong_shared.adk_tools import TELEGRAM_MESSAGE_LIMIT, AdvisorToolContext, AdvisorTools
from mekong_shared.digest import build_digest
from mekong_shared.logging_utils import log_event
from mekong_shared.models import ConversationTurn
from mekong_shared.stt import TranscriptionUnavailable, transcribe_audio

from ..deps import require_admin
from ..officer_auth import (
    PasscodeRateLimiter,
    authorized_for,
    issue_session,
    passcode_matches,
    sign_in_configured,
)
from ..problems import problem

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1", tags=["officer"])

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 6
MAX_AUDIO_BASE64_CHARS = 6_000_000
MAX_AUDIO_BYTES = 4_000_000


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AdvisorRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    locale: Literal["km", "en"] = "km"
    commune_code: str | None = None


class LoginRequest(BaseModel):
    passcode: str = Field(min_length=1, max_length=256)


class TranscribeRequest(BaseModel):
    audio_base64: str = Field(min_length=1, max_length=MAX_AUDIO_BASE64_CHARS)
    mime_type: str = Field(min_length=1, max_length=100)
    locale_hint: Literal["km", "en"] | None = None


def _login_limiter(request: Request) -> PasscodeRateLimiter:
    """Per-app limiter (lazily created; in-process state, single staging worker)."""
    limiter = getattr(request.app.state, "officer_login_limiter", None)
    if limiter is None:
        limiter = PasscodeRateLimiter()
        request.app.state.officer_login_limiter = limiter
    return limiter


def _telegram_error_detail(exc: Exception) -> str:
    """Map a Telegram failure to operator guidance without echoing raw payloads."""
    message = str(exc).lower()
    kind = type(exc).__name__.lower()
    if "chat not found" in message:
        return (
            "Telegram channel not found: add the bot as an administrator of the "
            "broadcast channel, then set TELEGRAM_BROADCAST_CHANNEL_ID to the "
            "channel's -100... id or @username."
        )
    if "blocked by the user" in message or "kicked" in message or "deactivated" in message:
        return (
            "Telegram bot was blocked or removed: re-add it as an administrator "
            "of the broadcast channel."
        )
    if (
        "not enough rights" in message
        or "not a member" in message
        or "forbidden" in message
        or "forbidden" in kind
    ):
        return (
            'Telegram bot lacks permission: grant it the "Post messages" '
            "administrator permission on the broadcast channel."
        )
    if (
        "timed out" in message
        or "timeout" in message
        or "network" in message
        or "connection" in message
        or "timedout" in kind
        or "networkerror" in kind
    ):
        return "Telegram is unreachable (timeout or network error); retry shortly."
    return (
        "Telegram rejected the post: verify TELEGRAM_BROADCAST_CHANNEL_ID and "
        "the bot's administrator permissions."
    )


def _channel_publisher(request: Request):
    """Publisher closure for the public channel; None when Telegram is not wired."""
    settings = request.app.state.settings
    channel = settings.telegram_broadcast_channel_id
    telegram_app = getattr(request.app.state, "telegram_app", None)
    if telegram_app is None or not channel:
        return None

    async def publish(text: str) -> dict:
        try:
            message = await telegram_app.bot.send_message(chat_id=channel, text=text)
        except Exception as exc:  # noqa: BLE001 - action failures are values
            detail = _telegram_error_detail(exc)
            log_event(
                log,
                "TELEGRAM_PUBLISH_FAILED",
                trace_id=getattr(request.state, "trace_id", None),
                error=type(exc).__name__,
            )
            return {"status": "error", "detail": detail}
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


@router.post("/officer/login")
async def officer_login(request: Request, body: LoginRequest) -> dict:
    """Exchange the officer passcode for a short-lived signed session token."""
    settings = request.app.state.settings
    trace_id = getattr(request.state, "trace_id", None)
    if not sign_in_configured(settings):
        return problem(
            503,
            "Officer sign-in unavailable",
            "Set OFFICER_PASSCODE (or ADMIN_TOKEN) to enable sign-in",
            type_suffix="officer-sign-in-unavailable",
            trace_id=trace_id,
        )

    limiter = _login_limiter(request)
    client_ip = request.client.host if request.client else "unknown"
    if limiter.blocked(client_ip):
        log_event(log, "OFFICER_LOGIN_RATE_LIMITED", trace_id=trace_id, client=client_ip)
        return problem(
            429,
            "Too many sign-in attempts",
            "Too many failed passcode attempts; try again later",
            type_suffix="too-many-attempts",
            trace_id=trace_id,
        )

    if not passcode_matches(settings, body.passcode):
        limiter.record_failure(client_ip)
        log_event(log, "OFFICER_LOGIN_FAILED", trace_id=trace_id, client=client_ip)
        return problem(
            401,
            "Invalid passcode",
            "The officer passcode is incorrect",
            type_suffix="invalid-passcode",
            trace_id=trace_id,
        )

    limiter.reset(client_ip)
    token, expires_at = issue_session(settings)
    log_event(log, "OFFICER_LOGIN", trace_id=trace_id, client=client_ip)
    return {"session": token, "expires_at": expires_at.isoformat()}


@router.post("/advisor")
async def advisor(request: Request, body: AdvisorRequest) -> dict:
    """One traced advisor turn; publishing requires a session or officer token."""
    settings = request.app.state.settings
    pipeline = request.app.state.pipeline
    authorized = authorized_for(settings, request.headers)

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


@router.post("/advisor/transcribe")
async def transcribe(request: Request, body: TranscribeRequest) -> dict:
    """Voice clip -> transcript for the assistant composer (chat itself is open)."""
    settings = request.app.state.settings
    trace_id = getattr(request.state, "trace_id", None)
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
    except ValueError:
        return problem(
            422,
            "Invalid audio payload",
            "audio_base64 is not valid base64",
            type_suffix="invalid-audio",
            trace_id=trace_id,
        )
    if len(audio) > MAX_AUDIO_BYTES:
        return problem(
            413,
            "Audio too large",
            f"Decoded audio exceeds {MAX_AUDIO_BYTES} bytes",
            type_suffix="audio-too-large",
            trace_id=trace_id,
        )

    try:
        text = await transcribe_audio(settings, audio, body.mime_type, body.locale_hint)
    except TranscriptionUnavailable as exc:
        return problem(
            503,
            "Transcription unavailable",
            str(exc),
            type_suffix="transcription-unavailable",
            trace_id=trace_id,
        )

    log_event(log, "TRANSCRIPTION_DONE", trace_id=trace_id, bytes=len(audio), chars=len(text))
    return {"text": text}


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
        result = await publisher(message)
    except Exception as exc:  # noqa: BLE001 - cron-friendly: report, never fail the run
        detail = _telegram_error_detail(exc)
        log_event(
            log,
            "DIGEST_SEND_FAILED",
            trace_id=getattr(request.state, "trace_id", None),
            error=detail,
        )
        return {"status": "error", "detail": detail, "digest_preview": preview}

    if result.get("status") == "error":
        detail = str(result.get("detail"))
        log_event(
            log,
            "DIGEST_SEND_FAILED",
            trace_id=getattr(request.state, "trace_id", None),
            error=detail,
        )
        return {"status": "error", "detail": detail, "digest_preview": preview}

    log_event(log, "DIGEST_SENT", trace_id=getattr(request.state, "trace_id", None))
    return {"status": "posted", "digest_preview": preview}


@router.get("/telegram/channel", dependencies=[Depends(require_admin)])
async def telegram_channel(request: Request) -> dict:
    """Admin diagnostic: confirm the bot can see the broadcast channel.

    Unconfigured Telegram is a 503 problem, but a Telegram-side failure is a
    200 with ``ok: false`` and an actionable detail. Keeping transport failures
    out of the problem contract lets a setup script read one response shape
    instead of branching on status codes.
    """
    settings = request.app.state.settings
    channel = settings.telegram_broadcast_channel_id
    telegram_app = getattr(request.app.state, "telegram_app", None)
    trace_id = getattr(request.state, "trace_id", None)
    if telegram_app is None or not channel:
        detail = (
            "Telegram bot is not initialized: verify TELEGRAM_BOT_TOKEN and backend startup logs"
            if telegram_app is None
            else "Set TELEGRAM_BROADCAST_CHANNEL_ID to the channel's -100... id or @username"
        )
        return problem(
            503,
            "Telegram not configured",
            detail,
            type_suffix="telegram-not-configured",
            trace_id=trace_id,
        )

    try:
        chat = await telegram_app.bot.get_chat(chat_id=channel)
    except Exception as exc:  # noqa: BLE001 - report the channel state, don't fail the check
        detail = _telegram_error_detail(exc)
        log_event(
            log,
            "TELEGRAM_CHANNEL_CHECK_FAILED",
            trace_id=trace_id,
            error=type(exc).__name__,
        )
        return {"configured_id": str(channel), "ok": False, "detail": detail}

    chat_type = getattr(chat, "type", None)
    if chat_type is not None:
        chat_type = str(getattr(chat_type, "value", chat_type))
    result = {
        "configured_id": str(channel),
        "ok": True,
        "id": getattr(chat, "id", None),
        "type": chat_type,
        "title": getattr(chat, "title", None),
        "username": getattr(chat, "username", None),
    }
    log_event(
        log,
        "TELEGRAM_CHANNEL_CHECK",
        trace_id=trace_id,
        ok=True,
        chat_type=chat_type,
    )
    return {key: value for key, value in result.items() if value is not None}
