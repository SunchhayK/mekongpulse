"""On-demand assessment flow (FR-04/FR-05 API path) incl. audio glue + fallbacks."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mekong_shared.agronomy import AgriDecisionEngine
from mekong_shared.audio_store import LocalAudioStore
from mekong_shared.models import (
    CommuneRisk,
    CropStage,
    FloodReason,
    RiskTier,
    StationSnapshot,
    WeatherSnapshot,
)
from mekong_shared.pipeline import (
    AssessmentUnavailable,
    CommuneNotFound,
    Pipeline,
    audio_cache_signature,
)
from mekong_shared.stations import load_stations
from mekong_shared.tts import AudioArtifact

from support import healthy_handlers

COMMUNE = "030502"  # Kampong Cham town
STATION = "019802"


def _warning_snapshot() -> StationSnapshot:
    return StationSnapshot(
        station_id=STATION,
        name="Kompong Cham",
        river="Mekong",
        level_m=15.5,
        alarm_stage_m=15.2,
        flood_stage_m=16.2,
        rate_of_rise_m_per_hr=0.0,
        recorded_at=datetime.now(timezone.utc),
    )


async def _prepared(repo, settings, make_pipeline, gazetteer, pipeline: Pipeline | None = None):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.save_observation(_warning_snapshot())
    commune = gazetteer.get(COMMUNE)
    await repo.save_weather(
        WeatherSnapshot(
            province_code=commune.province_code or "03",
            latitude=commune.lat or 12.0,
            longitude=commune.lng or 105.46,
            precipitation_48h_mm=0.0,
            precipitation_7d_mm=0.0,
            max_rain_24h_mm=0.0,
            soil_moisture_pct=50.0,
            fetched_at=datetime.now(timezone.utc),
        )
    )
    return pipeline or make_pipeline(repo, healthy_handlers())


async def test_assess_warning_ripening_returns_harvest_assessment(
    repo, settings, make_pipeline, gazetteer
):
    assert gazetteer.get(COMMUNE).nearest_station_id == STATION
    pipeline = await _prepared(repo, settings, make_pipeline, gazetteer)
    result = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING)

    assert result.risk_tier is RiskTier.WARNING
    assert result.directive == "EMERGENCY_HARVEST_ACCELERATION"
    assert result.directives[0].urgency.value == "HIGH"
    assert "កំពង់ចាម" in result.khmer_bulletin
    assert result.english_bulletin
    assert result.audio is None  # no Gemini key in dev
    assert result.estimated is False


async def test_assess_unknown_commune_raises(repo, settings, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    with pytest.raises(CommuneNotFound):
        await pipeline.assess_commune("999999", CropStage.RIPENING)


async def test_assess_commune_without_station_raises(repo, settings, make_pipeline, gazetteer):
    pipeline = make_pipeline(repo, healthy_handlers())
    orphan = next(c for c in gazetteer.all_communes() if not c.nearest_station_id)
    with pytest.raises(AssessmentUnavailable):
        await pipeline.assess_commune(orphan.code, CropStage.RIPENING)


async def test_assess_without_weather_still_works(repo, settings, make_pipeline, gazetteer):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.save_observation(_warning_snapshot())
    pipeline = make_pipeline(repo, healthy_handlers())
    result = await pipeline.assess_commune(COMMUNE, CropStage.VEGETATIVE)
    assert result.risk_tier is RiskTier.WARNING
    assert result.directive == "SLUICE_OPEN"  # WARNING + vegetative (no rain data)


async def test_assess_with_audio_uses_store_and_stub_tts(
    repo, settings, make_pipeline, gazetteer, tmp_path
):
    pipeline = await _prepared(repo, settings, make_pipeline, gazetteer)

    class StubTTS:
        async def synthesize(self, text: str) -> AudioArtifact:
            assert "កំពង់ចាម" in text
            return AudioArtifact(data=b"\xff\xfb\x90\x00fake-mp3", mime_type="audio/mpeg", duration_seconds=42.0)

    pipeline.tts = StubTTS()  # type: ignore[assignment]
    pipeline.audio_store = LocalAudioStore(tmp_path / "audio", "http://localhost:8080")

    result = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)
    assert result.audio is not None
    assert result.audio.url.startswith("http://localhost:8080/audio/")
    assert result.audio.duration_seconds == 42.0
    # the object really landed in the store
    key = result.audio.uri.removeprefix("local:")
    assert (tmp_path / "audio" / key).exists()


def test_audio_signature_buckets_small_telemetry_changes():
    risk = CommuneRisk(
        commune_code=COMMUNE,
        commune_name_kh="កំពង់ចាម",
        commune_name_en="Kampong Cham",
        province="Kampong Cham",
        tier=RiskTier.WARNING,
        score=70,
        reason=FloodReason.RIVER_OVERFLOW,
        lead_time_hours=35,
        station_id=STATION,
        updated_at=datetime.now(timezone.utc),
    )
    weather = WeatherSnapshot(
        province_code="03",
        latitude=12.0,
        longitude=105.46,
        precipitation_48h_mm=13.0,
        precipitation_7d_mm=25.0,
        max_rain_24h_mm=10.0,
        soil_moisture_pct=55.0,
        fetched_at=datetime.now(timezone.utc),
    )
    directives = AgriDecisionEngine().evaluate(RiskTier.WARNING, CropStage.RIPENING)
    station = _warning_snapshot()
    base = audio_cache_signature(COMMUNE, CropStage.RIPENING, risk, station, weather, directives)

    # 15.50 -> 15.54 m and 13 -> 15 mm stay inside the spoken buckets.
    same = audio_cache_signature(
        COMMUNE,
        CropStage.RIPENING,
        risk,
        station.model_copy(update={"level_m": 15.54}),
        weather.model_copy(update={"precipitation_48h_mm": 15.0}),
        directives,
    )
    assert same == base

    # Crossing a 0.1 m bucket is a meaningful change and must regenerate.
    changed = audio_cache_signature(
        COMMUNE,
        CropStage.RIPENING,
        risk,
        station.model_copy(update={"level_m": 15.65}),
        weather,
        directives,
    )
    assert changed != base


async def test_assess_audio_force_bypasses_cache(
    repo, settings, make_pipeline, gazetteer, tmp_path
):
    pipeline = await _prepared(repo, settings, make_pipeline, gazetteer)
    calls = {"n": 0}

    class CountingTTS:
        async def synthesize(self, text: str) -> AudioArtifact:
            calls["n"] += 1
            return AudioArtifact(
                data=b"\xff\xfb\x90\x00fake-mp3", mime_type="audio/mpeg", duration_seconds=42.0
            )

    pipeline.tts = CountingTTS()  # type: ignore[assignment]
    pipeline.audio_store = LocalAudioStore(tmp_path / "audio", "http://localhost:8080")

    first = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)
    second = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)
    forced = await pipeline.assess_commune(
        COMMUNE, CropStage.RIPENING, with_audio=True, force_audio=True
    )

    assert first.audio is not None and second.audio is not None and forced.audio is not None
    assert calls["n"] == 2  # the force call bypassed the cached MP3
    assert second.audio.url == first.audio.url
    assert forced.audio.url != first.audio.url  # versioned URL for the rewritten file
    assert len(list((tmp_path / "audio").rglob("*.mp3"))) == 1  # same content-addressed key


async def test_assess_audio_reuses_cache_for_identical_briefing(
    repo, settings, make_pipeline, gazetteer, tmp_path
):
    pipeline = await _prepared(repo, settings, make_pipeline, gazetteer)
    calls = {"n": 0}

    class CountingTTS:
        async def synthesize(self, text: str) -> AudioArtifact:
            calls["n"] += 1
            return AudioArtifact(
                data=b"\xff\xfb\x90\x00fake-mp3", mime_type="audio/mpeg", duration_seconds=42.0
            )

    pipeline.tts = CountingTTS()  # type: ignore[assignment]
    pipeline.audio_store = LocalAudioStore(tmp_path / "audio", "http://localhost:8080")

    first = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)
    second = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)

    assert first.audio is not None and second.audio is not None
    assert calls["n"] == 1  # second click reuses the stored MP3
    assert second.audio.url == first.audio.url
    assert second.audio.duration_seconds is None  # player reads it from metadata
    assert len(list((tmp_path / "audio").rglob("*.mp3"))) == 1

    # A changed reading is a changed briefing and must generate fresh audio.
    await repo.save_observation(_warning_snapshot().model_copy(update={"level_m": 15.6}))
    third = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING, with_audio=True)
    assert third.audio is not None
    assert calls["n"] == 2
    assert third.audio.url != first.audio.url


async def test_assess_estimated_when_telemetry_is_fallback(repo, settings, make_pipeline, gazetteer):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    fallback = _warning_snapshot().model_copy(
        update={"is_stale_fallback": True, "source": "fallback", "fallback_offset_m": -0.25}
    )
    await repo.save_observation(fallback)
    pipeline = make_pipeline(repo, healthy_handlers())
    result = await pipeline.assess_commune(COMMUNE, CropStage.RIPENING)
    assert result.estimated is True
    assert result.risk_tier is RiskTier.DANGER  # WARNING escalated conservatively (INV-03)
