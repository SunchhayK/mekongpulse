"""Ordered model fallback: classification, cooldown ordering, shared rotators."""

from __future__ import annotations

from mekong_shared import model_rotation
from mekong_shared.model_rotation import ModelRotator, failure_kind, rotator_for


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_failure_kind_classifies_provider_failures():
    assert failure_kind(ProviderError("quota", 429)) == "quota"
    assert failure_kind(ProviderError("RESOURCE_EXHAUSTED: daily limit")) == "quota"
    assert failure_kind(ProviderError("overloaded", 503)) == "overload"
    assert failure_kind(ProviderError("This model is currently experiencing high demand")) == "overload"
    assert failure_kind(ProviderError("model is not found", 404)) == "missing"
    assert failure_kind(ProviderError("response parsing failed")) is None


def test_cause_chain_is_classified():
    root = ProviderError("429 RESOURCE_EXHAUSTED", 429)
    wrapped = RuntimeError("ADK run failed")
    wrapped.__cause__ = root
    assert failure_kind(wrapped) == "quota"


def test_cooling_model_moves_last_then_returns(monkeypatch):
    now = 1_000.0
    monkeypatch.setattr(model_rotation.time, "monotonic", lambda: now)
    rotator = ModelRotator(["primary", "secondary", "third"])

    rotator.mark_failed("primary", ProviderError("quota", 429))
    assert rotator.ordered() == ["secondary", "third", "primary"]

    now += model_rotation.QUOTA_COOLDOWN_SECONDS + 1
    assert rotator.ordered() == ["primary", "secondary", "third"]


def test_mark_ok_clears_cooldown(monkeypatch):
    now = 2_000.0
    monkeypatch.setattr(model_rotation.time, "monotonic", lambda: now)
    rotator = ModelRotator(["primary", "secondary"])
    rotator.mark_failed("primary", ProviderError("overloaded", 503))
    assert rotator.ordered() == ["secondary", "primary"]

    rotator.mark_ok("primary")
    assert rotator.ordered() == ["primary", "secondary"]


def test_unknown_failures_are_not_rotated():
    rotator = ModelRotator(["primary"])
    assert rotator.should_rotate(ProviderError("bad tool arguments")) is False


def test_rotator_is_shared_per_chain_and_deduped():
    first = rotator_for(["unit-one", " unit-two ", "unit-one"])
    second = rotator_for(["unit-one", "unit-two"])
    assert first is second
    assert first.models == ("unit-one", "unit-two")


def test_all_models_cooling_still_returns_the_chain(monkeypatch):
    now = 3_000.0
    monkeypatch.setattr(model_rotation.time, "monotonic", lambda: now)
    rotator = ModelRotator(["primary", "secondary"])
    rotator.mark_failed("primary", ProviderError("quota", 429))
    rotator.mark_failed("secondary", ProviderError("quota", 429))
    assert rotator.ordered() == ["primary", "secondary"]
