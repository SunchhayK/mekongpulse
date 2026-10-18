"""Audio pipeline: WAV -> MP3 transcode + TTS availability behavior (TEST-DIS-01)."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from types import SimpleNamespace

from mekong_shared.config import Settings
from mekong_shared.tts import (
    AudioEncodeError,
    GeminiTTS,
    TTSUnavailable,
    synth_tts_prompt,
    wav_to_mp3,
)


def sine_wav(seconds: float = 1.0, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        if width == 2:
            payload = b"".join(
                struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
                for i in range(frames * channels)
            )
        else:
            payload = bytes(int(128 + 100 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(frames * channels))
        wav.writeframes(payload)
    return buffer.getvalue()


def test_wav_to_mp3_produces_valid_mpeg_frame():
    """TEST-DIS-01 shape: encoded artifact is a real MP3 of the right duration."""
    mp3, duration = wav_to_mp3(sine_wav(1.0))
    assert len(mp3) > 1000
    assert mp3[0] == 0xFF and (mp3[1] & 0xE0) == 0xE0  # MPEG frame sync
    assert duration == pytest.approx(1.0, abs=0.01)


def test_wav_to_mp3_rejects_garbage():
    with pytest.raises(AudioEncodeError):
        wav_to_mp3(b"not a wav at all")


def test_wav_to_mp3_rejects_non_pcm16():
    with pytest.raises(AudioEncodeError):
        wav_to_mp3(sine_wav(0.2, width=1))


def test_synth_prompt_is_one_style_line_plus_the_bulletin():
    bulletin = "សារព្រមានទឹកជំនន់"
    prompt = synth_tts_prompt(bulletin)
    directive, separator, spoken = prompt.partition("\n\n")
    assert separator == "\n\n"
    assert spoken == bulletin  # the spoken payload is the bulletin, verbatim
    assert "\n" not in directive
    assert directive.endswith(":")
    assert len(directive.split()) <= 16  # short style line, not a role-play preamble


class _CaptureModels:
    def __init__(self, wav: bytes) -> None:
        self.wav = wav
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        part = SimpleNamespace(inline_data=SimpleNamespace(data=self.wav))
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )


async def test_tts_sends_style_line_and_bulletin(tmp_path):
    """Regression: one short style line + the bulletin; no role-play preamble,
    and no system_instruction (the TTS model rejects it with 400)."""
    settings = Settings(
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
        gemini_api_key="test-key",
        use_vertex_ai=False,
    )
    tts = GeminiTTS(settings)
    models = _CaptureModels(sine_wav(0.4))
    tts._client = SimpleNamespace(models=models)  # type: ignore[assignment]

    bulletin = "សារព្រមានទឹកជំនន់សម្រាប់ឃុំ"
    artifact = await tts.synthesize(bulletin)

    call = models.calls[0]
    spoken = call["contents"][0]["parts"][0]["text"]
    assert spoken == synth_tts_prompt(bulletin)
    assert spoken.endswith(bulletin) and "announcer" not in spoken.lower()
    assert "system_instruction" not in call["config"]
    assert artifact.mime_type == "audio/mpeg"
    assert artifact.duration_seconds == pytest.approx(0.4, abs=0.05)


class _FailingModels:
    def generate_content(self, *, model, contents, config):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")


async def test_tts_api_failure_degrades_to_unavailable(tmp_path):
    """A quota/API error must surface as TTSUnavailable (text-only fallback),
    never as an unhandled 500 on the assessment endpoint."""
    settings = Settings(
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
        gemini_api_key="test-key",
        use_vertex_ai=False,
    )
    tts = GeminiTTS(settings)
    tts._client = SimpleNamespace(models=_FailingModels())  # type: ignore[assignment]
    with pytest.raises(TTSUnavailable):
        await tts.synthesize("សារព្រមានទឹកជំនន់")


async def test_tts_without_key_raises_unavailable(tmp_path):
    settings = Settings(
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
        gemini_api_key=None,
        use_vertex_ai=False,
    )
    tts = GeminiTTS(settings)
    with pytest.raises(TTSUnavailable):
        await tts.synthesize("សូមសុវត្ថិភាព")
