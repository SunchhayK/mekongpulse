"""Security helpers + domain model invariants."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from mekong_shared.models import CommuneRisk, CropStage, RiskTier, StationSnapshot
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
