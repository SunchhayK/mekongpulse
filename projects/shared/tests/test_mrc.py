"""TEST-HYD-01 + rate-of-rise + empirical failover offset math."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from mekong_shared.mrc import (
    MRCTelemetryClient,
    MRCTelemetryError,
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
