"""MekongSentinel autonomous patrol (FR-07, AC-03, BUG-03, IMP-06).

Runs on the 15-minute scheduler: syncs state, detects upward tier transitions,
enforces the 6-hour per-commune debounce (while always allowing strictly higher
severity escalations such as WARNING -> DANGER to bypass debounce), pre-warms
Khmer voice audio for communes entering WARNING/DANGER, and dispatches to
subscribers and the public channel (via the injected dispatcher). Every dispatch
is logged to `sentinel_patrol_runs`/`sentinel_alerts`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from .config import Settings
from .logging_utils import log_event
from .models import (
    AssessmentResult,
    CropStage,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    Subscription,
)
from .pipeline import Pipeline, RiskTransition

log = logging.getLogger("mekongpulse.sentinel")

PATROL_DISPATCH_CONCURRENCY = 5
MAX_PREWARM_COMMUNES = 3

Dispatcher = Callable[[SentinelAlert, list[Subscription], bool], Awaitable[int]]


async def _noop_dispatcher(
    alert: SentinelAlert, subscribers: list[Subscription], post_to_channel: bool = True
) -> int:
    """Records without delivering (offline/dev); returns delivered count."""
    return 0


@dataclass
class PatrolSummary:
    run: PatrolRun
    alerts: list[SentinelAlert]
    debounced: list[str]
    transitions: list[RiskTransition] = field(default_factory=list)


class SentinelPatrol:
    def __init__(
        self,
        pipeline: Pipeline,
        *,
        settings: Settings | None = None,
        dispatcher: Dispatcher | None = None,
        escalate_from: RiskTier = RiskTier.WARNING,
    ) -> None:
        self._pipeline = pipeline
        self._settings = settings or pipeline.settings
        self._dispatcher = dispatcher or _noop_dispatcher
        self._escalate_from = escalate_from

    async def _presynthesize_commune_audio(self, commune_code: str) -> None:
        """Pre-warm default RIPENING Khmer MP3 audio for instant /commune playback (IMP-06)."""
        try:
            await self._pipeline.assess_commune(
                commune_code, CropStage.RIPENING, with_audio=True
            )
        except Exception as exc:  # noqa: BLE001 - pre-warming must never break patrol
            log_event(
                log,
                "SENTINEL_AUDIO_PREWARM_FAILED",
                commune_code=commune_code,
                error=str(exc),
            )

    async def run(self) -> PatrolSummary:
        started = time.monotonic()
        summary, transitions = await self._pipeline.sync()

        pending: list[tuple[SentinelAlert, AssessmentResult]] = []
        debounced: list[str] = []
        eligible: list[RiskTransition] = []
        now = datetime.now(timezone.utc)
        debounce = timedelta(hours=self._settings.sentinel_debounce_hours)

        for transition in transitions:
            current = transition.current.tier
            previous = transition.previous or RiskTier.NORMAL
            if current.severity <= previous.severity:  # only escalations
                continue
            if current.severity < self._escalate_from.severity:
                continue

            commune_code = transition.commune.code
            last = await self._pipeline.repo.last_sentinel_alert(commune_code)
            if last is not None:
                elapsed = now - last.dispatched_at.astimezone(timezone.utc)
                # BUG-03: only suppress alerts at the same or lower severity;
                # escalations to a strictly higher tier (WARNING -> DANGER) bypass debounce.
                if elapsed < debounce and current.severity <= last.risk_tier.severity:
                    debounced.append(commune_code)
                    continue

            eligible.append(transition)

        dispatch_sem = asyncio.Semaphore(PATROL_DISPATCH_CONCURRENCY)

        async def _dispatch_transition(
            transition: RiskTransition,
        ) -> tuple[list[tuple[SentinelAlert, AssessmentResult]], tuple[int, float, str] | None]:
            commune_code = transition.commune.code
            local_pending: list[tuple[SentinelAlert, AssessmentResult]] = []
            async with dispatch_sem:
                subscribers = await self._pipeline.repo.subscriptions_for_commune(commune_code)
                by_stage: dict[CropStage, list[Subscription]] = {}
                for sub in subscribers:
                    effective = sub.crop_stage or CropStage.RIPENING  # INV-03 protective default
                    by_stage.setdefault(effective, []).append(sub)

                plan: list[tuple[CropStage, list[Subscription]]] = []
                for stage in (
                    CropStage.RIPENING,
                    CropStage.TILLERING,
                    CropStage.VEGETATIVE,
                    CropStage.FLOWERING,
                ):
                    group = by_stage.get(stage)
                    if group is not None:
                        plan.append((stage, group))
                if not plan or plan[0][0] is not CropStage.RIPENING:
                    # No ripening subscribers: still post the conservative version publicly.
                    plan.insert(0, (CropStage.RIPENING, []))

                ripening_synthesized = False
                for index, (stage, group) in enumerate(plan):
                    want_audio = bool(group)
                    assessment = await self._pipeline.assess_commune(
                        commune_code, stage, with_audio=want_audio
                    )
                    if stage is CropStage.RIPENING and want_audio and assessment.audio is not None:
                        ripening_synthesized = True
                    alert = SentinelAlert(
                        commune_id=commune_code,
                        station_id=transition.current.station_id,
                        risk_tier=assessment.risk_tier,
                        lead_time_hours=assessment.lead_time_hours,
                        directive_title=(
                            assessment.directives[0].title_en if assessment.directives else ""
                        ),
                        bulletin_text=assessment.khmer_bulletin,
                        audio_url=assessment.audio.url if assessment.audio else None,
                        dispatched_at=datetime.now(timezone.utc),
                        recipients_count=0,
                    )
                    delivered = await self._dispatcher(alert, group, index == 0)
                    alert = alert.model_copy(update={"recipients_count": delivered})
                    for sub in group:
                        await self._pipeline.repo.touch_notified(
                            sub.telegram_chat_id, commune_code, assessment.risk_tier, now
                        )
                    local_pending.append((alert, assessment))
                    log_event(
                        log,
                        "SENTINEL_ALERT_DISPATCHED",
                        commune_code=commune_code,
                        risk_tier=assessment.risk_tier.value,
                        crop_stage=stage.value,
                        recipients=delivered,
                        audio=bool(assessment.audio),
                    )

                prewarm_candidate: tuple[int, float, str] | None = None
                if (
                    not ripening_synthesized
                    and self._pipeline.audio_store is not None
                    and self._settings.has_gemini
                ):
                    prewarm_candidate = (
                        transition.current.tier.severity,
                        transition.current.score,
                        commune_code,
                    )
                return local_pending, prewarm_candidate

        prewarm_candidates: list[tuple[int, float, str]] = []
        if eligible:
            results = await asyncio.gather(*(_dispatch_transition(t) for t in eligible))
            for local_pending, prewarm_candidate in results:
                pending.extend(local_pending)
                if prewarm_candidate is not None:
                    prewarm_candidates.append(prewarm_candidate)

        prewarm_candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        prewarm_communes = [code for _, _, code in prewarm_candidates[:MAX_PREWARM_COMMUNES]]

        if prewarm_communes:
            semaphore = asyncio.Semaphore(4)

            async def _bounded_prewarm(code: str) -> None:
                async with semaphore:
                    await self._presynthesize_commune_audio(code)

            await asyncio.gather(
                *(_bounded_prewarm(code) for code in prewarm_communes),
                return_exceptions=True,
            )

        run = await self._pipeline.repo.save_patrol_run(
            PatrolRun(
                run_at=now,
                stations_polled=summary.stations_polled,
                communes_evaluated=summary.communes_evaluated,
                alerts_dispatched_count=len(pending),
                execution_duration_ms=int((time.monotonic() - started) * 1000),
            )
        )

        alerts: list[SentinelAlert] = []
        for alert, assessment in pending:
            saved = alert.model_copy(update={"patrol_run_id": run.id})
            await self._pipeline.repo.save_sentinel_alert(saved)
            await self._pipeline.repo.save_alert_dispatch(
                alert.commune_id,
                assessment.risk_tier,
                assessment.directives[0].family if assessment.directives else "MONITOR",
                assessment.khmer_bulletin,
                assessment.audio.uri if assessment.audio else None,
                assessment.audio.duration_seconds if assessment.audio else None,
                alert.recipients_count,
            )
            alerts.append(saved)

        log_event(
            log,
            "SENTINEL_PATROL_RUN",
            run_id=run.id,
            stations_polled=run.stations_polled,
            communes_evaluated=run.communes_evaluated,
            alerts=run.alerts_dispatched_count,
            debounced=len(debounced),
            prewarmed_audio=len(prewarm_communes),
            duration_ms=run.execution_duration_ms,
        )
        return PatrolSummary(
            run=run, alerts=alerts, debounced=debounced, transitions=transitions
        )
