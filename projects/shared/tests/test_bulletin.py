"""Bilingual bulletin templates + Gemini polish fallback (FR-05)."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.bulletin import BulletinBuilder, GeminiTextClient
from mekong_shared.agronomy import AgriDecisionEngine
from mekong_shared.models import (
    Commune,
    CommuneRisk,
    CropStage,
    FloodReason,
    RiskTier,
    StationSnapshot,
    WeatherSnapshot,
)


def _commune() -> Commune:
    return Commune(
        code="030502",
        name_kh="កំពង់ចាម",
        name_en="Kampong Cham",
        district_en="Kampong Cham",
        province_en="Kampong Cham",
        province_code="03",
        nearest_station_id="019802",
        has_boundary=True,
    )


def _risk(tier: RiskTier) -> CommuneRisk:
    return CommuneRisk(
        commune_code="030502",
        commune_name_kh="កំពង់ចាម",
        commune_name_en="Kampong Cham",
        province="Kampong Cham",
        tier=tier,
        score=70,
        reason=FloodReason.RIVER_OVERFLOW,
        lead_time_hours=35,
        drivers=["level 15.50m >= alarm stage 15.20m"],
        station_id="019802",
        station_level_m=15.5,
        updated_at=datetime.now(timezone.utc),
    )


def _station() -> StationSnapshot:
    return StationSnapshot(
        station_id="019802",
        name="Kompong Cham",
        river="Mekong",
        level_m=15.5,
        alarm_stage_m=15.2,
        flood_stage_m=16.2,
        rate_of_rise_m_per_hr=0.02,
        recorded_at=datetime.now(timezone.utc),
    )


def _weather() -> WeatherSnapshot:
    return WeatherSnapshot(
        province_code="03",
        latitude=12.0,
        longitude=105.46,
        precipitation_48h_mm=15.0,
        precipitation_7d_mm=25.0,
        max_rain_24h_mm=10.0,
        soil_moisture_pct=55.0,
        fetched_at=datetime.now(timezone.utc),
    )


def test_templates_carry_names_numbers_and_directives():
    engine = AgriDecisionEngine()
    directives = engine.evaluate(RiskTier.WARNING, CropStage.RIPENING, lead_time_hours=35)
    builder = BulletinBuilder()
    kh, en = builder.build_templates(_commune(), _risk(RiskTier.WARNING), directives, _station(), _weather())

    assert "កំពង់ចាម" in kh
    assert "ព្រមាន" in kh  # WARNING label
    assert "15.50" in kh and "15.20" in kh and "16.20" in kh
    assert "35" in kh  # lead time
    assert "ប្រមូលផល" in kh  # harvest directive
    assert "Kampong Cham" in en
    assert "WARNING" in en
    assert "Harvest" in en


def test_template_without_station_or_weather_still_renders():
    builder = BulletinBuilder()
    engine = AgriDecisionEngine()
    directives = engine.evaluate(RiskTier.NORMAL, CropStage.TILLERING)
    kh, en = builder.build_templates(_commune(), _risk(RiskTier.NORMAL), directives, None, None)
    assert "ធម្មតា" in kh
    assert "NORMAL" in en


class FakeTextClient:
    def __init__(self, reply: str | None = None, boom: bool = False) -> None:
        self.reply = reply
        self.boom = boom

    async def polish_khmer(self, text: str) -> str:
        if self.boom:
            raise RuntimeError("gemini down")
        return self.reply or text


async def test_polish_is_used_when_available():
    engine = AgriDecisionEngine()
    directives = engine.evaluate(RiskTier.WARNING, CropStage.RIPENING)
    builder = BulletinBuilder(FakeTextClient(reply="សារខ្មែរថ្មី"))  # type: ignore[arg-type]
    kh, _ = await builder.build(_commune(), _risk(RiskTier.WARNING), directives, _station(), _weather())
    assert kh == "សារខ្មែរថ្មី"


async def test_polish_failure_falls_back_to_template():
    engine = AgriDecisionEngine()
    directives = engine.evaluate(RiskTier.WARNING, CropStage.RIPENING)
    builder = BulletinBuilder(FakeTextClient(boom=True))  # type: ignore[arg-type]
    kh, _ = await builder.build(_commune(), _risk(RiskTier.WARNING), directives, _station(), _weather())
    assert "សារព្រមានទឹកជំនន់ពី MekongPulse" in kh


def test_gemini_text_client_has_polish_contract():
    assert hasattr(GeminiTextClient, "polish_khmer")
    assert hasattr(GeminiTextClient, "generate")
