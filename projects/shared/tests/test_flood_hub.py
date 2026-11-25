"""Google Flood Hub client tests: mock transport, caching, disabled no-op (IMP-04)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from mekong_shared.cache import InMemoryStateStore
from mekong_shared.flood_hub import FloodHubClient
from mekong_shared.models import RiskTier
from mekong_shared.stations import StationConfig


async def test_flood_hub_disabled_returns_none_and_empty():
    client = FloodHubClient(api_key=None)
    assert client.enabled is False
    assert await client.fetch_station_forecast("019802", 12.0, 105.46) is None
    station = StationConfig(
        id="019802",
        name_en="Kompong Cham",
        name_kh="កំពង់ចាម",
        river="Mekong",
        lat=12.0,
        lng=105.46,
        alarm_stage_m=15.2,
        flood_stage_m=16.2,
    )
    assert await client.fetch_forecasts_for_stations({"019802": station}) == {}


async def test_flood_hub_parses_and_caches_multiday_forecast():
    calls = {"count": 0}
    issued = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    peak = issued + timedelta(days=4)

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.url.params.get("key") == "test-fh-key"
        return httpx.Response(
            200,
            json={
                "floodStatuses": [
                    {
                        "severity": "WARNING",
                        "issuedTime": issued.isoformat(),
                        "peakTime": peak.isoformat(),
                        "forecastDischargeM3s": 32500.0,
                        "confidence": 0.85,
                    }
                ]
            },
        )

    store = InMemoryStateStore()
    client = FloodHubClient(
        api_key="test-fh-key",
        base_url="https://floodhub.test/v1",
        state_store=store,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    first = await client.fetch_station_forecast("019802", 12.0, 105.46)
    second = await client.fetch_station_forecast("019802", 12.0, 105.46)

    assert first is not None
    assert first.station_id == "019802"
    assert first.peak_severity is RiskTier.WARNING
    assert first.forecast_days == 4
    assert first.forecast_discharge_m3s == 32500.0
    assert first.confidence == 0.85
    assert second == first
    assert calls["count"] == 1  # second call served from StateStore cache


async def test_flood_hub_http_error_degrades_gracefully():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    client = FloodHubClient(
        api_key="test-fh-key",
        base_url="https://floodhub.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await client.fetch_station_forecast("019802", 12.0, 105.46) is None
