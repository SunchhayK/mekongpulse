"""Sync cost checks: unchanged risk rows and hourly weather are not rewritten."""

from __future__ import annotations

from support import healthy_handlers


async def test_sync_skips_unchanged_risk_rows(repo, settings, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    calls: list[int] = []
    original = repo.save_commune_risks

    async def spy(risks):
        calls.append(len(risks))
        await original(risks)

    repo.save_commune_risks = spy

    await pipeline.sync()
    await pipeline.sync()

    assert len(calls) == 1  # second pass found nothing to write
    assert calls[0] > 0


async def test_sync_reuses_weather_within_refresh_window(repo, settings, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    saves = 0
    original = repo.save_weather

    async def spy(snapshot):
        nonlocal saves
        saves += 1
        await original(snapshot)

    repo.save_weather = spy

    await pipeline.sync()
    first_pass = saves
    await pipeline.sync()

    assert first_pass > 0
    assert saves == first_pass  # cached for settings.weather_refresh_minutes
