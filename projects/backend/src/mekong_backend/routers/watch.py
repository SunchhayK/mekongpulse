"""Watch-officer runs: create, review, approve (publish), reject.

A run is a pending approval task. Approval posts the deterministic bilingual
draft to the public channel with the same publisher the assistant uses; the
agent itself never publishes. Officer authorization is required for every
endpoint, including listing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from mekong_shared.adk_tools import TELEGRAM_MESSAGE_LIMIT
from mekong_shared.logging_utils import log_event
from mekong_shared.models import AgentRun, AgentRunStatus
from mekong_shared.watch import pick_watch_commune, run_watch

from ..officer_auth import authorized_for
from ..problems import problem
from .officer import _channel_publisher

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/watch", tags=["watch"])

MAX_EDIT_CHARS = 3500


class WatchRequest(BaseModel):
    commune_code: str | None = Field(default=None, max_length=10)


class ApproveRequest(BaseModel):
    khmer_text: str | None = Field(default=None, max_length=MAX_EDIT_CHARS)
    english_text: str | None = Field(default=None, max_length=MAX_EDIT_CHARS)


def _require_officer(request: Request) -> None:
    settings = request.app.state.settings
    if not authorized_for(settings, request.headers):
        raise HTTPException(status_code=401, detail="officer session required")


@router.get("/runs")
async def list_runs(request: Request, status: str | None = None, limit: int = 20) -> dict:
    _require_officer(request)
    runs = await request.app.state.repo.list_agent_runs(
        status=status, limit=max(1, min(limit, 50))
    )
    return {"runs": [run.model_dump(mode="json") for run in runs]}


@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str) -> dict:
    _require_officer(request)
    run = await request.app.state.repo.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="watch run not found")
    return {"run": run.model_dump(mode="json")}


@router.post("/runs")
async def create_run(request: Request, body: WatchRequest) -> dict:
    _require_officer(request)
    pipeline = request.app.state.pipeline
    code = (body.commune_code or "").strip() or await pick_watch_commune(pipeline)
    run = await run_watch(pipeline, code, trigger="manual")
    return {"run": run.model_dump(mode="json")}


@router.post("/runs/{run_id}/approve")
async def approve_run(request: Request, run_id: str, body: ApproveRequest) -> dict:
    _require_officer(request)
    repo = request.app.state.repo
    run: AgentRun | None = await repo.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="watch run not found")
    if run.status is not AgentRunStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"run is already {run.status.value}")

    khmer = (body.khmer_text or run.draft_khmer).strip()
    english = (body.english_text or run.draft_english or "").strip()
    if not khmer:
        raise HTTPException(status_code=422, detail="the Khmer draft is empty")
    text = f"{khmer}\n\n{english}" if english else khmer
    text = text[:TELEGRAM_MESSAGE_LIMIT]

    publisher = _channel_publisher(request)
    if publisher is None:
        return problem(
            503,
            "Telegram channel not configured",
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_BROADCAST_CHANNEL_ID to publish watch runs.",
            type_suffix="telegram-not-configured",
            trace_id=getattr(request.state, "trace_id", None),
        )
    result = await publisher(text)
    if not isinstance(result, dict) or result.get("status") == "error" or "error" in result:
        detail = str(
            (result or {}).get("detail")
            or (result or {}).get("error")
            or "Telegram rejected the post"
        )
        log_event(log, "WATCH_PUBLISH_FAILED", run_id=run.id, error=detail[:200])
        return problem(
            502,
            "Channel publish failed",
            detail,
            type_suffix="publish-failed",
            trace_id=getattr(request.state, "trace_id", None),
        )

    now = datetime.now(timezone.utc)
    published = run.model_copy(
        update={
            "status": AgentRunStatus.PUBLISHED,
            "draft_khmer": khmer,
            "draft_english": english or None,
            "approved_at": now,
            "approved_by": "officer",
            "published_at": now,
            "published_message_id": result.get("message_id"),
            "published_text": text,
        }
    )
    await repo.update_agent_run(published)
    log_event(
        log,
        "WATCH_RUN_PUBLISHED",
        run_id=run.id,
        commune=run.commune_code,
        message_id=published.published_message_id,
    )
    return {"run": published.model_dump(mode="json")}


@router.post("/runs/{run_id}/reject")
async def reject_run(request: Request, run_id: str) -> dict:
    _require_officer(request)
    repo = request.app.state.repo
    run: AgentRun | None = await repo.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="watch run not found")
    if run.status is not AgentRunStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"run is already {run.status.value}")
    rejected = run.model_copy(
        update={
            "status": AgentRunStatus.REJECTED,
            "rejected_at": datetime.now(timezone.utc),
            "approved_by": "officer",
        }
    )
    await repo.update_agent_run(rejected)
    log_event(log, "WATCH_RUN_REJECTED", run_id=run.id, commune=run.commune_code)
    return {"run": rejected.model_dump(mode="json")}
