"""Khmer spoken voice notes via Gemini TTS (FR-05 / ADR-0005 / IMP-06).

Routes TTS synthesis through `ModelRotator` (`settings.gemini_tts_model_chain`)
and supports native Vertex AI Workload Identity / ADC IAM when
`use_vertex_ai=True`. Transcodes 24 kHz WAV PCM output to MP3 via `lameenc`.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import wave
from dataclasses import dataclass

from .cache import StateStore
from .config import Settings
from .model_rotation import create_genai_client, rotator_for

log = logging.getLogger("mekongpulse.tts")


class TTSUnavailable(Exception):
    """Raised when Gemini TTS cannot be used (no key / SDK missing)."""


class AudioEncodeError(Exception):
    pass


@dataclass(frozen=True)
class AudioArtifact:
    data: bytes
    mime_type: str
    duration_seconds: float


def wav_to_mp3(wav_bytes: bytes, bit_rate: int = 64) -> tuple[bytes, float]:
    """Transcode Gemini's 16-bit PCM WAV output to MP3. Returns (mp3, seconds)."""
    try:
        import lameenc
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise AudioEncodeError("lameenc is not installed") from exc
    try:
        with wave.open(io.BytesIO(wav_bytes)) as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            pcm = wav.readframes(frames)
    except wave.Error as exc:
        raise AudioEncodeError(f"invalid WAV payload: {exc}") from exc
    if sample_width != 2:
        raise AudioEncodeError(f"unsupported sample width {sample_width * 8} bit (need 16-bit PCM)")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bit_rate)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(5)
    mp3 = bytes(encoder.encode(pcm)) + bytes(encoder.flush())
    duration = frames / float(sample_rate) if sample_rate else 0.0
    return mp3, duration


def synth_tts_prompt(bulletin_text: str) -> str:
    """Spoken payload for the TTS model: one short style line + the bulletin."""
    return (
        "Read this aloud in Khmer with a calm, reassuring tone, slowly and clearly:"
        f"\n\n{bulletin_text}"
    )


def _extract_audio_bytes(response) -> bytes:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise TTSUnavailable("Gemini returned no candidates")
    for part in candidates[0].content.parts or []:
        inline = getattr(part, "inline_data", None)
        if inline is not None and inline.data:
            data = inline.data
            if isinstance(data, str):  # some SDK versions hand back base64
                data = base64.b64decode(data)
            return bytes(data)
    raise TTSUnavailable("Gemini response contained no audio part")


class GeminiTTS:
    def __init__(
        self,
        settings: Settings,
        *,
        voice: str = "Kore",
        state_store: StateStore | None = None,
    ) -> None:
        self._settings = settings
        self._voice = voice
        self._state_store = state_store
        self._client = None

    def _get_client(self):
        if not self._settings.has_gemini:
            raise TTSUnavailable("GEMINI_API_KEY / Vertex configuration is missing")
        if self._client is None:
            self._client = create_genai_client(self._settings)
        return self._client

    async def synthesize(self, bulletin_text: str) -> AudioArtifact:
        """Bulletin text -> MP3 artifact. Raises TTSUnavailable / AudioEncodeError."""
        client = self._get_client()
        rotator = rotator_for(
            self._settings.gemini_tts_model_chain,
            state_store=self._state_store,
        )
        config = {
            "response_modalities": ["audio"],
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": self._voice}}
            },
        }
        contents = [{"role": "user", "parts": [{"text": synth_tts_prompt(bulletin_text)}]}]

        wav_bytes: bytes | None = None
        last_error: BaseException | None = None
        try:
            for model in await rotator.ordered_async():
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=contents,
                        config=config,
                    )
                except Exception as exc:  # noqa: BLE001 - provider failure, rotate
                    if not rotator.should_rotate(exc):
                        raise
                    log.warning(
                        "TTS model %s failed (%s); trying next fallback",
                        model,
                        type(exc).__name__,
                    )
                    await rotator.mark_failed_async(model, exc)
                    last_error = exc
                    continue
                await rotator.mark_ok_async(model)
                wav_bytes = _extract_audio_bytes(response)
                break
        except TTSUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - audio is best-effort
            raise TTSUnavailable(f"TTS request failed: {exc}") from exc

        if wav_bytes is None:
            if last_error is not None:
                raise TTSUnavailable(f"TTS request failed: {last_error}") from last_error
            raise TTSUnavailable("No Gemini TTS model configured")

        mp3, duration = await asyncio.to_thread(wav_to_mp3, wav_bytes)
        return AudioArtifact(data=mp3, mime_type="audio/mpeg", duration_seconds=round(duration, 1))
