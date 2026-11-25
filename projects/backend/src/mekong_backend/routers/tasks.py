"""Cloud Tasks worker endpoints for durable watch runs and batched Telegram fan-out (IMP-02)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from mekong_shared.logging_utils import log_event
from mekong_shared.models import RiskTier, SentinelAlert
from mekong_shared.watch import run_watch

from ..deps import get_state_store, require_admin

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(tags=["tasks"], dependencies=[Depends(require_admin)])

WATCH_DEDUP_TTL_SECONDS = 3600


class WatchTaskRequest(BaseModel):
    commune_code: str = Field(min_length=1, max_length=16)
    trigger: str = Field(default="transition", max_length=32)
    previous_tier: RiskTier | None = None
    dedup_key: str | None = Field(default=None, max_length=128)


class DispatchBatchRequest(BaseModel):
    alert: dict[str, Any]
    chat_ids: list[str] = Field(default_factory=list)
    dedup_key: str | None = Field(default=None, max_length=128)


async def _execute_watch_task(request: Request, body: WatchTaskRequest) -> dict:
    state_store = get_state_store(request)
    if body.dedup_key and state_store is not None:
        dedup_cache_key = f"task:watch:{body.dedup_key}"
        existing_id = await state_store.get_json(dedup_cache_key)
        if existing_id:
            return {"status": "deduplicated", "run_id": existing_id}

    pipeline = request.app.state.pipeline
    run = await run_watch(
        pipeline,
        body.commune_code,
        trigger=body.trigger,
        previous_tier=body.previous_tier,
    )
    if body.dedup_key and state_store is not None:
        await state_store.set_json(
            f"task:watch:{body.dedup_key}", run.id, ttl_seconds=WATCH_DEDUP_TTL_SECONDS
        )
    log_event(
        log,
        "TASK_WATCH_COMPLETED",
        run_id=run.id,
        commune=body.commune_code,
        trigger=body.trigger,
    )
    return {"status": "completed", "run": run.model_dump(mode="json")}


async def _execute_dispatch_batch(request: Request, body: DispatchBatchRequest) -> dict:
    telegram_app = getattr(request.app.state, "telegram_app", None)
    if telegram_app is None:
        return {"status": "unavailable", "delivered": 0, "total": len(body.chat_ids)}

    from mekong_bot.dispatcher import dispatch_alert_batch

    alert = SentinelAlert.model_validate(body.alert)
    delivered = await dispatch_alert_batch(
        request.app.state.pipeline,
        telegram_app.bot,
        alert,
        body.chat_ids,
    )
    log_event(
        log,
        "TASK_DISPATCH_BATCH_COMPLETED",
        commune=alert.commune_id,
        delivered=delivered,
        total=len(body.chat_ids),
    )
    return {"status": "completed", "delivered": delivered, "total": len(body.chat_ids)}


@router.post("/api/v1/tasks/watch")
async def task_watch(request: Request, body: WatchTaskRequest) -> dict:
    """Idempotently execute one watch-officer run for a commune."""
    return await _execute_watch_task(request, body)


@router.post("/internal/tasks/watch-run")
async def internal_task_watch(request: Request, body: WatchTaskRequest) -> dict:
    """Cloud Tasks target alias for watch-officer runs."""
    return await _execute_watch_task(request, body)


@router.post("/api/v1/tasks/dispatch-batch")
async def task_dispatch_batch(request: Request, body: DispatchBatchRequest) -> dict:
    """Dispatch a batch of Telegram alerts/voice notes."""
    return await _execute_dispatch_batch(request, body)


@router.post("/internal/tasks/dispatch-batch")
async def internal_task_dispatch_batch(request: Request, body: DispatchBatchRequest) -> dict:
    """Cloud Tasks target alias for batched Telegram fan-out."""
    return await _execute_dispatch_batch(request, body)
