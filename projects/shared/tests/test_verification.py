"""Verification summary, threshold calibration, and BigQueryExporter tests (IMP-07)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mekong_shared.config import Settings
from mekong_shared.models import (
    FieldReport,
    FieldReportStatus,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    WeatherSnapshot,
)
from mekong_shared.verification import (
    BigQueryExporter,
    calibrate_commune_thresholds,
    compute_verification_summary,
)

BASE = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)


def _alert(commune: str, hours_offset: float, lead_time: int | None = 24) -> SentinelAlert:
    return SentinelAlert(
        id=f"a-{commune}-{hours_offset}",
        commune_id=commune,
        station_id="033401",
        risk_tier=RiskTier.WARNING,
        lead_time_hours=lead_time,
        directive_title="Prepare sluice gates",
        bulletin_text="test",
        dispatched_at=BASE + timedelta(hours=hours_offset),
    )


def _report(
    rid: str, commune: str, status: FieldReportStatus, hours_offset: float
) -> FieldReport:
    return FieldReport(
        id=rid,
        commune_code=commune,
        status=status,
        source="telegram",
        reported_at=BASE + timedelta(hours=hours_offset),
    )


def test_verification_summary_computes_precision_recall_and_lead_error():
    alerts = [
        _alert("080404", 0.0, lead_time=24),  # TP: water reached at +18h (error 6h)
        _alert("080404", 100.0, lead_time=24),  # FP: no_water at +110h
    ]
    reports = [
        _report("r1", "080404", FieldReportStatus.WATER_REACHED, 18.0),
        _report("r2", "080404", FieldReportStatus.NO_WATER, 110.0),
        _report("r3", "030502", FieldReportStatus.WATER_REACHED, 10.0),  # FN: unwarned
    ]

    summary = compute_verification_summary(alerts, reports)
    assert summary.total_alerts == 2
    assert summary.true_positives == 1
    assert summary.false_positives == 1
    assert summary.false_negatives == 1
    assert summary.precision == pytest.approx(0.5)
    assert summary.recall == pytest.approx(0.5)
    assert summary.mean_lead_time_error_hours == pytest.approx(6.0)
    assert summary.by_commune["080404"]["precision"] == pytest.approx(0.5)
    assert summary.by_commune["030502"]["false_negatives"] == 1


def test_calibrate_commune_thresholds_adjusts_margin_and_multiplier():
    alerts = [
        _alert("080404", 0.0, lead_time=20),  # actual arrival at +10h => ratio 0.5
        _alert("080405", 0.0, lead_time=24),  # FP => tighten margin
    ]
    reports = [
        _report("r1", "080404", FieldReportStatus.WATER_REACHED, 10.0),
        _report("r2", "080405", FieldReportStatus.NO_WATER, 12.0),
        _report("r3", "030502", FieldReportStatus.WATER_REACHED, 5.0),  # FN => widen margin
    ]

    cals = {c.commune_code: c for c in calibrate_commune_thresholds(alerts, reports)}
    assert cals["030502"].levee_margin_m == pytest.approx(0.40)  # +0.10 for FN
    assert cals["080405"].levee_margin_m == pytest.approx(0.25)  # -0.05 for FP
    assert cals["080404"].lead_time_multiplier == pytest.approx(0.75)  # avg(1.0, 0.5)


async def test_bigquery_exporter_noop_when_unset_and_streams_when_configured(tmp_path):
    off_settings = Settings(
        _env_file=None, environment="development", data_dir=tmp_path, audio_dir=tmp_path / "audio"
    )
    noop = BigQueryExporter(off_settings)
    assert noop.enabled is False
    snap = StationSnapshot(
        station_id="033401",
        name="Chaktomuk",
        river="Bassac",
        level_m=8.0,
        alarm_stage_m=10.5,
        flood_stage_m=12.0,
        rate_of_rise_m_per_hr=0.01,
        rain_mm=1.2,
        recorded_at=BASE,
    )
    assert await noop.export_observations([snap]) == 0

    class FakeBQ:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[dict]]] = []

        def insert_rows_json(self, table_id: str, rows: list[dict]):
            self.calls.append((table_id, rows))
            return []

    on_settings = Settings(
        _env_file=None,
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
        bigquery_project="proj-1",
        bigquery_dataset="mekong_analytics",
    )
    fake = FakeBQ()
    exporter = BigQueryExporter(on_settings, client=fake)
    assert exporter.enabled is True
    assert await exporter.export_observations([snap]) == 1
    assert await exporter.export_weather(
        [
            WeatherSnapshot(
                province_code="08",
                latitude=11.5,
                longitude=105.0,
                precipitation_48h_mm=12.0,
                precipitation_7d_mm=30.0,
                max_rain_24h_mm=8.0,
                soil_moisture_pct=50.0,
                fetched_at=BASE,
            )
        ]
    ) == 1
    assert await exporter.export_alerts([_alert("080404", 0.0)]) == 1
    assert await exporter.export_field_reports(
        [_report("r1", "080404", FieldReportStatus.WATER_REACHED, 5.0)]
    ) == 1
    assert [t for t, _ in fake.calls] == [
        "proj-1.mekong_analytics.hydro_observations",
        "proj-1.mekong_analytics.weather_forecasts",
        "proj-1.mekong_analytics.sentinel_alerts",
        "proj-1.mekong_analytics.field_reports",
    ]
