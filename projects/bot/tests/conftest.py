"""Bot fixtures: memory repo, offline pipeline, BotService."""

from __future__ import annotations

import pytest

from mekong_shared.audio_store import LocalAudioStore
from mekong_shared.config import PROJECTS_ROOT, Settings
from mekong_shared.memory_repo import MemoryRepository
from mekong_shared.pipeline import Pipeline

from mekong_bot.service import BotService

DATA_DIR = PROJECTS_ROOT / "data"


@pytest.fixture
def settings(tmp_path):
    return Settings(
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
def pipeline(settings, repo):
    """Real pipeline object with local audio store; no network is ever hit."""
    return Pipeline(
        settings=settings,
        repo=repo,
        audio_store=LocalAudioStore(settings.audio_dir, settings.public_base_url),
    )


@pytest.fixture
def service(settings, pipeline, repo):
    return BotService(settings, pipeline, repo)
