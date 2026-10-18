"""Server-side speech-to-text for the officer assistant's voice input (FR-08).

Same degradation discipline as tts.py: no key, missing SDK, provider errors
(quota, safety blocks, transport), and empty transcripts all surface as
`TranscriptionUnavailable` so the gateway answers 503 instead of 500. The
sync google-genai call is wrapped in a thread like adk_agent.py does.
"""

from __future__ import annotations

import asyncio

from .config import Settings


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
    from google import genai

    if settings.use_vertex_ai:
        return genai.Client(
            vertexai=True,
            project=settings.vertex_project,
            location=settings.vertex_location,
        )
    return genai.Client(api_key=settings.gemini_api_key)


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
) -> str:
    """Audio bytes -> stripped transcript. Raises TranscriptionUnavailable, never others."""
    client = _get_client(settings)
    instruction = transcribe_instruction(locale_hint)

    def _generate() -> str:
        response = client.models.generate_content(
            model=settings.gemini_text_model,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": mime_type, "data": audio}},
                        {"text": instruction},
                    ],
                }
            ],
        )
        return _extract_transcript(response)

    try:
        transcript = await asyncio.to_thread(_generate)
    except TranscriptionUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - voice input is best-effort
        # Quota (429), safety blocks, and transient API failures degrade to
        # "transcription unavailable" in the UI; a 500 on /advisor/transcribe
        # would break that contract.
        raise TranscriptionUnavailable(f"transcription request failed: {exc}") from exc
    if not transcript:
        raise TranscriptionUnavailable("Gemini returned an empty transcript")
    return transcript
