"""FR-02: Open-Meteo forecast aggregation (48h/7d sums, 24h peak, soil moisture)."""

from __future__ import annotations

import httpx
import pytest

from mekong_shared.weather import OpenMeteoClient, WeatherError


def weather_transport(payload: dict | int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(payload, int):
            return httpx.Response(payload)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def hourly_payload(rain_mm_per_h: float = 1.0, hours: int = 192) -> dict:
    return {
        "hourly": {
            "precipitation": [rain_mm_per_h] * hours,
            "soil_moisture_0_to_7cm": [0.35] * hours,
        }
    }


async def test_forecast_aggregates_rain_windows():
    client = OpenMeteoClient(
        "https://meteo.test/v1", http_client=httpx.AsyncClient(transport=weather_transport(hourly_payload()))
    )
    snap = await client.fetch_forecast("08", 11.5, 105.0)
    assert snap.province_code == "08"
    assert snap.precipitation_48h_mm == pytest.approx(48.0)
    assert snap.precipitation_7d_mm == pytest.approx(168.0)
    assert snap.max_rain_24h_mm == pytest.approx(24.0)
    assert snap.soil_moisture_pct == pytest.approx(35.0)


async def test_forecast_too_short_is_rejected():
    client = OpenMeteoClient(
        "https://meteo.test/v1", http_client=httpx.AsyncClient(transport=weather_transport(hourly_payload(hours=47)))
    )
    with pytest.raises(WeatherError):
        await client.fetch_forecast("08", 11.5, 105.0)


async def test_forecast_http_error_raises_weather_error():
    client = OpenMeteoClient(
        "https://meteo.test/v1", http_client=httpx.AsyncClient(transport=weather_transport(500))
    )
    with pytest.raises(WeatherError):
        await client.fetch_forecast("08", 11.5, 105.0)
