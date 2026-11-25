"""TEST-HYD-01 + rate-of-rise + empirical failover offset math."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from mekong_shared.mrc import (
    MRCTelemetryClient,
    MRCTelemetryError,
    MRCValidationError,
    Measurement,
    compute_hydraulic_offset,
    rate_of_rise_m_per_hr,
)

from support import BASE_TIME, mrc_payload, mrc_transport


async def test_poll_station_returns_grounded_reading():
    """TEST-HYD-01: live station read yields float level + timestamp (INV-01)."""
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(
            transport=mrc_transport({"020102": mrc_payload("020102", level=6.33, rate_m_per_hr=0.02)})
        ),
    )
    snapshot = await client.fetch_station("020102")
    assert snapshot.station_id == "020102"
    assert snapshot.name == "Prek Kdam"
    assert snapshot.level_m == pytest.approx(6.33, abs=1e-6)
    assert snapshot.alarm_stage_m == 9.5 and snapshot.flood_stage_m == 10.0
    assert snapshot.recorded_at == BASE_TIME
    assert snapshot.rate_of_rise_m_per_hr == pytest.approx(0.02, abs=1e-3)
    assert snapshot.is_stale_fallback is False and snapshot.source == "live"


async def test_station_http_error_raises_telemetry_error():
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(transport=mrc_transport({"020102": 500})),
    )
    with pytest.raises(MRCTelemetryError):
        await client.fetch_station("020102")


async def test_station_payload_mismatch_rejected():
    """A payload for a different station must never be attributed (INV-01)."""
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(transport=mrc_transport({"020102": mrc_payload("033401")})),
    )
    with pytest.raises(MRCTelemetryError):
        await client.fetch_station("020102")


def test_rate_of_rise_uses_trailing_window():
    from mekong_shared.mrc import Measurement

    base = BASE_TIME - timedelta(hours=6)
    points = [
        Measurement(at=base + timedelta(minutes=15 * i), level_m=5.0 + 0.05 * (i / 4))
        for i in range(25)  # 6h, rising 0.05 m/hr
    ]
    assert rate_of_rise_m_per_hr(points) == pytest.approx(0.05, abs=0.002)


def test_rate_of_rise_flat_is_zero():
    from mekong_shared.mrc import Measurement

    points = [
        Measurement(at=BASE_TIME - timedelta(minutes=15 * i), level_m=6.0) for i in range(12, 0, -1)
    ]
    assert rate_of_rise_m_per_hr(points) == 0.0


def test_hydraulic_offset_is_empirical_median():
    from mekong_shared.mrc import Measurement

    primary = [
        Measurement(at=BASE_TIME - timedelta(minutes=15 * i), level_m=5.0 + 0.5 - 0.001 * i)
        for i in range(40)
        # primary runs ~0.5m above fallback
    ]
    fallback = [
        Measurement(at=BASE_TIME - timedelta(minutes=15 * i), level_m=5.0 - 0.001 * i)
        for i in range(40)
    ]
    offset = compute_hydraulic_offset(primary, fallback)
    assert offset == pytest.approx(0.5, abs=0.01)


def test_hydraulic_offset_requires_overlap():
    from mekong_shared.mrc import Measurement

    primary = [Measurement(at=BASE_TIME - timedelta(hours=i), level_m=5.0) for i in range(10)]
    fallback = [Measurement(at=BASE_TIME - timedelta(days=1, hours=i), level_m=4.0) for i in range(10)]
    assert compute_hydraulic_offset(primary, fallback) is None


async def test_fetch_station_populates_rain_mm():
    """BUG-12: StationSnapshot.rain_mm is populated from latest measurement."""
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(
            transport=mrc_transport({"020102": mrc_payload("020102", level=6.33, rain=4.25)})
        ),
    )
    snapshot = await client.fetch_station("020102")
    assert snapshot.rain_mm == pytest.approx(4.25)


async def test_fetch_station_rejects_out_of_range_reading():
    """BUG-10 / IMP-05: implausible level outside [alarm-10, flood+3] raises QC_OUT_OF_RANGE."""
    payload = mrc_payload("020102", level=6.5)
    payload["measurements"][-1]["w"] = 18.0  # flood=10.0, high=13.0
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(transport=mrc_transport({"020102": payload})),
    )
    with pytest.raises(MRCValidationError) as exc_info:
        await client.fetch_station("020102")
    assert exc_info.value.kind == "QC_OUT_OF_RANGE"


async def test_fetch_station_rejects_single_tick_spike():
    """BUG-10 / IMP-05: implausible 15-min jump raises QC_SPIKE_REJECTED."""
    payload = mrc_payload("020102", level=6.5)
    payload["measurements"][-1]["w"] = 7.6  # +1.1m in 15 min
    client = MRCTelemetryClient(
        "https://mrc.test/api/v1",
        http_client=httpx.AsyncClient(transport=mrc_transport({"020102": payload})),
    )
    with pytest.raises(MRCValidationError) as exc_info:
        await client.fetch_station("020102")
    assert exc_info.value.kind == "QC_SPIKE_REJECTED"


def test_rate_of_rise_filters_single_noisy_tick_but_triggers_on_sustained_rise():
    """BUG-10: single +0.30m glitch must not cross 0.08 m/hr; >=2 consecutive ticks do."""
    base = BASE_TIME - timedelta(hours=3)
    flat_with_glitch = [
        Measurement(at=base + timedelta(minutes=15 * i), level_m=5.0) for i in range(12)
    ] + [Measurement(at=BASE_TIME, level_m=5.30)]
    assert rate_of_rise_m_per_hr(flat_with_glitch) == pytest.approx(0.0, abs=1e-4)

    sustained = [
        Measurement(at=base + timedelta(minutes=15 * i), level_m=5.0) for i in range(11)
    ] + [
        Measurement(at=BASE_TIME - timedelta(minutes=15), level_m=5.30),
        Measurement(at=BASE_TIME, level_m=5.30),
    ]
    assert rate_of_rise_m_per_hr(sustained) >= 0.08
