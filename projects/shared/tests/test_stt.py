"""Server-side STT: provider success, degradation, and the pinned instruction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import google.genai as genai

from mekong_shared.config import Settings
from mekong_shared.stt import (
    TRANSCRIBE_INSTRUCTION,
    TranscriptionUnavailable,
    transcribe_audio,
    transcribe_instruction,
)


def make_settings(tmp_path, *, key: str | None = "test-key") -> Settings:
    return Settings(
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
        gemini_api_key=key,
        use_vertex_ai=False,
    )


def patch_genai_client(monkeypatch, models) -> None:
    monkeypatch.setattr(genai, "Client", lambda **kwargs: SimpleNamespace(models=models))


class _CaptureModels:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _response(*parts) -> SimpleNamespace:
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)))]
    )


def test_default_instruction_is_pinned():
    """Regression: the exact instruction the model was smoke-tested against."""
    assert TRANSCRIBE_INSTRUCTION == (
        "Transcribe this speech to text. It is Khmer or English. Return only the transcript."
    )
    assert transcribe_instruction(None) == TRANSCRIBE_INSTRUCTION
    assert transcribe_instruction("km") == (
        "Transcribe this speech to text. It is Khmer. Return only the transcript."
    )
    assert transcribe_instruction("en") == (
        "Transcribe this speech to text. It is English. Return only the transcript."
    )


async def test_transcribe_returns_stripped_transcript(tmp_path, monkeypatch):
    models = _CaptureModels(_response(SimpleNamespace(text="  សូមស្វាគមន៍  ")))
    patch_genai_client(monkeypatch, models)
    settings = make_settings(tmp_path)

    text = await transcribe_audio(settings, b"webm-bytes", "audio/webm", "km")

    assert text == "សូមស្វាគមន៍"
    call = models.calls[0]
    assert call["model"] == settings.gemini_text_model
    parts = call["contents"][0]["parts"]
    assert parts[0]["inline_data"] == {"mime_type": "audio/webm", "data": b"webm-bytes"}
    assert parts[1]["text"] == transcribe_instruction("km")


async def test_transcribe_defaults_to_bilingual_instruction(tmp_path, monkeypatch):
    models = _CaptureModels(_response(SimpleNamespace(text="hello")))
    patch_genai_client(monkeypatch, models)
    await transcribe_audio(make_settings(tmp_path), b"audio", "audio/ogg")
    assert models.calls[0]["contents"][0]["parts"][1]["text"] == TRANSCRIBE_INSTRUCTION


async def test_provider_error_degrades_to_unavailable(tmp_path, monkeypatch):
    """Quota/transport failures must surface as TranscriptionUnavailable, never 500."""
    models = _CaptureModels(RuntimeError("429 RESOURCE_EXHAUSTED"))
    patch_genai_client(monkeypatch, models)
    with pytest.raises(TranscriptionUnavailable):
        await transcribe_audio(make_settings(tmp_path), b"audio", "audio/webm")


async def test_empty_transcript_degrades_to_unavailable(tmp_path, monkeypatch):
    models = _CaptureModels(_response(SimpleNamespace(text="   ")))
    patch_genai_client(monkeypatch, models)
    with pytest.raises(TranscriptionUnavailable):
        await transcribe_audio(make_settings(tmp_path), b"audio", "audio/webm")


async def test_no_candidates_degrades_to_unavailable(tmp_path, monkeypatch):
    models = _CaptureModels(SimpleNamespace(candidates=[]))
    patch_genai_client(monkeypatch, models)
    with pytest.raises(TranscriptionUnavailable):
        await transcribe_audio(make_settings(tmp_path), b"audio", "audio/webm")


async def test_without_key_raises_unavailable(tmp_path, monkeypatch):
    def boom(**kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("genai client must not be constructed without a key")

    monkeypatch.setattr(genai, "Client", boom)
    with pytest.raises(TranscriptionUnavailable):
        await transcribe_audio(make_settings(tmp_path, key=None), b"audio", "audio/webm")
