"""Tests for shared runtime StateStore (IMP-01)."""

from __future__ import annotations

import pytest

from mekong_shared.cache import InMemoryStateStore, RedisStateStore, create_state_store
from mekong_shared.config import Settings


async def test_in_memory_state_store_json_ttl_and_delete():
    now = [100.0]
    store = InMemoryStateStore(clock=lambda: now[0])

    await store.set_json("k1", {"a": 1}, ttl_seconds=10.0)
    assert await store.get_json("k1") == {"a": 1}

    now[0] += 11.0
    assert await store.get_json("k1") is None

    await store.set_json("k2", [1, 2, 3])
    await store.delete("k2")
    assert await store.get_json("k2") is None


async def test_in_memory_state_store_window_and_timestamp():
    now = [10.0]
    store = InMemoryStateStore(clock=lambda: now[0])

    assert await store.incr_window("rate:ip1", 60.0) == 1
    assert await store.incr_window("rate:ip1", 60.0) == 2
    now[0] += 61.0
    assert await store.incr_window("rate:ip1", 60.0) == 1

    await store.set_timestamp("cd:model", 1234.5, ttl_seconds=30.0)
    assert await store.get_timestamp("cd:model") == pytest.approx(1234.5)
    now[0] += 31.0
    assert await store.get_timestamp("cd:model") is None


class _FakeAsyncRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.closed = False

    async def get(self, key: str):
        if self.fail:
            raise ConnectionError("redis down")
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.fail:
            raise ConnectionError("redis down")
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def delete(self, key: str):
        if self.fail:
            raise ConnectionError("redis down")
        self.data.pop(key, None)

    async def incr(self, key: str) -> int:
        if self.fail:
            raise ConnectionError("redis down")
        val = int(self.data.get(key, "0")) + 1
        self.data[key] = str(val)
        return val

    async def expire(self, key: str, ex: int) -> None:
        self.ttls[key] = ex

    async def aclose(self) -> None:
        self.closed = True


async def test_redis_state_store_operations_and_fallback():
    client = _FakeAsyncRedis()
    store = RedisStateStore(client)

    await store.set_json("weather:08", {"rain": 12.0}, ttl_seconds=60.0)
    assert await store.get_json("weather:08") == {"rain": 12.0}
    assert client.ttls["weather:08"] == 60

    assert await store.incr_window("rl:1", 30.0) == 1
    assert await store.incr_window("rl:1", 30.0) == 2
    assert client.ttls["rl:1"] == 30

    await store.set_timestamp("cd:g", 99.5, ttl_seconds=15.0)
    assert await store.get_timestamp("cd:g") == pytest.approx(99.5)

    # Simulate Redis outage -> falls back to in-memory without raising
    client.fail = True
    await store.set_json("fallback_key", {"ok": True}, ttl_seconds=60.0)
    assert await store.get_json("fallback_key") == {"ok": True}
    assert await store.incr_window("rl:fallback", 60.0) == 1

    await store.close()
    assert client.closed


def test_create_state_store_defaults_to_in_memory():
    store = create_state_store(Settings(redis_url=None))
    assert isinstance(store, InMemoryStateStore)
