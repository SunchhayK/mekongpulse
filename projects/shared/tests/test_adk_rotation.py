"""Model rotation on the ADK path and the native google-genai ReAct path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mekong_shared import adk_agent
from mekong_shared.adk_agent import GeminiFunctionCaller, _rotating_llm_class
from mekong_shared.config import Settings


class QuotaError(Exception):
    status_code = 429


class FakeRequest:
    def __init__(self, model: str = "original") -> None:
        self.model = model

    def model_copy(self, update=None):
        return FakeRequest((update or {}).get("model", self.model))


class FakeLlm:
    def __init__(self, model: str, outcomes: list) -> None:
        self.model = model
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate_content_async(self, request, stream: bool = False):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        yield outcome


def test_adk_wrapper_rotates_on_quota_and_remembers(monkeypatch):
    primary = FakeLlm("unit-adk-primary", [QuotaError("429 RESOURCE_EXHAUSTED")])
    secondary = FakeLlm("unit-adk-secondary", ["answer", "answer two"])

    def fake_llm(model: str):
        return {
            "unit-adk-primary": primary,
            "unit-adk-secondary": secondary,
        }[model]

    monkeypatch.setattr(adk_agent, "_adk_llm", fake_llm)
    wrapper_cls = _rotating_llm_class()
    wrapper = wrapper_cls(
        model="unit-adk-primary",
        models=["unit-adk-primary", "unit-adk-secondary"],
    )

    async def collect():
        return [response async for response in wrapper.generate_content_async(FakeRequest())]

    assert asyncio.run(collect()) == ["answer"]
    # The exhausted primary is skipped on the next call.
    assert asyncio.run(collect()) == ["answer two"]
    assert primary.calls == 1
    assert secondary.calls == 2


def test_adk_wrapper_does_not_retry_after_partial_output(monkeypatch):
    class PartialThenQuota:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_content_async(self, request, stream: bool = False):
            self.calls += 1
            yield "partial"
            raise QuotaError("429 RESOURCE_EXHAUSTED")

    primary = PartialThenQuota()
    secondary_calls: list[str] = []

    def fake_llm(model: str):
        if model == "unit-partial-primary":
            return primary
        secondary_calls.append(model)
        return FakeLlm(model, ["must not run"])

    monkeypatch.setattr(adk_agent, "_adk_llm", fake_llm)
    wrapper = _rotating_llm_class()(
        model="unit-partial-primary",
        models=["unit-partial-primary", "unit-partial-secondary"],
    )

    async def collect():
        return [response async for response in wrapper.generate_content_async(FakeRequest())]

    with pytest.raises(QuotaError):
        asyncio.run(collect())
    assert secondary_calls == []


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        if model == "unit-native-primary":
            raise QuotaError("429 RESOURCE_EXHAUSTED")
        part = SimpleNamespace(function_call=None, text="ok")
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )


def test_native_caller_rotates_on_quota():
    settings = Settings(
        _env_file=None,
        environment="development",
        gemini_api_key="test-key",
        gemini_text_model="unit-native-primary",
        gemini_fallback_models="unit-native-secondary",
    )
    models = FakeModels()
    caller = GeminiFunctionCaller(settings, client=SimpleNamespace(models=models))

    step = asyncio.run(caller.step([{"role": "user", "parts": [{"text": "hi"}]}]))

    assert step.text == "ok"
    assert models.calls == ["unit-native-primary", "unit-native-secondary"]
