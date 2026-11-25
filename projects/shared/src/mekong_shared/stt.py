"""Server-side speech-to-text for the officer assistant's voice input (FR-08, IMP-06).

Same degradation discipline as tts.py: no key, missing SDK, provider errors
(quota, safety blocks, transport), and empty transcripts all surface as
`TranscriptionUnavailable` so the gateway answers 503 instead of 500. Uses
`ModelRotator` with optional `StateStore` cooldowns and Vertex AI ADC / Workload
Identity IAM when `use_vertex_ai=True`.
"""

from __future__ import annotations

import asyncio

from .cache import StateStore
from .config import Settings
from .model_rotation import create_genai_client, rotator_for


class TranscriptionUnavailable(Exception):
    """Raised when Gemini STT cannot be used (no key / SDK missing / provider error)."""


TRANSCRIBE_INSTRUCTION = (
    "Transcribe this speech to text. It is Khmer or English. "
    "Return only the transcript."
)
TRANSCRIBE_INSTRUCTION_BY_LOCALE = {
    "km": "Transcribe this speech to text. It is Khmer. Return only the transcript.",
    "en": "Transcribe this speech to text. It is English. Return only the transcript.",
}


def transcribe_instruction(locale_hint: str | None = None) -> str:
    """One short inline instruction (no developer-instruction channel for text+audio)."""
    return TRANSCRIBE_INSTRUCTION_BY_LOCALE.get(locale_hint or "", TRANSCRIBE_INSTRUCTION)


def _get_client(settings: Settings):
    if not settings.has_gemini:
        raise TranscriptionUnavailable("GEMINI_API_KEY / Vertex configuration is missing")
    return create_genai_client(settings)


def _extract_transcript(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise TranscriptionUnavailable("Gemini returned no candidates")
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(part.text for part in parts if getattr(part, "text", None)).strip()


async def transcribe_audio(
    settings: Settings,
    audio: bytes,
    mime_type: str,
    locale_hint: str | None = None,
    *,
    state_store: StateStore | None = None,
) -> str:
    """Audio bytes -> stripped transcript. Raises TranscriptionUnavailable, never others."""
    client = _get_client(settings)
    instruction = transcribe_instruction(locale_hint)
    rotator = rotator_for(settings.gemini_model_chain, state_store=state_store)
    contents = [
        {
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": audio}},
                {"text": instruction},
            ],
        }
    ]

    transcript: str | None = None
    last_error: BaseException | None = None
    try:
        for model in await rotator.ordered_async():
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=contents,
                )
            except Exception as exc:  # noqa: BLE001 - provider failure, rotate
                if not rotator.should_rotate(exc):
                    raise
                await rotator.mark_failed_async(model, exc)
                last_error = exc
                continue
            await rotator.mark_ok_async(model)
            transcript = _extract_transcript(response)
            break
    except TranscriptionUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - voice input is best-effort
        raise TranscriptionUnavailable(f"transcription request failed: {exc}") from exc

    if transcript is None:
        if last_error is not None:
            raise TranscriptionUnavailable(f"transcription request failed: {last_error}") from last_error
        raise TranscriptionUnavailable("No Gemini model configured")
    if not transcript:
        raise TranscriptionUnavailable("Gemini returned an empty transcript")
    return transcript
