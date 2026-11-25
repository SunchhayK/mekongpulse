"""Sentinel -> Telegram dispatch: batched, rate-limited subscriber fan-out + channel post."""

from __future__ import annotations

import asyncio
import logging
import time
from io import BytesIO
from typing import Sequence

from mekong_shared.models import SentinelAlert, Subscription
from mekong_shared.pipeline import Pipeline
from mekong_shared.tasks import CloudTasksQueue, TaskQueue

log = logging.getLogger("mekongpulse.bot")

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
DEFAULT_WEB_BASE_URL = "https://ai-builder-cup-9f8cd.web.app"  # fallback if settings lacks web_base_url
DEFAULT_BATCH_SIZE = 25
DEFAULT_MAX_PER_SECOND = 25.0  # stay safely under Telegram's 30 msg/sec cap
DEFAULT_CONCURRENCY = 8


def _chat_id(value: str | int):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


async def _audio_bytes(pipeline: Pipeline, url: str) -> bytes | None:
    """Fetch local-store audio so dev/staging works without a public URL."""
    marker = "/audio/"
    index = url.find(marker)
    if index < 0 or pipeline.audio_store is None:
        return None
    key = url[index + len(marker) :].split("?", 1)[0]
    try:
        return await pipeline.audio_store.get(f"local:{key}")
    except Exception:  # noqa: BLE001 - audio is best-effort, text always goes out
        return None


class _TokenBucket:
    """Simple async rate limiter capping dispatches to <= `rate` per second."""

    def __init__(self, rate: float) -> None:
        self._rate = max(1.0, float(rate))
        self._interval = 1.0 / self._rate
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next_slot <= now:
                self._next_slot = now + self._interval
                return
            wait = self._next_slot - now
            self._next_slot += self._interval
        if wait > 0:
            await asyncio.sleep(wait)


async def send_alert_to_chat(
    pipeline: Pipeline,
    bot,
    chat_id: str | int,
    alert: SentinelAlert,
    *,
    cached_audio: bytes | None = None,
) -> None:
    """Deliver a single alert (voice note if available, otherwise text) to one chat."""
    text = alert.bulletin_text[:MESSAGE_LIMIT]
    resolved_chat = _chat_id(chat_id)
    if alert.audio_url:
        if alert.audio_url.startswith("https://"):
            await bot.send_voice(
                chat_id=resolved_chat, voice=alert.audio_url, caption=text[:CAPTION_LIMIT]
            )
            return
        data = cached_audio if cached_audio is not None else await _audio_bytes(pipeline, alert.audio_url)
        if data:
            await bot.send_voice(
                chat_id=resolved_chat, voice=BytesIO(data), caption=text[:CAPTION_LIMIT]
            )
            return
    await bot.send_message(chat_id=resolved_chat, text=text)


async def dispatch_alert_batch(
    pipeline: Pipeline,
    bot,
    alert: SentinelAlert,
    chat_ids: Sequence[str | int],
    *,
    max_per_second: float = DEFAULT_MAX_PER_SECOND,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> int:
    """Deliver one batch of alerts with bounded concurrency and <=25 msg/sec rate limit."""
    if not chat_ids:
        return 0

    cached_audio: bytes | None = None
    if alert.audio_url and not alert.audio_url.startswith("https://"):
        cached_audio = await _audio_bytes(pipeline, alert.audio_url)

    bucket = _TokenBucket(max_per_second)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _deliver_one(raw_chat_id: str | int) -> int:
        async with semaphore:
            await bucket.acquire()
            try:
                await send_alert_to_chat(
                    pipeline, bot, raw_chat_id, alert, cached_audio=cached_audio
                )
                return 1
            except Exception as exc:  # noqa: BLE001 - one bad chat must not stop the batch
                log.warning("alert delivery failed for chat %s: %s", raw_chat_id, exc)
                return 0

    results = await asyncio.gather(*(_deliver_one(cid) for cid in chat_ids))
    return sum(results)


def make_telegram_dispatcher(
    pipeline: Pipeline,
    bot,
    *,
    task_queue: TaskQueue | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_per_second: float = DEFAULT_MAX_PER_SECOND,
    concurrency: int = DEFAULT_CONCURRENCY,
):
    """Returns the Sentinel dispatcher callable bound to a PTB Bot.

    When `task_queue` is a `CloudTasksQueue`, subscriber batches are enqueued onto
    Cloud Tasks for durable, rate-limited fan-out. Otherwise, batches are dispatched
    in-process with bounded async concurrency capped at `<= 25 msg/sec`.
    """
    settings = pipeline.settings
    chunk_size = max(1, batch_size)

    async def dispatch(
        alert: SentinelAlert,
        subscribers: list[Subscription],
        post_to_channel: bool = True,
    ) -> int:
        chat_ids = [sub.telegram_chat_id for sub in subscribers]
        delivered = 0

        if isinstance(task_queue, CloudTasksQueue) and chat_ids:
            alert_payload = alert.model_dump(mode="json")
            for idx in range(0, len(chat_ids), chunk_size):
                batch = chat_ids[idx : idx + chunk_size]
                dedup_key = (
                    f"dispatch:{alert.patrol_run_id or 'ad-hoc'}:"
                    f"{alert.commune_id}:{alert.risk_tier.value}:b{idx // chunk_size}"
                )
                try:
                    await task_queue.enqueue_dispatch_batch(
                        alert_payload=alert_payload,
                        chat_ids=batch,
                        dedup_key=dedup_key,
                    )
                    delivered += len(batch)
                except Exception as exc:  # noqa: BLE001 - fall back to direct send on enqueue error
                    log.warning("cloud tasks dispatch enqueue failed, falling back: %s", exc)
                    delivered += await dispatch_alert_batch(
                        pipeline,
                        bot,
                        alert,
                        batch,
                        max_per_second=max_per_second,
                        concurrency=concurrency,
                    )
        else:
            for idx in range(0, len(chat_ids), chunk_size):
                batch = chat_ids[idx : idx + chunk_size]
                delivered += await dispatch_alert_batch(
                    pipeline,
                    bot,
                    alert,
                    batch,
                    max_per_second=max_per_second,
                    concurrency=concurrency,
                )

        channel = settings.telegram_broadcast_channel_id if post_to_channel else None
        if channel:
            base = getattr(settings, "web_base_url", None) or DEFAULT_WEB_BASE_URL
            link = f"\n\n{base.rstrip('/')}/km/commune?code={alert.commune_id}"
            try:
                await bot.send_message(
                    chat_id=_chat_id(channel),
                    text=alert.bulletin_text[: MESSAGE_LIMIT - len(link)] + link,
                )
            except Exception as exc:  # noqa: BLE001 - channel post is best-effort
                log.warning("broadcast channel post failed: %s", exc)
        return delivered

    return dispatch
