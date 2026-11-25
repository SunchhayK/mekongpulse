"""Google Flood Hub API client for multi-day hydrological forecasts (IMP-04).

Layers 3-7 day river flood forecasts alongside live MRC gauge readings. When
`flood_hub_api_key` is unset, all methods degrade cleanly to None / empty dict
so dev and offline runs require zero external credentials.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .cache import StateStore
from .logging_utils import log_event
from .models import FloodForecast, RiskTier
from .stations import StationConfig

log = logging.getLogger("mekongpulse.flood_hub")

_SEVERITY_MAP: dict[str, RiskTier] = {
    "EXTREME": RiskTier.DANGER,
    "DANGER": RiskTier.DANGER,
    "SEVERE": RiskTier.DANGER,
    "WARNING": RiskTier.WARNING,
    "HIGH": RiskTier.WARNING,
    "ABOVE_NORMAL": RiskTier.ADVISORY,
    "ADVISORY": RiskTier.ADVISORY,
    "MODERATE": RiskTier.ADVISORY,
    "NO_FLOODING": RiskTier.NORMAL,
    "NORMAL": RiskTier.NORMAL,
    "UNKNOWN": RiskTier.NORMAL,
}


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _severity_to_tier(raw: str | None) -> RiskTier:
    if not raw:
        return RiskTier.NORMAL
    return _SEVERITY_MAP.get(raw.strip().upper(), RiskTier.NORMAL)


class FloodHubClient:
    """Thin async client for the Google Flood Hub API with StateStore caching."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://floodforecasting.googleapis.com/v1",
        state_store: StateStore | None = None,
        cache_ttl_seconds: int = 3600,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._state_store = state_store
        self._cache_ttl_seconds = cache_ttl_seconds
        self._timeout = timeout
        self._client = http_client

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        params = {"key": self._api_key} if self._api_key else None
        if self._client is not None:
            resp = await self._client.post(url, params=params, json=body)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, params=params, json=body)
        resp.raise_for_status()
        return resp.json()

    async def fetch_station_forecast(
        self,
        station_id: str,
        lat: float,
        lng: float,
        *,
        radius_deg: float = 0.25,
    ) -> FloodForecast | None:
        """Fetch latest multi-day flood forecast near a station's coordinates."""
        if not self._api_key:
            return None

        cache_key = f"flood_hub:station:{station_id}"
        if self._state_store is not None:
            cached = await self._state_store.get_json(cache_key)
            if isinstance(cached, dict):
                try:
                    return FloodForecast.model_validate(cached)
                except Exception:  # noqa: BLE001
                    pass

        body = {
            "loop": {
                "vertices": [
                    {"latitude": lat - radius_deg, "longitude": lng - radius_deg},
                    {"latitude": lat - radius_deg, "longitude": lng + radius_deg},
                    {"latitude": lat + radius_deg, "longitude": lng + radius_deg},
                    {"latitude": lat + radius_deg, "longitude": lng - radius_deg},
                ]
            }
        }
        try:
            payload = await self._post("floodStatus:searchLatestFloodStatusByArea", body)
        except (httpx.HTTPError, ValueError) as exc:
            log_event(log, "FLOOD_HUB_FETCH_FAILED", station_id=station_id, error=str(exc))
            return None

        forecast = self._parse_forecast(station_id, payload)
        if forecast is not None and self._state_store is not None:
            await self._state_store.set_json(
                cache_key,
                forecast.model_dump(mode="json"),
                ttl_seconds=self._cache_ttl_seconds,
            )
        return forecast

    async def fetch_forecasts_for_stations(
        self,
        stations: dict[str, StationConfig],
    ) -> dict[str, FloodForecast]:
        """Fetch forecasts for every station in the roster; returns {} when disabled."""
        if not self._api_key:
            return {}
        out: dict[str, FloodForecast] = {}
        for station_id, cfg in stations.items():
            forecast = await self.fetch_station_forecast(station_id, cfg.lat, cfg.lng)
            if forecast is not None:
                out[station_id] = forecast
        return out

    @staticmethod
    def _parse_forecast(station_id: str, payload: dict[str, Any]) -> FloodForecast | None:
        statuses = payload.get("floodStatuses") or payload.get("flood_statuses") or []
        if not statuses:
            return None

        best: FloodForecast | None = None
        now = datetime.now(timezone.utc)
        for item in statuses:
            if not isinstance(item, dict):
                continue
            tier = _severity_to_tier(item.get("severity"))
            issued_at = _parse_iso(item.get("issuedTime") or item.get("issued_time")) or now
            time_range = item.get("forecastTimeRange") or item.get("forecast_time_range") or {}
            peak_time = _parse_iso(
                item.get("peakTime")
                or item.get("peak_time")
                or time_range.get("endTime")
                or time_range.get("startTime")
            )
            if peak_time is not None:
                delta_days = max(1, min(7, int(round((peak_time - issued_at).total_seconds() / 86400.0))))
            else:
                delta_days = int(item.get("forecastDays") or item.get("forecast_days") or 5)
                peak_time = issued_at + timedelta(days=delta_days)

            discharge = item.get("forecastDischargeM3s") or item.get("dischargeM3s")
            confidence = item.get("confidence")
            candidate = FloodForecast(
                station_id=station_id,
                issued_at=issued_at,
                forecast_days=max(1, min(7, delta_days)),
                peak_severity=tier,
                peak_time=peak_time,
                forecast_discharge_m3s=float(discharge) if discharge is not None else None,
                confidence=float(confidence) if confidence is not None else None,
                source="google_flood_hub",
            )
            if best is None or candidate.peak_severity.severity > best.peak_severity.severity:
                best = candidate
        return best
