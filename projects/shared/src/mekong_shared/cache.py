"""Shared runtime state store (IMP-01).

Provides a thin async key-value / rate-limit / cooldown abstraction with an
in-memory default and an optional Redis backend (`redis.asyncio`) when
`REDIS_URL` is configured. Falls back cleanly to in-memory if Redis is not
installed or unreachable.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Protocol

from .config import Settings

log = logging.getLogger(__name__)


class StateStore(Protocol):
    async def get_json(self, key: str) -> Any | None: ...
    async def set_json(self, key: str, value: Any, ttl_seconds: float | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def incr_window(self, key: str, window_seconds: float) -> int: ...
    async def get_timestamp(self, key: str) -> float | None: ...
    async def set_timestamp(
        self, key: str, value: float, ttl_seconds: float | None = None
    ) -> None: ...
    async def close(self) -> None: ...


class InMemoryStateStore:
    """Process-local StateStore used in development, tests, and Redis fallback."""

    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, tuple[Any, float | None]] = {}
        self._windows: dict[str, tuple[int, float]] = {}

    def _is_expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and self._clock() >= expires_at

    async def get_json(self, key: str) -> Any | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._is_expired(expires_at):
            self._values.pop(key, None)
            return None
        return value

    async def set_json(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        expires_at = (self._clock() + ttl_seconds) if ttl_seconds is not None else None
        self._values[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)
        self._windows.pop(key, None)

    async def incr_window(self, key: str, window_seconds: float) -> int:
        now = self._clock()
        entry = self._windows.get(key)
        if entry is None or now >= entry[1]:
            count = 1
            self._windows[key] = (count, now + window_seconds)
            return count
        count = entry[0] + 1
        self._windows[key] = (count, entry[1])
        return count

    async def get_timestamp(self, key: str) -> float | None:
        val = await self.get_json(key)
        return float(val) if val is not None else None

    async def set_timestamp(
        self, key: str, value: float, ttl_seconds: float | None = None
    ) -> None:
        await self.set_json(key, float(value), ttl_seconds=ttl_seconds)

    async def close(self) -> None:
        self._values.clear()
        self._windows.clear()


class RedisStateStore:
    """Async Redis StateStore with automatic in-memory fallback on errors."""

    def __init__(self, client: Any, *, fallback: InMemoryStateStore | None = None) -> None:
        self._client = client
        self._fallback = fallback or InMemoryStateStore()

    async def get_json(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning("redis get_json failed, using in-memory fallback: %s", exc)
            return await self._fallback.get_json(key)

    async def set_json(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        payload = json.dumps(value, default=str)
        try:
            if ttl_seconds is not None:
                ex = max(1, int(math.ceil(ttl_seconds)))
                await self._client.set(key, payload, ex=ex)
            else:
                await self._client.set(key, payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("redis set_json failed, using in-memory fallback: %s", exc)
            await self._fallback.set_json(key, value, ttl_seconds=ttl_seconds)

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            log.warning("redis delete failed, using in-memory fallback: %s", exc)
        await self._fallback.delete(key)

    async def incr_window(self, key: str, window_seconds: float) -> int:
        try:
            count = int(await self._client.incr(key))
            if count == 1:
                ex = max(1, int(math.ceil(window_seconds)))
                await self._client.expire(key, ex)
            return count
        except Exception as exc:  # noqa: BLE001
            log.warning("redis incr_window failed, using in-memory fallback: %s", exc)
            return await self._fallback.incr_window(key, window_seconds)

    async def get_timestamp(self, key: str) -> float | None:
        val = await self.get_json(key)
        return float(val) if val is not None else None

    async def set_timestamp(
        self, key: str, value: float, ttl_seconds: float | None = None
    ) -> None:
        await self.set_json(key, float(value), ttl_seconds=ttl_seconds)

    async def close(self) -> None:
        try:
            if hasattr(self._client, "aclose"):
                await self._client.aclose()
            elif hasattr(self._client, "close"):
                await self._client.close()
        except Exception:  # noqa: BLE001
            pass
        await self._fallback.close()


def create_state_store(settings: Settings | None = None) -> StateStore:
    """Create a RedisStateStore when redis_url is configured, else InMemoryStateStore."""
    redis_url = settings.redis_url if settings is not None else None
    if not redis_url:
        return InMemoryStateStore()
    try:
        import redis.asyncio as aioredis  # type: ignore[import-not-found]
    except ImportError:
        log.warning("REDIS_URL is set but redis package is not installed; using InMemoryStateStore")
        return InMemoryStateStore()
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        return RedisStateStore(client)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to initialize Redis client (%s); using InMemoryStateStore", exc)
        return InMemoryStateStore()
