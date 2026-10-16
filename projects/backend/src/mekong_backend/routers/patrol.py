"""Sentinel patrol trigger (Cloud Scheduler -> escalation scan -> dispatch)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import require_admin

router = APIRouter(prefix="/api/v1/patrol", tags=["patrol"])


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_patrol(request: Request) -> dict:
    sentinel = request.app.state.sentinel
    summary = await sentinel.run()
    return {
        "run": summary.run.model_dump(mode="json"),
        "alerts": [a.model_dump(mode="json") for a in summary.alerts],
        "debounced": summary.debounced,
    }
