"""Sentinel patrol trigger (Cloud Scheduler -> escalation scan -> dispatch).

Upward WARNING/DANGER transitions enqueue watch-officer runs onto `TaskQueue`
(Cloud Tasks in production, bounded local execution in dev/tests) capped by
`WATCH_AUTO_MAX_RUNS`. The runs draft approval tasks asynchronously; they never
publish without an officer.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from mekong_shared.models import RiskTier
from mekong_shared.tasks import LocalTaskQueue
from mekong_shared.watch import run_watch

from ..deps import get_task_queue, require_admin

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
async def run_patrol(request: Request) -> dict:
    sentinel = request.app.state.sentinel
    summary = await sentinel.run()

    settings = request.app.state.settings
    pipeline = request.app.state.pipeline
    task_queue = get_task_queue(request)
    if task_queue is None:
        async def _local_watch(code: str, trigger: str, prev: str | None) -> None:
            prev_tier = RiskTier(prev) if prev else None
            await _auto_watch(pipeline, code, prev_tier)

        task_queue = LocalTaskQueue(watch_handler=_local_watch)

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
            dedup_key = f"patrol:{summary.run.id}:{transition.commune.code}:{current.value}"
            try:
                task = await task_queue.enqueue_watch_run(
                    commune_code=transition.commune.code,
                    trigger="transition",
                    previous_tier=previous.value if previous else None,
                    dedup_key=dedup_key,
                )
                if not task.deduplicated:
                    queued += 1
            except Exception:  # noqa: BLE001 - enqueue failure must not fail patrol response
                log.exception(
                    "failed to enqueue watch run for commune %s", transition.commune.code
                )

    return {
        "run": summary.run.model_dump(mode="json"),
        "alerts": [a.model_dump(mode="json") for a in summary.alerts],
        "debounced": summary.debounced,
        "watch_runs_queued": queued,
    }
