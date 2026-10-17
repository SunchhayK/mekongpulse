"""Risk classifier rules: AC-01, AC-02, INV-03 and elevation reasoning."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mekong_shared.models import Commune, FloodReason, RiskTier, StationSnapshot, WeatherSnapshot
from mekong_shared.risk import SpatialRiskClassifier


def make_commune(code: str = "080404", elevation: float | None = None) -> Commune:
    return Commune(
        code=code,
        name_kh="កោះធំ ក",
        name_en="Kaoh Thum Ka",
        district_code="0804",
        district_kh="កោះធំ",
        district_en="Kaoh Thum",
        province_code="08",
        province_kh="កណ្ដាល",
        province_en="Kandal",
        lat=11.2,
        lng=105.0,
        ground_elevation_m=elevation,
        nearest_station_id="033401",
        distance_to_station_km=5.0,
        has_boundary=True,
    )


def make_station(
    level: float,
    *,
    alarm: float = 10.5,
    flood: float = 12.0,
    rate: float = 0.0,
    station_id: str = "033401",
    stale: bool = False,
    source: str = "live",
) -> StationSnapshot:
    return StationSnapshot(
        station_id=station_id,
        name="Chaktomuk",
        river="Bassac",
        level_m=level,
        alarm_stage_m=alarm,
        flood_stage_m=flood,
        rate_of_rise_m_per_hr=rate,
        recorded_at=datetime.now(timezone.utc),
        is_stale_fallback=stale,
        source=source,
    )


def make_weather(rain48: float = 0.0, rain24: float = 0.0) -> WeatherSnapshot:
    return WeatherSnapshot(
        province_code="08",
        latitude=11.5,
        longitude=105.0,
        precipitation_48h_mm=rain48,
        precipitation_7d_mm=rain48,
        max_rain_24h_mm=rain24,
        soil_moisture_pct=40.0,
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def classifier() -> SpatialRiskClassifier:
    return SpatialRiskClassifier()


def test_ac02_far_below_alarm_is_normal(classifier):
    """>2.0 m below alarm stage and no weather threat => NORMAL (AC-02)."""
    risk = classifier.classify(make_commune(), make_station(8.0), make_weather())
    assert risk.tier is RiskTier.NORMAL
    assert risk.reason is FloodReason.NONE


def test_approaching_alarm_is_advisory(classifier):
    risk = classifier.classify(make_commune(), make_station(9.0), make_weather())
    assert risk.tier is RiskTier.ADVISORY


def test_ac01_rapid_pulse_reaches_warning(classifier):
    """rate > 0.08 m/hr must reach WARNING or DANGER (AC-01)."""
    risk = classifier.classify(make_commune(), make_station(9.0, rate=0.09), make_weather())
    assert risk.tier is RiskTier.WARNING
    assert risk.reason is FloodReason.RIVER_PULSE


def test_above_alarm_is_warning(classifier):
    risk = classifier.classify(make_commune(), make_station(10.6), make_weather())
    assert risk.tier is RiskTier.WARNING


def test_above_alarm_with_pulse_is_danger(classifier):
    risk = classifier.classify(make_commune(), make_station(10.6, rate=0.10), make_weather())
    assert risk.tier is RiskTier.DANGER


def test_above_flood_is_danger(classifier):
    risk = classifier.classify(make_commune(), make_station(12.1), make_weather())
    assert risk.tier is RiskTier.DANGER
    assert risk.reason is FloodReason.RIVER_OVERFLOW


def test_heavy_rain_calm_river_is_advisory(classifier):
    """River calm + moderate rain => ADVISORY rain rules."""
    risk = classifier.classify(make_commune(), make_station(8.0), make_weather(rain48=45, rain24=30))
    assert risk.tier is RiskTier.ADVISORY
    assert any("rain" in d for d in risk.drivers)


def test_flash_flood_reason_for_extreme_24h_rain(classifier):
    risk = classifier.classify(make_commune(), make_station(8.0), make_weather(rain48=95, rain24=85))
    assert risk.tier is RiskTier.ADVISORY
    assert risk.reason is FloodReason.LOCAL_FLASH_FLOOD


def test_heavy_rain_near_alarm_is_warning(classifier):
    risk = classifier.classify(
        make_commune(), make_station(9.8), make_weather(rain48=65, rain24=25)
    )
    assert risk.tier is RiskTier.WARNING


def test_heavy_rain_above_alarm_is_danger(classifier):
    risk = classifier.classify(
        make_commune(), make_station(10.6), make_weather(rain48=65, rain24=25)
    )
    assert risk.tier is RiskTier.DANGER


def test_inv03_estimated_telemetry_escalates_conservatively(classifier):
    """INV-03: fallback/cached telemetry never downgrades; it escalates."""
    risk = classifier.classify(
        make_commune(), make_station(9.0, stale=True, source="fallback"), make_weather()
    )
    assert risk.tier is RiskTier.WARNING  # ADVISORY escalated
    assert risk.estimated is True
    assert any("estimated" in d for d in risk.drivers)


def test_elevation_water_surface_near_ground_is_warning(classifier):
    """Gauge datum + DEM: water surface within 0.3m of ground => WARNING."""
    # 033401 zero gauge = -1.02 MSL; level 8.0 => water surface 6.98; ground 7.1
    risk = classifier.classify(make_commune(elevation=7.1), make_station(8.0), make_weather())
    assert risk.tier is RiskTier.WARNING
    assert any("ground" in d for d in risk.drivers)


def test_elevation_water_above_ground_is_danger(classifier):
    risk = classifier.classify(make_commune(elevation=6.7), make_station(8.0), make_weather())
    assert risk.tier is RiskTier.DANGER


def test_elevation_rule_keeps_working_with_unknown_distance(classifier):
    """Missing distance data stays conservative (JRN-02): rule still applies."""
    commune = make_commune(elevation=6.7).model_copy(update={"distance_to_station_km": None})
    risk = classifier.classify(commune, make_station(8.0), make_weather())
    assert risk.tier is RiskTier.DANGER


def test_lead_time_from_stage_rise(classifier):
    risk = classifier.classify(make_commune(), make_station(10.0, rate=0.02), make_weather())
    assert risk.lead_time_hours == 100  # (12.0 - 10.0) / 0.02


def test_lead_time_none_when_flat(classifier):
    risk = classifier.classify(make_commune(), make_station(10.0), make_weather())
    assert risk.lead_time_hours is None


def test_lead_time_zero_when_above_flood(classifier):
    risk = classifier.classify(make_commune(), make_station(12.2), make_weather())
    assert risk.lead_time_hours == 0


def test_lead_time_uses_ground_head_when_lower(classifier):
    # ground 9.5, surface 8.98 => head 0.52 => 26h, earlier than stage-based 100h
    risk = classifier.classify(make_commune(elevation=9.5), make_station(10.0, rate=0.02), make_weather())
    assert risk.lead_time_hours == 26


def test_elevation_rule_suppressed_far_from_station(classifier):
    """INV-01: a gauge >50 km away must not fabricate local inundation risk."""
    commune = make_commune(elevation=6.7).model_copy(update={"distance_to_station_km": 180.0})
    risk = classifier.classify(commune, make_station(8.0), make_weather())
    assert risk.tier is RiskTier.NORMAL
    assert not any("water surface" in d for d in risk.drivers)


def test_lead_time_ignores_ground_head_far_from_station(classifier):
    commune = make_commune(elevation=9.5).model_copy(update={"distance_to_station_km": 180.0})
    risk = classifier.classify(commune, make_station(10.0, rate=0.02), make_weather())
    assert risk.lead_time_hours == 100  # stage-based estimate, not head-based


def test_score_reflects_tier(classifier):
    scores = {}
    for tier_level in (8.0, 9.0, 10.6, 12.1):
        scores[tier_level] = classifier.classify(make_commune(), make_station(tier_level), make_weather()).score
    assert scores[8.0] < scores[9.0] < scores[10.6] < scores[12.1]
    assert all(0 <= s <= 100 for s in scores.values())
