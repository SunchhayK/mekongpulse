"""Open-Meteo weather client (FR-02).

Pulls 7-day hourly precipitation and 0-7cm soil moisture for given coordinates
and aggregates them into a `WeatherSnapshot`. Forecasts are fetched per
province (25 calls) rather than per commune (1,661 calls); every commune
inherits its province's forecast.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .models import WeatherSnapshot


class WeatherError(Exception):
    pass


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client = http_client

    async def _get(self, params: dict) -> dict:
        url = f"{self._base}/forecast"
        try:
            if self._client is not None:
                resp = await self._client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise WeatherError(f"Open-Meteo request failed: {exc}") from exc

    async def fetch_forecast(
        self, province_code: str, lat: float, lng: float
    ) -> WeatherSnapshot:
        payload = await self._get(
            {
                "latitude": round(lat, 4),
                "longitude": round(lng, 4),
                "hourly": "precipitation,soil_moisture_0_to_7cm",
                "forecast_days": 8,
                "timezone": "Asia/Phnom_Penh",
            }
        )
        hourly = payload.get("hourly") or {}
        rain = [float(v or 0.0) for v in hourly.get("precipitation", [])]
        moisture = [float(v) for v in hourly.get("soil_moisture_0_to_7cm", []) if v is not None]
        if len(rain) < 48:
            raise WeatherError(f"forecast for province {province_code} too short: {len(rain)}h")

        rain_48h = round(sum(rain[:48]), 1)
        rain_7d = round(sum(rain[:168]), 1)
        max_rain_24h = round(max(sum(rain[i : i + 24]) for i in range(0, 48)), 1)
        # Open-Meteo soil moisture is volumetric (m3/m3); report percent of saturation.
        soil_pct = round((moisture[0] * 100.0) if moisture else 0.0, 1)

        return WeatherSnapshot(
            province_code=province_code,
            latitude=lat,
            longitude=lng,
            precipitation_48h_mm=rain_48h,
            precipitation_7d_mm=rain_7d,
            max_rain_24h_mm=max_rain_24h,
            soil_moisture_pct=min(soil_pct, 100.0),
            fetched_at=datetime.now(timezone.utc),
        )
