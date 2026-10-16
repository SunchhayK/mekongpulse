"""Backend fixtures: in-memory repo, mock-transport pipeline, ASGI client."""

from __future__ import annotations

import httpx
import pytest

from mekong_shared.config import PROJECTS_ROOT, Settings
from mekong_shared.memory_repo import MemoryRepository
from mekong_shared.mrc import MRCTelemetryClient
from mekong_shared.pipeline import Pipeline
from mekong_shared.weather import OpenMeteoClient
from mekong_backend.app import create_app

from support import healthy_handlers, mrc_transport, running_client, weather_payload, weather_transport

DATA_DIR = PROJECTS_ROOT / "data"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        environment="development",
        repository_backend="memory",
        data_dir=DATA_DIR,
        audio_dir=tmp_path / "audio",
        public_base_url="http://testserver",
    )


@pytest.fixture
async def repo():
    repository = MemoryRepository()
    await repository.init()
    yield repository
    await repository.close()


@pytest.fixture
def make_pipeline(settings):
    def _make(repository, handlers: dict | None = None, weather: dict | None = None) -> Pipeline:
        handlers = handlers if handlers is not None else healthy_handlers()
        return Pipeline(
            settings=settings,
            repo=repository,
            mrc=MRCTelemetryClient(
                "https://mrc.test/api/v1",
                http_client=httpx.AsyncClient(transport=mrc_transport(handlers)),
            ),
            weather=OpenMeteoClient(
                "https://weather.test/v1",
                http_client=httpx.AsyncClient(
                    transport=weather_transport(weather if weather is not None else weather_payload(0.0))
                ),
            ),
        )

    return _make


@pytest.fixture
def make_app(settings):
    def _make(*, repository, pipeline, settings_override=None, telegram_app=None):
        return create_app(
            settings=settings_override or settings,
            repo=repository,
            pipeline=pipeline,
            telegram_app=telegram_app,
        )

    return _make


@pytest.fixture
async def client(repo, make_pipeline, make_app):
    """Default client: calm stations, dry weather, memory repo, no bot."""
    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    app = make_app(repository=repo, pipeline=pipeline)
    async with running_client(app) as c:
        yield c
