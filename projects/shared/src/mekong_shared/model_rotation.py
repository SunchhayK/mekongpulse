"""Ordered Gemini model fallback for all AI surfaces (IMP-01, IMP-06).

Free-tier quota is counted per project per model per day, so an exhausted
primary can hand the next *model call* to another Flash model. Rotation happens
at the LLM-call level (never by replaying a turn), which keeps tool side effects
— notably ``publish_to_channel`` — from firing twice.

Provider failures are given a short cooldown so subsequent calls skip the dead
model across threads and (when a `StateStore` such as Redis is configured)
across Cloud Run instances:

- quota / 429 ``RESOURCE_EXHAUSTED``: one hour (the daily quota resets later)
- overload / 503 ``UNAVAILABLE``: one minute
- missing model / 404: six hours (e.g. a retired preview id)

When every model is cooling down the order still falls back to the full chain,
because a quota window may have reset early.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable

from .cache import StateStore
from .config import Settings

QUOTA_COOLDOWN_SECONDS = 3600.0
OVERLOAD_COOLDOWN_SECONDS = 60.0
MISSING_MODEL_COOLDOWN_SECONDS = 6 * 3600.0

_FAILURE_COOLDOWNS = {
    "quota": QUOTA_COOLDOWN_SECONDS,
    "overload": OVERLOAD_COOLDOWN_SECONDS,
    "missing": MISSING_MODEL_COOLDOWN_SECONDS,
}

_QUOTA_MARKERS = ("RESOURCE_EXHAUSTED", "429")
_OVERLOAD_MARKERS = ("UNAVAILABLE", "HIGH DEMAND", "OVERLOADED", "503")
_MISSING_MARKERS = ("NOT_FOUND", "IS NOT FOUND", "NOT SUPPORTED FOR GENERATECONTENT", "404")

_COOLDOWN_KEY_PREFIX = "model_cooldown:"


def create_genai_client(settings: Settings):
    """Build a google-genai Client supporting Vertex AI ADC / Workload Identity.

    When `settings.use_vertex_ai` is True, authenticates via native GCP
    Application Default Credentials / Cloud Run Workload Identity IAM with zero
    static key files required.
    """
    from google import genai  # local import: optional in offline runs

    if settings.use_vertex_ai:
        kwargs: dict[str, object] = {
            "vertexai": True,
            "location": settings.vertex_location,
        }
        project = settings.vertex_project or settings.firestore_project
        if project:
            kwargs["project"] = project
        return genai.Client(**kwargs)
    return genai.Client(api_key=settings.gemini_api_key)


def _chain_text(exc: BaseException) -> str:
    """Concatenated messages of the exception and its causes (ADK wraps provider errors)."""
    parts: list[str] = []
    current: BaseException | None = exc
    for _ in range(6):
        if current is None:
            break
        parts.append(str(current))
        following = current.__cause__ or current.__context__
        if following is current:
            break
        current = following
    return "\n".join(parts)


def _status_code(exc: BaseException) -> int | None:
    for attribute in ("status_code", "code", "status"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def failure_kind(exc: BaseException) -> str | None:
    """Classify a provider failure as quota / overload / missing, or None."""
    text = _chain_text(exc).upper()
    code = _status_code(exc)
    if code == 429 or any(marker in text for marker in _QUOTA_MARKERS):
        return "quota"
    if code == 404 or any(marker in text for marker in _MISSING_MARKERS):
        return "missing"
    if code == 503 or any(marker in text for marker in _OVERLOAD_MARKERS):
        return "overload"
    return None


class ModelRotator:
    """Ordered model chain with in-process and optional StateStore-backed cooldowns."""

    def __init__(
        self,
        models: Iterable[str],
        *,
        state_store: StateStore | None = None,
    ) -> None:
        self.models: tuple[str, ...] = tuple(
            dict.fromkeys(model.strip() for model in models if model and model.strip())
        )
        self._cooldowns: dict[str, float] = {}
        self._lock = threading.Lock()
        self._state_store = state_store

    def bind_state_store(self, state_store: StateStore | None) -> None:
        self._state_store = state_store

    def ordered(self) -> list[str]:
        """Healthy models first (in configured order), cooling models last."""
        now = time.monotonic()
        with self._lock:
            fresh = [model for model in self.models if self._cooldowns.get(model, 0.0) <= now]
            cooling = [model for model in self.models if self._cooldowns.get(model, 0.0) > now]
        return fresh + cooling

    async def ordered_async(self) -> list[str]:
        """Like `ordered()`, merging shared cooldown timestamps from `StateStore`."""
        store = self._state_store
        if store is None:
            return self.ordered()

        now_mono = time.monotonic()
        now_wall = time.time()
        fresh: list[str] = []
        cooling: list[str] = []
        for model in self.models:
            with self._lock:
                local_until = self._cooldowns.get(model, 0.0)
            is_cooling = local_until > now_mono
            if not is_cooling:
                remote_until = await store.get_timestamp(f"{_COOLDOWN_KEY_PREFIX}{model}")
                if remote_until is not None and remote_until > now_wall:
                    is_cooling = True
                    with self._lock:
                        self._cooldowns[model] = now_mono + (remote_until - now_wall)
            if is_cooling:
                cooling.append(model)
            else:
                fresh.append(model)
        return fresh + cooling

    def should_rotate(self, exc: BaseException) -> bool:
        return failure_kind(exc) is not None

    def mark_failed(self, model: str, exc: BaseException) -> None:
        kind = failure_kind(exc)
        if kind is None:
            return
        with self._lock:
            self._cooldowns[model] = time.monotonic() + _FAILURE_COOLDOWNS[kind]

    async def mark_failed_async(self, model: str, exc: BaseException) -> None:
        kind = failure_kind(exc)
        if kind is None:
            return
        ttl = _FAILURE_COOLDOWNS[kind]
        with self._lock:
            self._cooldowns[model] = time.monotonic() + ttl
        if self._state_store is not None:
            await self._state_store.set_timestamp(
                f"{_COOLDOWN_KEY_PREFIX}{model}",
                time.time() + ttl,
                ttl_seconds=ttl,
            )

    def mark_ok(self, model: str) -> None:
        with self._lock:
            self._cooldowns.pop(model, None)

    async def mark_ok_async(self, model: str) -> None:
        self.mark_ok(model)
        if self._state_store is not None:
            await self._state_store.delete(f"{_COOLDOWN_KEY_PREFIX}{model}")


_ROTATORS: dict[tuple[str, ...], ModelRotator] = {}
_ROTATORS_LOCK = threading.Lock()
_DEFAULT_STATE_STORE: StateStore | None = None


def configure_rotator_state_store(state_store: StateStore | None) -> None:
    """Bind a shared StateStore (e.g. Redis) to all current and future rotators."""
    global _DEFAULT_STATE_STORE
    with _ROTATORS_LOCK:
        _DEFAULT_STATE_STORE = state_store
        for rotator in _ROTATORS.values():
            rotator.bind_state_store(state_store)


def rotator_for(
    models: Iterable[str],
    *,
    state_store: StateStore | None = None,
) -> ModelRotator:
    """Shared rotator per chain so ADK, native loop, bulletin, TTS, and STT share cooldowns."""
    key = tuple(dict.fromkeys(model.strip() for model in models if model and model.strip()))
    with _ROTATORS_LOCK:
        rotator = _ROTATORS.get(key)
        if rotator is None:
            rotator = ModelRotator(key, state_store=state_store or _DEFAULT_STATE_STORE)
            _ROTATORS[key] = rotator
        elif state_store is not None and rotator._state_store is None:
            rotator.bind_state_store(state_store)
        return rotator
