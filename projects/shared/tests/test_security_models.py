"""Security helpers + domain model invariants."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from mekong_shared.config import Settings
from mekong_shared.memory_repo import MemoryRepository
from mekong_shared.models import (
    AgentRun,
    AgentRunStatus,
    CommuneCalibration,
    CommuneRisk,
    CropStage,
    CropType,
    FloodForecast,
    PatrolRun,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    Subscription,
    VerificationSummary,
)
from mekong_shared.risk import RATE_PULSE_M_PER_HR, RAIN_HEAVY_48H_MM
from mekong_shared.security import (
    anonymize_chat_id,
    anonymize_location,
    new_trace_id,
    parse_traceparent,
    sha256_hex,
)


def test_anonymization_is_salted_and_deterministic():
    a = anonymize_location(11.556, 104.928, "salt-a")
    assert a == anonymize_location(11.556, 104.928, "salt-a")
    assert a != anonymize_location(11.556, 104.928, "salt-b")
    # coordinates rounded to ~1km make the hash stable across GPS jitter
    assert a == anonymize_location(11.5561, 104.9284, "salt-a")
    assert a != anonymize_location(12.6, 104.9, "salt-a")


def test_chat_id_anonymization_hides_raw_value():
    hashed = anonymize_chat_id(123456789, "salt")
    assert "123456789" not in hashed
    assert len(hashed) == 16


def test_sha256_hex_accepts_numbers():
    assert sha256_hex(42, "s") == sha256_hex("42", "s")


def test_parse_traceparent_valid_and_invalid():
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    header = f"00-{trace_id}-b7ad6b7169203331-01"
    assert parse_traceparent(header) == trace_id
    assert parse_traceparent("garbage") is None
    assert parse_traceparent(None) is None
    assert parse_traceparent("00-short-b7ad6b7169203331-01") is None


def test_new_trace_id_shape():
    assert re.fullmatch(r"[0-9a-f]{32}", new_trace_id())


def test_risk_tier_ordering_and_metadata():
    assert RiskTier.DANGER.severity > RiskTier.WARNING.severity > RiskTier.ADVISORY.severity > RiskTier.NORMAL.severity
    assert RiskTier.DANGER.at_least(RiskTier.ADVISORY)
    assert not RiskTier.NORMAL.at_least(RiskTier.WARNING)
    for tier in RiskTier:
        assert tier.emoji and tier.label_kh


def test_crop_stage_labels():
    for stage in CropStage:
        assert stage.label_kh and stage.label_en


def test_station_snapshot_margins():
    snap = StationSnapshot(
        station_id="019802",
        name="Kompong Cham",
        river="Mekong",
        level_m=15.5,
        alarm_stage_m=15.2,
        flood_stage_m=16.2,
        rate_of_rise_m_per_hr=0.0,
        recorded_at=datetime.now(timezone.utc),
    )
    assert snap.margin_to_alarm_m == pytest.approx(-0.3)
    assert snap.margin_to_flood_m == pytest.approx(0.7)


def test_commune_risk_score_bounds_enforced():
    with pytest.raises(ValidationError):
        CommuneRisk(
            commune_code="080404",
            commune_name_kh="កោះធំ ក",
            commune_name_en="Kaoh Thum Ka",
            tier=RiskTier.NORMAL,
            score=101,
            updated_at=datetime.now(timezone.utc),
        )


def test_pinned_thresholds():
    """AC-01 pins the pulse threshold; rain-hold rule uses 60mm/48h."""
    assert RATE_PULSE_M_PER_HR == 0.08
    assert RAIN_HEAVY_48H_MM == 60.0


def test_new_domain_models_and_settings():
    now = datetime.now(timezone.utc)
    for ct in CropType:
        assert ct.label_kh and ct.label_en

    sub = Subscription(
        telegram_chat_id="123",
        commune_id="080404",
        crop_type=CropType.LIVESTOCK,
        planting_date=date(2026, 7, 1),
    )
    assert sub.crop_type == CropType.LIVESTOCK
    assert sub.planting_date == date(2026, 7, 1)

    run = PatrolRun(
        id="firestore-doc-id",
        run_at=now,
        stations_polled=9,
        communes_evaluated=1661,
        alerts_dispatched_count=0,
        execution_duration_ms=100,
    )
    alert = SentinelAlert(
        id="alert-doc-id",
        patrol_run_id=run.id,
        commune_id="080404",
        risk_tier=RiskTier.WARNING,
        directive_title="Watch",
        bulletin_text="text",
        dispatched_at=now,
    )
    assert alert.patrol_run_id == "firestore-doc-id"

    forecast = FloodForecast(
        station_id="033401",
        issued_at=now,
        forecast_days=5,
        peak_severity=RiskTier.DANGER,
    )
    assert forecast.source == "google_flood_hub"

    summary = VerificationSummary(total_alerts=5, true_positives=4, false_positives=1, precision=0.8)
    assert summary.precision == pytest.approx(0.8)

    settings = Settings(environment="production", repository_backend="postgres")
    assert settings.use_firestore is False
    assert settings.gemini_tts_model_chain == ["gemini-3.8-flash-lite-tts", "gemini-3.7-flash-tts"]


async def test_memory_repo_parity_for_new_methods():
    repo = MemoryRepository()
    now = datetime.now(timezone.utc)
    await repo.save_observation(
        StationSnapshot(
            station_id="033401",
            name="Chaktomuk",
            river="Bassac",
            level_m=7.5,
            alarm_stage_m=10.5,
            flood_stage_m=12.0,
            rate_of_rise_m_per_hr=0.01,
            recorded_at=now,
            rain_mm=8.2,
        )
    )
    series = await repo.telemetry_series("033401", hours=24)
    assert series[0][2] == pytest.approx(8.2)

    await repo.upsert_subscription(
        "c1", "080404", "VEGETATIVE", crop_type="RICE", planting_date=date(2026, 6, 1)
    )
    assert len(await repo.list_all_subscriptions()) == 1

    run = AgentRun(
        id="r1",
        commune_code="080404",
        current_tier=RiskTier.DANGER,
        status=AgentRunStatus.PENDING_APPROVAL,
        draft_khmer="draft",
        created_at=now,
    )
    await repo.add_agent_run(run)
    claimed = await repo.claim_agent_run_for_publish("r1")
    assert claimed is not None and claimed.status == AgentRunStatus.PUBLISHING
    assert await repo.claim_agent_run_for_publish("r1") is None

    cal = CommuneCalibration(commune_code="080404", levee_margin_m=0.25, updated_at=now)
    await repo.save_commune_calibration(cal)
    assert (await repo.list_commune_calibrations())["080404"].levee_margin_m == pytest.approx(0.25)
