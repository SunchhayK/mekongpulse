"""Ordered Gemini model fallback for the advisor.

Free-tier quota is counted per project per model per day, so an exhausted
primary can hand the next *model call* to another Flash model. Rotation happens
at the LLM-call level (never by replaying a turn), which keeps tool side effects
— notably ``publish_to_channel`` — from firing twice.

Provider failures are given a short cooldown so subsequent calls skip the dead
model in-process:

- quota / 429 ``RESOURCE_EXHAUSTED``: one hour (the daily quota resets later)
- overload / 503 ``UNAVAILABLE``: one minute
- missing model / 404: six hours (e.g. a retired preview id)

When every model is cooling down the order still falls back to the full chain,
because a quota window may have reset early. The state is process-local; the
stabilisation deployment runs a single API worker.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable

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
    """Ordered model chain with in-process cooldowns; safe across threads."""

    def __init__(self, models: Iterable[str]) -> None:
        self.models: tuple[str, ...] = tuple(
            dict.fromkeys(model.strip() for model in models if model and model.strip())
        )
        self._cooldowns: dict[str, float] = {}
        self._lock = threading.Lock()

    def ordered(self) -> list[str]:
        """Healthy models first (in configured order), cooling models last."""
        now = time.monotonic()
        with self._lock:
            fresh = [model for model in self.models if self._cooldowns.get(model, 0.0) <= now]
            cooling = [model for model in self.models if self._cooldowns.get(model, 0.0) > now]
        return fresh + cooling

    def should_rotate(self, exc: BaseException) -> bool:
        return failure_kind(exc) is not None

    def mark_failed(self, model: str, exc: BaseException) -> None:
        kind = failure_kind(exc)
        if kind is None:
            return
        with self._lock:
            self._cooldowns[model] = time.monotonic() + _FAILURE_COOLDOWNS[kind]

    def mark_ok(self, model: str) -> None:
        with self._lock:
            self._cooldowns.pop(model, None)


_ROTATORS: dict[tuple[str, ...], ModelRotator] = {}
_ROTATORS_LOCK = threading.Lock()


def rotator_for(models: Iterable[str]) -> ModelRotator:
    """Shared rotator per chain so ADK and the native loop see the same cooldowns."""
    key = tuple(dict.fromkeys(model.strip() for model in models if model and model.strip()))
    with _ROTATORS_LOCK:
        rotator = _ROTATORS.get(key)
        if rotator is None:
            rotator = ModelRotator(key)
            _ROTATORS[key] = rotator
        return rotator
