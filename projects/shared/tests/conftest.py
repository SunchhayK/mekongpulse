"""Shared fixtures for the mekong-shared test-suite.

Uses the real bundled gazetteer / station roster (they are build artifacts of
verified data) and mock HTTP transports for MRC + Open-Meteo.
"""

from __future__ import annotations

import httpx
import pytest

from mekong_shared.config import PROJECTS_ROOT, Settings
from mekong_shared.memory_repo import MemoryRepository
from mekong_shared.mrc import MRCTelemetryClient
from mekong_shared.pipeline import Pipeline
from mekong_shared.spatial import Gazetteer
from mekong_shared.stations import load_stations
from mekong_shared.weather import OpenMeteoClient

from support import healthy_handlers, mrc_transport, weather_payload, weather_transport

DATA_DIR = PROJECTS_ROOT / "data"


@pytest.fixture(autouse=True)
def reset_model_rotators():
    """Cooldowns are process-wide; keep one test's quota failure out of the next."""
    from mekong_shared import model_rotation

    yield
    with model_rotation._ROTATORS_LOCK:
        model_rotation._ROTATORS.clear()


@pytest.fixture(scope="session")
def data_dir():
    return DATA_DIR


@pytest.fixture(scope="session")
def gazetteer(data_dir):
    return Gazetteer(data_dir)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        # Hermetic: never load a developer .env (real Gemini/Telegram keys
        # would turn unit tests into live network calls when pytest runs
        # from the projects/ root, where .env -> .env.staging).
        _env_file=None,
        environment="development",
        repository_backend="memory",
        data_dir=DATA_DIR,
        audio_dir=tmp_path / "audio",
        public_base_url="http://localhost:8080",
    )


@pytest.fixture
async def repo():
    repository = MemoryRepository()
    await repository.init()
    yield repository
    await repository.close()


@pytest.fixture
def stations():
    return load_stations(str(DATA_DIR))


@pytest.fixture
def make_pipeline(settings):
    """Factory: Pipeline wired to mock MRC + Open-Meteo transports."""

    def _make(
        repository: MemoryRepository,
        handlers: dict | None = None,
        weather: dict | None = None,
    ) -> Pipeline:
        handlers = handlers if handlers is not None else healthy_handlers()
        mrc_client = MRCTelemetryClient(
            "https://mrc.test/api/v1",
            http_client=httpx.AsyncClient(transport=mrc_transport(handlers)),
        )
        weather_client = OpenMeteoClient(
            "https://weather.test/v1",
            http_client=httpx.AsyncClient(transport=weather_transport(weather or weather_payload())),
        )
        return Pipeline(settings=settings, repo=repository, mrc=mrc_client, weather=weather_client)

    return _make
