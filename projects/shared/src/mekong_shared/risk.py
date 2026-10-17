"""Spatial inundation risk classification (FR-03, INV-03).

Deterministic, documented rules combining live station state (INV-01) with the
province rain forecast and the commune's DEM ground elevation. Under
conflicting or uncertain signals the classifier takes the conservative posture
(INV-03): escalate the tier, never downgrade.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import Commune, CommuneRisk, FloodReason, RiskTier, StationSnapshot, WeatherSnapshot

# Thresholds (documented in README; AC-01 requires rate > 0.08 m/hr to reach WARNING+)
RATE_PULSE_M_PER_HR = 0.08
RATE_EMERGING_M_PER_HR = 0.04
RAIN_HEAVY_48H_MM = 60.0
RAIN_ADVISORY_48H_MM = 40.0
RAIN_FLASH_24H_MM = 80.0
LEVEE_MARGIN_M = 0.30  # empirical buffer: water surface this close to ground = concern

_TIER_SCORE = {RiskTier.NORMAL: 15, RiskTier.ADVISORY: 40, RiskTier.WARNING: 70, RiskTier.DANGER: 95}
_ESCALATE = {
    RiskTier.NORMAL: RiskTier.ADVISORY,
    RiskTier.ADVISORY: RiskTier.WARNING,
    RiskTier.WARNING: RiskTier.DANGER,
    RiskTier.DANGER: RiskTier.DANGER,
}


class SpatialRiskClassifier:
    def classify(
        self,
        commune: Commune,
        station: StationSnapshot,
        weather: WeatherSnapshot | None,
        *,
        ground_elevation_m: float | None = None,
    ) -> CommuneRisk:
        if ground_elevation_m is None:
            ground_elevation_m = commune.ground_elevation_m

        level = station.level_m
        alarm = station.alarm_stage_m
        flood = station.flood_stage_m
        rate = station.rate_of_rise_m_per_hr
        rain48 = weather.precipitation_48h_mm if weather else None
        rain24 = weather.max_rain_24h_mm if weather else None

        drivers: list[str] = []
        reason = FloodReason.NONE
        tier = RiskTier.NORMAL

        # --- river stage rules -------------------------------------------------
        if level >= flood:
            tier, reason = RiskTier.DANGER, FloodReason.RIVER_OVERFLOW
            drivers.append(f"level {level:.2f}m >= flood stage {flood:.2f}m")
        elif level >= alarm and rate >= RATE_PULSE_M_PER_HR:
            tier, reason = RiskTier.DANGER, FloodReason.RIVER_PULSE
            drivers.append(f"above alarm stage with rapid rise {rate:.2f} m/hr")
        elif level >= alarm and rain48 is not None and rain48 >= RAIN_HEAVY_48H_MM:
            tier, reason = RiskTier.DANGER, FloodReason.RIVER_OVERFLOW
            drivers.append(f"above alarm stage and {rain48:.0f}mm rain forecast (48h)")
        elif level >= alarm:
            tier, reason = RiskTier.WARNING, FloodReason.RIVER_OVERFLOW
            drivers.append(f"level {level:.2f}m >= alarm stage {alarm:.2f}m")
        elif rate >= RATE_PULSE_M_PER_HR:
            tier, reason = RiskTier.WARNING, FloodReason.RIVER_PULSE
            drivers.append(f"rapid rise {rate:.2f} m/hr (pulse threshold {RATE_PULSE_M_PER_HR})")
        elif rain48 is not None and rain48 >= RAIN_HEAVY_48H_MM and level >= alarm - 1.0:
            tier, reason = RiskTier.WARNING, FloodReason.RIVER_OVERFLOW
            drivers.append(f"{rain48:.0f}mm rain (48h) with level within 1m of alarm stage")

        # --- elevation-based inundation (DEM elevation vs gauge water surface) ---
        zero = _zero_gauge_elevation(station)
        if ground_elevation_m is not None and zero is not None:
            water_surface = level + zero
            head = ground_elevation_m - water_surface
            if head <= 0:
                if tier.severity < RiskTier.DANGER.severity:
                    tier, reason = RiskTier.DANGER, FloodReason.RIVER_OVERFLOW
                drivers.append(
                    f"water surface {water_surface:.2f}m above commune ground {ground_elevation_m:.1f}m"
                )
            elif head <= LEVEE_MARGIN_M:
                if tier.severity < RiskTier.WARNING.severity:
                    tier, reason = RiskTier.WARNING, FloodReason.RIVER_OVERFLOW
                drivers.append(
                    f"water surface within {head:.2f}m of commune ground {ground_elevation_m:.1f}m"
                )

        # --- rain rules (localized flooding even with a calm river) ------------
        if len(drivers) == 0 or tier.severity < RiskTier.ADVISORY.severity:
            if rain48 is not None and rain48 >= RAIN_ADVISORY_48H_MM:
                tier = RiskTier.ADVISORY
                reason = FloodReason.LOCAL_FLASH_FLOOD if (rain24 or 0) >= RAIN_FLASH_24H_MM else reason
                drivers.append(f"{rain48:.0f}mm rain forecast (48h) >= {RAIN_ADVISORY_48H_MM:.0f}mm")
            elif rate >= RATE_EMERGING_M_PER_HR:
                tier = RiskTier.ADVISORY
                drivers.append(f"emerging rise {rate:.2f} m/hr")
            elif level >= alarm - 2.0:
                tier = RiskTier.ADVISORY
                drivers.append(f"level {level:.2f}m approaching alarm stage {alarm:.2f}m")

        # --- telemetry uncertainty: conservative escalation (INV-03) -----------
        if station.is_stale_fallback or station.source == "cache":
            if tier.severity >= RiskTier.ADVISORY.severity:
                tier = _ESCALATE[tier]
            drivers.append(f"estimated telemetry ({station.source}); conservative escalation")

        lead_time = self._lead_time_hours(level, flood, rate, ground_elevation_m, station)
        score = _TIER_SCORE[tier]
        if rain48 is not None and rain48 >= RAIN_HEAVY_48H_MM:
            score = min(100, score + 5)

        return CommuneRisk(
            commune_code=commune.code,
            commune_name_kh=commune.name_kh,
            commune_name_en=commune.name_en,
            province=commune.province_en,
            lat=commune.lat,
            lng=commune.lng,
            tier=tier,
            score=score,
            reason=reason,
            lead_time_hours=lead_time,
            drivers=drivers,
            station_id=station.station_id,
            station_level_m=level,
            estimated=station.is_stale_fallback or station.source == "cache",
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _lead_time_hours(
        level: float,
        flood: float,
        rate: float,
        ground_elevation_m: float | None,
        station: StationSnapshot,
    ) -> int | None:
        if level >= flood:
            return 0
        if rate <= 0.005:
            return None  # receding or flat: no meaningful arrival estimate
        hours_stage = (flood - level) / rate
        zero = _zero_gauge_elevation(station)
        if ground_elevation_m is not None and zero is not None:
            head = ground_elevation_m - (level + zero)
            if head <= 0:
                return 0
            hours = min(hours_stage, head / rate)
        else:
            hours = hours_stage
        return max(1, min(120, int(round(hours))))


_ZERO_GAUGE: dict[str, float] = {
    # MRC FFW-bulletin gauge zero elevations (m MSL); stations without a
    # published datum fall back to stage-only rules.
    "020102": 0.08,
    "033401": -1.02,
    "033402": -1.00,
}


def _zero_gauge_elevation(station: StationSnapshot) -> float | None:
    return _ZERO_GAUGE.get(station.station_id)


def classify_batch(
    communes: list[Commune],
    station: StationSnapshot,
    weather_by_province: dict[str, WeatherSnapshot],
    classifier: SpatialRiskClassifier | None = None,
) -> list[CommuneRisk]:
    engine = classifier or SpatialRiskClassifier()
    out: list[CommuneRisk] = []
    for c in communes:
        weather = weather_by_province.get(c.province_code or "")
        out.append(engine.classify(c, station, weather))
    return out
