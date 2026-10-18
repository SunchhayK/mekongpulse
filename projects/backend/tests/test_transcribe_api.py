"""Advisor voice input: base64 -> transcript, size guard, graceful 503."""

from __future__ import annotations

import base64

from mekong_shared.stt import TranscriptionUnavailable

from mekong_backend.routers import officer


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def payload(data: bytes, **overrides) -> dict:
    body = {"audio_base64": b64(data), "mime_type": "audio/webm"}
    body.update(overrides)
    return body


async def test_transcribe_returns_text(client, monkeypatch):
    captured: dict = {}

    async def fake_transcribe(settings, audio, mime_type, locale_hint=None):
        captured.update(audio=audio, mime_type=mime_type, locale_hint=locale_hint)
        return "សូមស្វាគមន៍"

    monkeypatch.setattr(officer, "transcribe_audio", fake_transcribe)

    audio = b"\x1a\x45\xdf\xa3" + b"fake-webm" * 200
    response = await client.post(
        "/api/v1/advisor/transcribe", json=payload(audio, locale_hint="km")
    )

    assert response.status_code == 200
    assert response.json() == {"text": "សូមស្វាគមន៍"}
    assert captured == {"audio": audio, "mime_type": "audio/webm", "locale_hint": "km"}


async def test_transcribe_rejects_oversized_audio(client, monkeypatch):
    called = False

    async def fake_transcribe(*args, **kwargs):
        nonlocal called
        called = True
        return "should not run"

    monkeypatch.setattr(officer, "transcribe_audio", fake_transcribe)

    response = await client.post("/api/v1/advisor/transcribe", json=payload(b"\x00" * 4_000_001))

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("audio-too-large")
    assert called is False


async def test_transcribe_rejects_non_base64_payload(client):
    response = await client.post(
        "/api/v1/advisor/transcribe",
        json={"audio_base64": "not base64 $$$", "mime_type": "audio/webm"},
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-audio")


async def test_transcribe_unavailable_without_gemini(client):
    """No key configured: the real path degrades to a 503 problem, never a 500."""
    response = await client.post(
        "/api/v1/advisor/transcribe", json=payload(b"fake-audio" * 200)
    )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["type"].endswith("transcription-unavailable")


async def test_transcribe_provider_failure_returns_503(client, monkeypatch):
    async def failing_transcribe(*args, **kwargs):
        raise TranscriptionUnavailable("quota exhausted")

    monkeypatch.setattr(officer, "transcribe_audio", failing_transcribe)

    response = await client.post(
        "/api/v1/advisor/transcribe", json=payload(b"fake-audio" * 200)
    )
    assert response.status_code == 503
    body = response.json()
    assert body["type"].endswith("transcription-unavailable")
    assert body["detail"] == "quota exhausted"


async def test_transcribe_rejects_tiny_clip(client, monkeypatch):
    called = False

    async def fake_transcribe(*args, **kwargs):
        nonlocal called
        called = True
        return "should not run"

    monkeypatch.setattr(officer, "transcribe_audio", fake_transcribe)

    response = await client.post(
        "/api/v1/advisor/transcribe", json=payload(b"\x00" * 100)
    )

    assert response.status_code == 422
    assert response.json()["type"].endswith("audio-too-short")
    assert called is False


async def test_transcribe_normalizes_codec_suffix(client, monkeypatch):
    captured: dict = {}

    async def fake_transcribe(settings, audio, mime_type, locale_hint=None):
        captured.update(mime_type=mime_type)
        return "ok"

    monkeypatch.setattr(officer, "transcribe_audio", fake_transcribe)

    audio = b"\x1a\x45\xdf\xa3" + b"x" * 2_000
    response = await client.post(
        "/api/v1/advisor/transcribe",
        json=payload(audio, mime_type="audio/webm;codecs=opus"),
    )

    assert response.status_code == 200
    assert captured["mime_type"] == "audio/webm"
