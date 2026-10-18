"""Sentinel patrol trigger (Cloud Scheduler -> escalation scan -> dispatch).

Upward WARNING/DANGER transitions also queue a watch-officer run (capped by
`WATCH_AUTO_MAX_RUNS`). The runs draft approval tasks in the background; they
never publish without an officer.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from mekong_shared.models import RiskTier
from mekong_shared.watch import run_watch

from ..deps import require_admin

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/patrol", tags=["patrol"])


async def _auto_watch(pipeline, commune_code: str, previous_tier: RiskTier | None) -> None:
    try:
        await run_watch(
            pipeline, commune_code, trigger="transition", previous_tier=previous_tier
        )
    except Exception:  # noqa: BLE001 - a watch draft must never break the patrol
        log.exception("automatic watch run failed for commune %s", commune_code)


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_patrol(request: Request, background: BackgroundTasks) -> dict:
    sentinel = request.app.state.sentinel
    summary = await sentinel.run()

    settings = request.app.state.settings
    pipeline = request.app.state.pipeline
    queued = 0
    if settings.watch_auto_max_runs > 0:
        for transition in summary.transitions:
            previous = transition.previous
            current = transition.current.tier
            if previous is not None and current.severity <= previous.severity:
                continue
            if current.severity < RiskTier.WARNING.severity:
                continue
            if queued >= settings.watch_auto_max_runs:
                break
            background.add_task(_auto_watch, pipeline, transition.commune.code, previous)
            queued += 1

    return {
        "run": summary.run.model_dump(mode="json"),
        "alerts": [a.model_dump(mode="json") for a in summary.alerts],
        "debounced": summary.debounced,
        "watch_runs_queued": queued,
    }
