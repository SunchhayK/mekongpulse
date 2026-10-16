"""Audio pipeline: WAV -> MP3 transcode + TTS availability behavior (TEST-DIS-01)."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

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


def test_synth_prompt_carries_bulletin_and_tone_rules():
    prompt = synth_tts_prompt("សារព្រមានទឹកជំនន់")
    assert "សារព្រមានទឹកជំនន់" in prompt
    assert "Khmer" in prompt
    assert "Do not add, omit, or change" in prompt


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
