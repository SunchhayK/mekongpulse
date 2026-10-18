"""Evidence payload: QC verdicts, confidence downgrades, chain, field reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mekong_shared.evidence import build_evidence
from mekong_shared.models import (
    FieldReport,
    FieldReportStatus,
    RiskTier,
    StationSnapshot,
    WeatherSnapshot,
)
from mekong_shared.pipeline import AssessmentUnavailable, CommuneNotFound

from support import healthy_handlers

COMMUNE = "030502"  # Kampong Cham town, station 019802, 0.47 km
STATION = "019802"
FAR_COMMUNE = "030208"  # Ta Prok, 50.2 km from station 019802
CHAKTOMUK_COMMUNE = "031402"  # Chi Bal, station 033401, 27.4 km

STATION_META = {
    "019802": {"name": "Kompong Cham", "river": "Mekong", "alarm": 15.2, "flood": 16.2},
    "020102": {"name": "Prek Kdam", "river": "Tonlesap", "alarm": 9.5, "flood": 10.0},
    "033401": {"name": "Chaktomuk", "river": "Bassac", "alarm": 10.5, "flood": 12.0},
    "033402": {"name": "Koh Khel", "river": "Bassac", "alarm": 7.9, "flood": 8.4},
}

CONTRACT_KEYS = {
    "commune_code", "commune_name_kh", "commune_name_en", "generated_at", "risk_tier",
    "score", "confidence", "confidence_reasons", "station", "qc", "cross_checks",
    "evidence_chain", "limitations",
}


def _obs(station_id: str, level: float, minutes_ago: int, *, rate: float = 0.0, **extra):
    meta = STATION_META[station_id]
    return StationSnapshot(
        station_id=station_id,
        name=meta["name"],
        river=meta["river"],
        level_m=level,
        alarm_stage_m=meta["alarm"],
        flood_stage_m=meta["flood"],
        rate_of_rise_m_per_hr=rate,
        recorded_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        **extra,
    )


async def _save_series(repo, station_id: str, points, *, rate: float = 0.0, **extra) -> None:
    """Save (minutes_ago, level) pairs as station observations."""
    for minutes_ago, level in points:
        await repo.save_observation(_obs(station_id, level, minutes_ago, rate=rate, **extra))


async def _seed_weather(repo, gazetteer, rain_48h: float = 0.0) -> None:
    commune = gazetteer.get(COMMUNE)
    await repo.save_weather(
        WeatherSnapshot(
            province_code=commune.province_code or "03",
            latitude=commune.lat or 12.0,
            longitude=commune.lng or 105.46,
            precipitation_48h_mm=rain_48h,
            precipitation_7d_mm=rain_48h,
            max_rain_24h_mm=rain_48h,
            soil_moisture_pct=50.0,
            fetched_at=datetime.now(timezone.utc),
        )
    )


def _hourly(start_hours_ago: int, count: int, level_at) -> list[tuple[int, float]]:
    """(minutes_ago, level) points, oldest first; level_at takes hours-ago."""
    return [(60 * h, level_at(h)) for h in range(start_hours_ago, start_hours_ago - count, -1)]


# --- clean path ------------------------------------------------------------------

async def test_clean_series_high_confidence_full_chain(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    # 25 varied hourly points ending now, gentle rise; ADVISORY via the rain rule.
    await _save_series(repo, STATION, _hourly(24, 25, lambda h: 12.0 + 0.02 * (24 - h)), rate=0.02)
    await _seed_weather(repo, gazetteer, rain_48h=45.0)

    payload = await build_evidence(pipeline, COMMUNE)
    body = payload.model_dump(mode="json")

    assert set(body) == CONTRACT_KEYS
    assert body["commune_name_kh"] == "កំពង់ចាម"
    assert body["commune_name_en"] == "Kampong Cham"
    assert body["risk_tier"] == "ADVISORY"
    assert body["confidence"] == "high"
    assert body["confidence_reasons"] == [
        "fresh_telemetry", "qc_clean", "near_station", "sources_agree",
    ]

    station = body["station"]
    assert station["station_id"] == STATION
    assert station["distance_km"] == 0.47
    assert station["freshness"] == "fresh"
    assert station["age_minutes"] < 90
    assert station["level_m"] == 12.48
    assert station["alarm_stage_m"] == 15.2 and station["flood_stage_m"] == 16.2

    assert body["qc"]["status"] == "pass"
    assert [c["id"] for c in body["qc"]["checks"]] == ["gaps", "stuck", "spike", "range"]
    assert [c["status"] for c in body["qc"]["checks"]] == ["pass"] * 4

    assert [c["id"] for c in body["cross_checks"]] == [
        "rainfall_agreement", "upstream_coherence",
    ]
    assert body["cross_checks"][0]["status"] == "agree"
    assert "Heuristic" in body["cross_checks"][0]["detail"]
    assert body["cross_checks"][1]["status"] == "unavailable"

    chain = {s["id"]: s for s in body["evidence_chain"]}
    assert [s["id"] for s in body["evidence_chain"]] == [
        "reading", "change", "threshold", "tier", "directive",
    ]
    assert "12.48" in chain["reading"]["text_en"] and "Kompong Cham" in chain["reading"]["text_en"]
    assert chain["reading"]["text_kh"]
    assert "rising" in chain["change"]["text_en"]
    assert "below the alarm stage" in chain["threshold"]["text_en"]
    assert "ADVISORY" in chain["tier"]["text_en"]
    assert "MONITOR_NORMAL_OPERATIONS" in chain["directive"]["text_en"]
    assert chain["directive"]["text_kh"]

    assert body["limitations"]["text_en"] and body["limitations"]["text_kh"]
    assert "cannot" in body["limitations"]["text_en"]


async def test_danger_rules_show_in_chain(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await _save_series(repo, STATION, _hourly(6, 7, lambda h: 16.25 + 0.03 * (6 - h)), rate=0.12)
    await _seed_weather(repo, gazetteer, rain_48h=70.0)

    payload = await build_evidence(pipeline, COMMUNE)
    assert payload.risk_tier is RiskTier.DANGER

    chain = {s.id: s for s in payload.evidence_chain}
    assert "16.43" in chain["reading"].text_en
    assert "rising fast" in chain["change"].text_en
    assert "above the flood stage" in chain["threshold"].text_en
    assert "DANGER" in chain["tier"].text_en and "near zero" in chain["tier"].text_en
    assert "EMERGENCY_HARVEST_ACCELERATION" in chain["directive"].text_en


# --- QC verdicts ------------------------------------------------------------------

async def test_gapped_series_warns_then_downgrades_to_medium(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    # 45 of 59 hourly slots -> ~24% missing, above warn ratio but below fail.
    points = [(60 * h, 12.0 + 0.01 * h) for h in range(1, 60) if h % 4 != 0]
    await _save_series(repo, STATION, points)
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    gaps = payload.qc.checks[0]
    assert gaps.id == "gaps" and gaps.status == "warn"
    assert "missing" in gaps.detail
    assert payload.qc.status == "warn"
    assert payload.confidence == "medium"
    assert "qc_warning" in payload.confidence_reasons


async def test_gapped_series_fails_then_drops_to_low(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    # every third hourly slot -> ~66% missing, above fail ratio.
    points = [(60 * h, 12.0 + 0.03 * h) for h in range(1, 60) if h % 3 == 1]
    await _save_series(repo, STATION, points)
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    gaps = payload.qc.checks[0]
    assert gaps.id == "gaps" and gaps.status == "fail"
    assert payload.qc.status == "fail"
    assert payload.confidence == "low"
    assert "qc_fail" in payload.confidence_reasons
    assert "qc_warning" not in payload.confidence_reasons


async def test_stuck_series_fails_qc(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    levels = [12.0 + 0.01 * i for i in range(25)]
    for i in range(8, 16):  # eight identical hourly readings = 7 h run
        levels[i] = 12.50
    await _save_series(repo, STATION, [(60 * (24 - i), level) for i, level in enumerate(levels)])
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    stuck = payload.qc.checks[1]
    assert stuck.id == "stuck" and stuck.status == "fail"
    assert "12.50 m for 7.0 h" in stuck.detail
    assert payload.qc.status == "fail"
    assert payload.confidence == "low"


async def test_spiked_series_fails_qc(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    levels = [12.0 + 0.01 * i for i in range(25)]
    levels[12] = 13.50  # 1.39 m step, above the fail threshold
    await _save_series(repo, STATION, [(60 * (24 - i), level) for i, level in enumerate(levels)])
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    spike = payload.qc.checks[2]
    assert spike.id == "spike" and spike.status == "fail"
    assert "1.39 m" in spike.detail
    assert payload.qc.status == "fail"
    assert payload.confidence == "low"


async def test_out_of_range_series_fails_qc(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    # whole series below alarm - 10 m: wrong datum, not a spike.
    await _save_series(repo, STATION, _hourly(24, 25, lambda h: 3.0 + 0.01 * (24 - h)))
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    rng = payload.qc.checks[3]
    assert rng.id == "range" and rng.status == "fail"
    assert "5.20-19.20 m" in rng.detail
    assert payload.qc.status == "fail"
    assert payload.confidence == "low"


async def test_single_reading_marks_qc_unavailable(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await repo.save_observation(_obs(STATION, 12.5, 5))

    payload = await build_evidence(pipeline, COMMUNE)
    assert payload.qc.status == "unavailable"
    assert [c.status for c in payload.qc.checks] == [
        "unavailable", "unavailable", "unavailable", "pass",
    ]
    assert "qc_clean" not in payload.confidence_reasons
    assert "qc_warning" not in payload.confidence_reasons


# --- confidence downgrades ----------------------------------------------------------

async def test_fallback_telemetry_downgrades_confidence(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await _save_series(
        repo, STATION, _hourly(24, 25, lambda h: 12.5 + (0.01 if h % 2 else 0.0)),
        is_stale_fallback=True, source="fallback",
    )
    await _seed_weather(repo, gazetteer)

    payload = await build_evidence(pipeline, COMMUNE)
    assert payload.confidence == "medium"
    assert "stale_telemetry" in payload.confidence_reasons
    assert "fresh_telemetry" not in payload.confidence_reasons


async def test_far_station_downgrades_confidence(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await _save_series(repo, STATION, _hourly(24, 25, lambda h: 12.5 + (0.01 if h % 2 else 0.0)))

    payload = await build_evidence(pipeline, FAR_COMMUNE)
    assert payload.station.distance_km is not None and payload.station.distance_km > 50.0
    assert payload.confidence == "medium"
    assert "far_from_station" in payload.confidence_reasons
    assert "near_station" not in payload.confidence_reasons


async def test_rainfall_disagreement_downgrades_confidence(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await _save_series(repo, STATION, _hourly(24, 25, lambda h: 12.0 + 0.1 * (24 - h)), rate=0.1)
    await _seed_weather(repo, gazetteer, rain_48h=0.0)

    payload = await build_evidence(pipeline, COMMUNE)
    rainfall = payload.cross_checks[0]
    assert rainfall.id == "rainfall_agreement" and rainfall.status == "disagree"
    assert "Heuristic" in rainfall.detail
    assert payload.confidence == "medium"
    assert "source_disagree" in payload.confidence_reasons


async def test_upstream_disagreement_uses_nearest_station_with_data(repo, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    # Chaktomuk falling over 24 h, Prek Kdam (30.9 km away) rising.
    await _save_series(repo, "033401", _hourly(24, 25, lambda h: 7.2 + 0.01 * h))
    await _save_series(repo, "020102", _hourly(24, 25, lambda h: 6.0 + 0.05 * (24 - h)))

    payload = await build_evidence(pipeline, CHAKTOMUK_COMMUNE)
    upstream = payload.cross_checks[1]
    assert upstream.id == "upstream_coherence" and upstream.status == "disagree"
    assert "Prek Kdam" in upstream.detail
    assert "24 h trends disagree" in upstream.detail
    assert payload.confidence == "medium"
    assert "source_disagree" in payload.confidence_reasons


async def test_upstream_agreement_when_flat(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await _save_series(repo, STATION, _hourly(24, 25, lambda h: 12.5 + (0.01 if h % 2 else 0.0)))
    await _save_series(repo, "033401", _hourly(24, 25, lambda h: 7.2 + 0.02 * (24 - h)))
    await _seed_weather(repo, gazetteer, rain_48h=0.0)

    payload = await build_evidence(pipeline, COMMUNE)
    upstream = payload.cross_checks[1]
    assert upstream.status == "agree"  # flat here vs rising upstream: no contradiction
    assert "Chaktomuk" in upstream.detail


# --- resolution errors ----------------------------------------------------------------

async def test_unknown_commune_raises_not_found(repo, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    with pytest.raises(CommuneNotFound):
        await build_evidence(pipeline, "999999")


async def test_stationless_commune_raises_unavailable(repo, gazetteer, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    orphan = next(c for c in gazetteer.all_communes() if not c.nearest_station_id)
    with pytest.raises(AssessmentUnavailable):
        await build_evidence(pipeline, orphan.code)


async def test_missing_observation_fetches_live_and_persists(repo, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    payload = await build_evidence(pipeline, COMMUNE)
    assert payload.station.source == "live"

    saved = await repo.latest_observation(STATION)
    assert saved is not None and saved.source == "live"
    assert saved.level_m == 12.5


# --- field reports ---------------------------------------------------------------------

async def test_field_reports_memory_repo_roundtrip(repo):
    now = datetime.now(timezone.utc)
    older = FieldReport(
        id="a" * 32, commune_code=COMMUNE, status=FieldReportStatus.WATER_REACHED,
        note="Water in the paddy", reporter_label="Commune chief", source="web",
        reported_at=now - timedelta(hours=2),
    )
    newer = FieldReport(
        id="b" * 32, commune_code=COMMUNE, status=FieldReportStatus.NO_WATER,
        source="telegram", reported_at=now,
    )
    other = FieldReport(
        id="c" * 32, commune_code="030301", status=FieldReportStatus.OTHER,
        source="web", reported_at=now,
    )
    for report in (older, newer, other):
        assert await repo.add_field_report(report) == report

    listing = await repo.list_field_reports(COMMUNE)
    assert [r.id for r in listing] == ["b" * 32, "a" * 32]  # newest first
    assert listing[0].status is FieldReportStatus.NO_WATER
    assert listing[0].note is None and listing[0].reporter_label is None

    assert await repo.list_field_reports("039999") == []
    limited = await repo.list_field_reports(limit=2)
    assert len(limited) == 2
    assert limited[0].reported_at >= limited[1].reported_at
