"""MekongAdvisor ReAct agent (FR-08, AC-04).

Primary engine: Google ADK `LlmAgent` over the tool registry (when
`google-adk` is installed). Fallback engine: an equivalent ReAct loop over
google-genai function calling — same tools, same observable behavior (the
agent calls `get_station_telemetry` and `evaluate_crop_directive` and reasons
over results). The loop is engine-agnostic so tests can drive it with a
scripted LLM.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from .adk_tools import FUNCTION_DECLARATIONS, AdvisorTools
from .config import Settings
from .models import ConversationTurn

log = logging.getLogger("mekongpulse.advisor")

ADVISOR_INSTRUCTION = """You are MekongPulse Advisor, the agronomic flood advisor for Cambodian
commune chiefs and smallholder rice farmers along the Mekong, Bassac, and Tonle Sap rivers.

Rules:
- Always ground answers in tool data. Call get_station_telemetry and/or
  evaluate_crop_directive before giving any water level, risk tier, lead time, or
  field-action advice. Never invent water elevations or stage values (INV-01).
- When telemetry is estimated (fallback/cache), say so and advise conservatively (INV-03).
- Answer in the user's language: Khmer if they write Khmer, otherwise English. Keep the
  register respectful and the sentences short and concrete.
- Include exact lead times and harvest/fertilizer guidance when relevant.
- If the location is outside Cambodia, ask the caller for their commune name and use
  search_commune.
"""


class AdvisorUnavailable(Exception):
    pass


@dataclass
class StepResult:
    text: str | None = None
    calls: list[tuple[str, dict]] = field(default_factory=list)


class StepLLM(Protocol):
    async def step(self, contents: list[dict]) -> StepResult: ...


class ScriptedLLM:
    """Deterministic test double: yields canned steps and records prompts."""

    def __init__(self, steps: list[StepResult]) -> None:
        self._steps = list(steps)
        self.contents_seen: list[list[dict]] = []

    async def step(self, contents: list[dict]) -> StepResult:
        self.contents_seen.append(contents)
        if not self._steps:
            return StepResult(text="(script exhausted)")
        return self._steps.pop(0)


class GeminiFunctionCaller:
    """google-genai function-calling step (sync SDK wrapped in a thread)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    async def step(self, contents: list[dict]) -> StepResult:
        if not self._settings.has_gemini:
            raise AdvisorUnavailable("GEMINI_API_KEY / Vertex configuration is missing")

        def _run() -> StepResult:
            from google import genai

            if self._client is None:
                if self._settings.use_vertex_ai:
                    self._client = genai.Client(
                        vertexai=True,
                        project=self._settings.vertex_project,
                        location=self._settings.vertex_location,
                    )
                else:
                    self._client = genai.Client(api_key=self._settings.gemini_api_key)
            response = self._client.models.generate_content(
                model=self._settings.gemini_text_model,
                contents=contents,
                config={
                    "temperature": 0.3,
                    "system_instruction": ADVISOR_INSTRUCTION,
                    "tools": [{"function_declarations": FUNCTION_DECLARATIONS}],
                },
            )
            parts = []
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                parts = candidates[0].content.parts or []
            calls: list[tuple[str, dict]] = []
            texts: list[str] = []
            for part in parts:
                function_call = getattr(part, "function_call", None)
                if function_call is not None and getattr(function_call, "name", None):
                    calls.append((function_call.name, dict(function_call.args or {})))
                else:
                    text = getattr(part, "text", None)
                    if text:
                        texts.append(text)
            return StepResult(text="\n".join(texts).strip() or None, calls=calls)

        return await asyncio.to_thread(_run)


async def run_react(
    tools: AdvisorTools,
    history: list[ConversationTurn],
    user_text: str,
    llm: StepLLM,
    *,
    max_steps: int = 6,
) -> str:
    contents: list[dict] = []
    for turn in history:
        role = "user" if turn.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.content}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    last_text: str | None = None
    for _ in range(max_steps):
        step = await llm.step(contents)
        if step.text:
            last_text = step.text
        if not step.calls:
            return step.text or last_text or ""
        contents.append(
            {
                "role": "model",
                "parts": [
                    {"function_call": {"name": name, "args": args}} for name, args in step.calls
                ],
            }
        )
        responses: list[tuple[str, dict]] = []
        for name, args in step.calls:
            method = getattr(tools, name, None)
            if method is None:
                responses.append((name, {"error": f"unknown tool {name}"}))
                continue
            try:
                result = await method(**args)
            except TypeError as exc:
                result = {"error": f"invalid arguments: {exc}"}
            except Exception as exc:  # noqa: BLE001 - surface tool errors to the LLM
                result = {"error": str(exc)}
            responses.append((name, result))
        contents.append(
            {
                "role": "user",
                "parts": [
                    {"function_response": {"name": name, "response": result}}
                    for name, result in responses
                ],
            }
        )
    return last_text or "(advisor reached the tool-call limit)"


def build_adk_agent(tools: AdvisorTools, settings: Settings):
    """Best-effort Google ADK LlmAgent; returns None when ADK is unavailable."""
    try:
        from google.adk.agents import LlmAgent  # type: ignore
    except Exception:  # noqa: BLE001 - ADK is optional at runtime
        return None
    try:
        return LlmAgent(
            name="mekong_advisor",
            model=settings.gemini_text_model,
            instruction=ADVISOR_INSTRUCTION,
            tools=[getattr(tools, decl["name"]) for decl in FUNCTION_DECLARATIONS],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ADK agent construction failed: %s", exc)
        return None


async def _run_adk(agent, history: list[ConversationTurn], user_text: str) -> str:
    from google.adk.runners import InMemoryRunner  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    runner = InMemoryRunner(agent=agent, app_name="mekongpulse")
    session = await runner.session_service.create_session(
        app_name="mekongpulse", user_id="telegram"
    )
    prefix = ""
    if history:
        transcript = "\n".join(
            f"{turn.role}: {turn.content}" for turn in history[-6:]
        )
        prefix = f"Conversation so far:\n{transcript}\n\n"
    message = genai_types.Content(
        role="user", parts=[genai_types.Part(text=prefix + user_text)]
    )
    final_text = ""
    async for event in runner.run_async(
        user_id="telegram", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts)
    return final_text.strip()


async def answer(
    tools: AdvisorTools,
    history: list[ConversationTurn],
    user_text: str,
    settings: Settings,
    *,
    llm: StepLLM | None = None,
) -> str:
    """One advisor turn. `llm` injects a scripted/deterministic engine for tests."""
    if llm is not None:
        return await run_react(tools, history, user_text, llm)
    if not settings.has_gemini:
        raise AdvisorUnavailable("advisor requires GEMINI_API_KEY")
    agent = build_adk_agent(tools, settings)
    if agent is not None:
        try:
            return await _run_adk(agent, history, user_text)
        except Exception as exc:  # noqa: BLE001 - fall back to the native loop
            log.warning("ADK run failed, falling back to native ReAct loop: %s", exc)
    return await run_react(tools, history, user_text, GeminiFunctionCaller(settings))
