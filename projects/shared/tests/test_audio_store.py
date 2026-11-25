"""Tests for audio object storage including CDN URL and immutable Cache-Control (IMP-09)."""

from __future__ import annotations

from pathlib import Path

from mekong_shared.audio_store import GCSAudioStore, LocalAudioStore
from mekong_shared.config import Settings
from mekong_shared.repository import create_audio_store


class _FakeBlob:
    def __init__(self, name: str, store: dict[str, bytes]) -> None:
        self.name = name
        self._store = store
        self.cache_control: str | None = None
        self.content_type: str | None = None

    def upload_from_string(self, data: bytes, content_type: str = "audio/mpeg") -> None:
        self.content_type = content_type
        self._store[self.name] = data

    def exists(self) -> bool:
        return self.name in self._store

    def download_as_bytes(self) -> bytes:
        return self._store[self.name]


class _FakeBucket:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.blobs: dict[str, _FakeBlob] = {}

    def blob(self, key: str) -> _FakeBlob:
        if key not in self.blobs:
            self.blobs[key] = _FakeBlob(key, self.store)
        return self.blobs[key]


class _FakeStorageClient:
    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return self.buckets.setdefault(name, _FakeBucket())


async def test_local_audio_store_roundtrip(tmp_path: Path):
    store = LocalAudioStore(tmp_path, "http://localhost:8080/")
    ref = await store.put("abc.mp3", b"ID3data")
    assert ref.uri == "local:abc.mp3"
    assert ref.url.startswith("http://localhost:8080/audio/abc.mp3?v=")
    assert await store.head("abc.mp3") is not None
    assert await store.get(ref.uri) == b"ID3data"


async def test_gcs_audio_store_sets_immutable_cache_control_and_cdn_url():
    client = _FakeStorageClient()
    store = GCSAudioStore(
        bucket="mekong-audio",
        public_base="https://storage.googleapis.com/mekong-audio",
        cdn_base_url="https://cdn.mekongpulse.org/audio/",
        cache_control="public, max-age=31536000, immutable",
        client=client,
    )
    ref = await store.put("bulletins/hash123.mp3", b"mp3bytes")
    assert ref.uri == "gs://mekong-audio/bulletins/hash123.mp3"
    assert ref.url == "https://cdn.mekongpulse.org/audio/bulletins/hash123.mp3"

    blob = client.buckets["mekong-audio"].blobs["bulletins/hash123.mp3"]
    assert blob.cache_control == "public, max-age=31536000, immutable"
    assert await store.get(ref.uri) == b"mp3bytes"


async def test_gcs_audio_store_without_cdn_uses_public_base():
    client = _FakeStorageClient()
    store = GCSAudioStore(
        bucket="mekong-audio",
        public_base=None,
        cdn_base_url=None,
        client=client,
    )
    ref = await store.put("hash.mp3", b"mp3")
    assert ref.url.startswith("https://storage.googleapis.com/mekong-audio/hash.mp3?v=")


def test_create_audio_store_uses_local_in_dev(tmp_path: Path):
    settings = Settings(environment="development", audio_dir=tmp_path)
    store = create_audio_store(settings)
    assert isinstance(store, LocalAudioStore)
