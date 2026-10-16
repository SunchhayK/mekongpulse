"""Khmer spoken voice notes via Gemini TTS (FR-05 / ADR-0005, amended).

The technical report's original model line (Gemini 2.0 Flash) cannot emit
audio and 2.5-era Gemini TTS lacked Khmer support; the verified Khmer-capable
path is `gemini-3.8-flash-tts` (unary request returning 24 kHz WAV PCM), which
we transcode to MP3 with the `lameenc` bindings (no system ffmpeg dependency in
the container).
"""

from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass

from .config import Settings


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
    return (
        "You are a calm, respectful announcer for the MekongPulse flood early-warning "
        "service in Cambodia. Read the following bulletin aloud in clear, natural spoken "
        "Khmer. Serious but reassuring tone; slow enough to be understood by elderly "
        "listeners; short pauses between sections. Do not add, omit, or change any "
        "information.\n\n"
        f"{bulletin_text}"
    )


class GeminiTTS:
    def __init__(self, settings: Settings, *, voice: str = "Kore") -> None:
        self._settings = settings
        self._voice = voice
        self._client = None

    def _get_client(self):
        if not self._settings.has_gemini:
            raise TTSUnavailable("GEMINI_API_KEY / Vertex configuration is missing")
        if self._client is None:
            from google import genai

            if self._settings.use_vertex_ai:
                self._client = genai.Client(
                    vertexai=True,
                    project=self._settings.vertex_project,
                    location=self._settings.vertex_location,
                )
            else:
                self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    async def synthesize(self, bulletin_text: str) -> AudioArtifact:
        """Bulletin text -> MP3 artifact. Raises TTSUnavailable / AudioEncodeError."""
        client = self._get_client()

        def _generate() -> bytes:
            config = {
                "response_modalities": ["audio"],
                "speech_config": {
                    "voice_config": {"prebuilt_voice_config": {"voice_name": self._voice}}
                },
            }
            response = client.models.generate_content(
                model=self._settings.gemini_tts_model,
                contents=[{"role": "user", "parts": [{"text": synth_tts_prompt(bulletin_text)}]}],
                config=config,
            )
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                raise TTSUnavailable("Gemini returned no candidates")
            for part in candidates[0].content.parts or []:
                inline = getattr(part, "inline_data", None)
                if inline is not None and inline.data:
                    data = inline.data
                    if isinstance(data, str):  # some SDK versions hand back base64
                        import base64

                        data = base64.b64decode(data)
                    return bytes(data)
            raise TTSUnavailable("Gemini response contained no audio part")

        wav_bytes = await asyncio.to_thread(_generate)
        mp3, duration = await asyncio.to_thread(wav_to_mp3, wav_bytes)
        return AudioArtifact(data=mp3, mime_type="audio/mpeg", duration_seconds=round(duration, 1))
