"""OpenTelemetry no-op/configured tracing and structured SLO event tests (IMP-08)."""

from __future__ import annotations

import logging

from mekong_shared.config import Settings
from mekong_shared.telemetry import (
    configure_tracing,
    emit_gauge_failover,
    emit_mrc_station_timeout,
    emit_telemetry_warning,
    emit_tts_unavailable,
    emit_watch_publish_failed,
    traced_span,
)


def test_configure_tracing_noop_when_disabled(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
    )
    assert configure_tracing(None, settings) is False
    with traced_span("test.op", {"commune_code": "080404"}) as span:
        span.set_attribute("tier", "WARNING")
        span.add_event("checked")


def test_slo_emitters_log_structured_events(caplog):
    with caplog.at_level(logging.INFO, logger="mekongpulse.telemetry"):
        emit_mrc_station_timeout("020102", "timeout")
        emit_watch_publish_failed("run-1", "080404", "telegram 502")
        emit_tts_unavailable("080404", "quota exceeded")
        emit_telemetry_warning("020102", "QC_SPIKE_REJECTED", "spike 1.5m")
        emit_gauge_failover("020102", "fallback", "033401")

    events = [getattr(r, "event", None) for r in caplog.records]
    assert events == [
        "MRC_STATION_TIMEOUT",
        "WATCH_PUBLISH_FAILED",
        "TTS_UNAVAILABLE",
        "TELEMETRY_WARNING",
        "GAUGE_FAILOVER",
    ]
    metric_types = [getattr(r, "fields", {}).get("metric_type") for r in caplog.records]
    assert all(mt and mt.startswith("custom.googleapis.com/mekongpulse/") for mt in metric_types)
