"""Audio object storage: local directory (dev/staging) and GCS (production).

Synthesized MP3 bulletins are cached here; the returned `AudioRef` carries both
the storage uri and the playable URL used by the bot and dashboard.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .models import AudioRef


class LocalAudioStore:
    def __init__(self, audio_dir: Path, public_base_url: str) -> None:
        self._dir = Path(audio_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._base = public_base_url.rstrip("/")

    async def put(self, key: str, data: bytes, mime_type: str = "audio/mpeg") -> AudioRef:
        path = self._dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        stat = await asyncio.to_thread(path.stat)
        return AudioRef(
            uri=f"local:{key}",
            url=f"{self._base}/audio/{key}?v={stat.st_mtime_ns}",
            mime_type=mime_type,
        )

    async def head(self, key: str) -> AudioRef | None:
        path = self._dir / key
        if not await asyncio.to_thread(path.is_file):
            return None
        stat = await asyncio.to_thread(path.stat)
        return AudioRef(
            uri=f"local:{key}",
            url=f"{self._base}/audio/{key}?v={stat.st_mtime_ns}",
        )

    async def get(self, key_or_uri: str) -> bytes:
        key = key_or_uri.removeprefix("local:")
        return await asyncio.to_thread((self._dir / key).read_bytes)


class GCSAudioStore:
    def __init__(self, bucket: str | None, public_base: str | None) -> None:
        if not bucket:
            raise ValueError("GCS_BUCKET is required in production")
        from google.cloud import storage

        self._bucket_name = bucket
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        self._base = (public_base or f"https://storage.googleapis.com/{bucket}").rstrip("/")

    async def put(self, key: str, data: bytes, mime_type: str = "audio/mpeg") -> AudioRef:
        def _upload() -> None:
            blob = self._bucket.blob(key)
            blob.cache_control = "public, max-age=86400"
            blob.upload_from_string(data, content_type=mime_type)

        await asyncio.to_thread(_upload)
        return AudioRef(
            uri=f"gs://{self._bucket_name}/{key}",
            url=f"{self._base}/{key}?v={time.time_ns()}",
            mime_type=mime_type,
        )

    async def head(self, key: str) -> AudioRef | None:
        if not await asyncio.to_thread(self._bucket.blob(key).exists):
            return None
        return AudioRef(uri=f"gs://{self._bucket_name}/{key}", url=f"{self._base}/{key}")

    async def get(self, key_or_uri: str) -> bytes:
        key = key_or_uri.removeprefix(f"gs://{self._bucket_name}/")
        return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)
