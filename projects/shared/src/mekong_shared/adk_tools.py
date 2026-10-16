"""Advisor tool registry (FR-08, Slice 5.1).

Plain async methods carrying tool descriptions, consumed both by the
google-genai function-calling loop and by Google ADK when available. Every
tool returns a JSON-serializable dict and degrades with {"error": ...} instead
of raising, so the LLM can recover conversationally.
"""

from __future__ import annotations

import logging

from .agronomy import primary_directive
from .models import CropStage
from .mrc import MRCTelemetryError
from .pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline
from .spatial import OutsideBasinError
from .stations import load_stations

log = logging.getLogger("mekongpulse.advisor")


class AdvisorToolContext:
    """Holds the per-request dependencies injected into every tool call."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.repo = pipeline.repo

    @property
    def gazetteer(self):
        return self.pipeline.gazetteer


TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_station_telemetry": (
        "Get the latest water level, alarm/flood stages, and rate of rise for an MRC "
        "river station. Station ids: 033401 Chaktomuk (Bassac), 033402 Koh Khel (Bassac), "
        "019802 Kompong Cham (Mekong), 020102 Prek Kdam (Tonle Sap)."
    ),
    "resolve_commune_by_location": (
        "Resolve a GPS latitude/longitude to the Cambodian commune (MEF gazetteer) that "
        "contains it. Returns the commune code, names, district, province, and the "
        "resolution method."
    ),
    "search_commune": (
        "Search Cambodian communes by name (Khmer or English), district, or province. "
        "Returns the best matches with commune codes."
    ),
    "evaluate_crop_directive": (
        "Evaluate the flood risk and agronomic directives for a commune given the rice "
        "crop stage (TILLERING, VEGETATIVE, FLOWERING, RIPENING). Returns the risk tier, "
        "estimated time until water arrival in hours, and ordered field actions."
    ),
    "synthesize_voice_bulletin": (
        "Generate the spoken Khmer voice bulletin (MP3) for a commune. Returns the audio "
        "URL when synthesis is available, else the Khmer bulletin text."
    ),
}

FUNCTION_DECLARATIONS: list[dict] = [
    {
        "name": "get_station_telemetry",
        "description": TOOL_DESCRIPTIONS["get_station_telemetry"],
        "parameters": {
            "type": "object",
            "properties": {
                "station_id": {
                    "type": "string",
                    "description": "MRC station id, e.g. 033401",
                }
            },
            "required": ["station_id"],
        },
    },
    {
        "name": "resolve_commune_by_location",
        "description": TOOL_DESCRIPTIONS["resolve_commune_by_location"],
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "GPS latitude in WGS84"},
                "longitude": {"type": "number", "description": "GPS longitude in WGS84"},
            },
            "required": ["latitude", "longitude"],
        },
    },
    {
        "name": "search_commune",
        "description": TOOL_DESCRIPTIONS["search_commune"],
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Commune/district name"}},
            "required": ["name"],
        },
    },
    {
        "name": "evaluate_crop_directive",
        "description": TOOL_DESCRIPTIONS["evaluate_crop_directive"],
        "parameters": {
            "type": "object",
            "properties": {
                "commune_id": {"type": "string", "description": "MEF commune code, e.g. 080404"},
                "crop_stage": {
                    "type": "string",
                    "enum": [s.value for s in CropStage],
                    "description": "Rice growth stage",
                },
            },
            "required": ["commune_id", "crop_stage"],
        },
    },
    {
        "name": "synthesize_voice_bulletin",
        "description": TOOL_DESCRIPTIONS["synthesize_voice_bulletin"],
        "parameters": {
            "type": "object",
            "properties": {
                "commune_id": {"type": "string", "description": "MEF commune code"}
            },
            "required": ["commune_id"],
        },
    },
]


class AdvisorTools:
    def __init__(self, context: AdvisorToolContext) -> None:
        self._ctx = context

    async def get_station_telemetry(self, station_id: str) -> dict:
        """Latest water level and stages for an MRC station (grounded, INV-01)."""
        stations = load_stations(str(self._ctx.pipeline.settings.data_dir))
        cfg = stations.get(station_id)
        if cfg is None:
            return {
                "error": f"unknown station {station_id}",
                "known_stations": sorted(stations.keys()),
            }
        snapshot = await self._ctx.repo.latest_observation(station_id)
        if snapshot is None:
            try:
                snapshot = await self._ctx.pipeline.mrc.fetch_station(station_id)
                await self._ctx.repo.save_observation(snapshot)
            except MRCTelemetryError as exc:
                return {"error": f"telemetry unavailable: {exc}"}
        return {
            "station_id": snapshot.station_id,
            "name": snapshot.name,
            "river": snapshot.river,
            "water_level_m": snapshot.level_m,
            "alarm_stage_m": snapshot.alarm_stage_m,
            "flood_stage_m": snapshot.flood_stage_m,
            "rate_of_rise_m_per_hr": snapshot.rate_of_rise_m_per_hr,
            "recorded_at": snapshot.recorded_at.isoformat(),
            "estimated": snapshot.is_stale_fallback or snapshot.source == "cache",
            "source": snapshot.source,
            "staleness_minutes": snapshot.staleness_minutes,
        }

    async def resolve_commune_by_location(self, latitude: float, longitude: float) -> dict:
        """Resolve GPS coordinates to a commune via the STRtree gazetteer."""
        try:
            resolved = self._ctx.gazetteer.resolve(float(latitude), float(longitude))
        except OutsideBasinError:
            return {
                "error": "location is outside Cambodia; ask the user for their commune name "
                "and use search_commune instead"
            }
        c = resolved.commune
        return {
            "commune_code": c.code,
            "commune_name_kh": c.name_kh,
            "commune_name_en": c.name_en,
            "district_en": c.district_en,
            "province_en": c.province_en,
            "nearest_station_id": c.nearest_station_id,
            "method": resolved.method,
            "distance_km": resolved.distance_km,
        }

    async def search_commune(self, name: str) -> dict:
        """Search communes by Khmer/English name, district, or province."""
        hits = self._ctx.gazetteer.search(str(name), limit=5)
        return {
            "results": [
                {
                    "commune_code": c.code,
                    "commune_name_kh": c.name_kh,
                    "commune_name_en": c.name_en,
                    "district_en": c.district_en,
                    "province_en": c.province_en,
                }
                for c in hits
            ]
        }

    async def evaluate_crop_directive(self, commune_id: str, crop_stage: str) -> dict:
        """Risk tier + ordered agronomic directives for a commune and crop stage."""
        try:
            stage = CropStage(str(crop_stage).strip().upper())
        except ValueError:
            return {
                "error": f"invalid crop_stage {crop_stage!r}",
                "valid_stages": [s.value for s in CropStage],
            }
        try:
            assessment = await self._ctx.pipeline.assess_commune(commune_id, stage)
        except (CommuneNotFound, AssessmentUnavailable) as exc:
            return {"error": str(exc)}
        primary = primary_directive(assessment.directives)
        return {
            "commune_code": assessment.commune_code,
            "commune_name_kh": assessment.commune_name_kh,
            "commune_name_en": assessment.commune_name_en,
            "risk_tier": assessment.risk_tier.value,
            "risk_score": assessment.score,
            "estimated": assessment.estimated,
            "lead_time_hours": assessment.lead_time_hours,
            "primary_directive": primary.action_code,
            "directives": [
                {
                    "action_code": d.action_code,
                    "title_en": d.title_en,
                    "title_kh": d.title_kh,
                    "urgency": d.urgency.value,
                }
                for d in assessment.directives
            ],
            "khmer_bulletin": assessment.khmer_bulletin,
            "english_bulletin": assessment.english_bulletin,
        }

    async def synthesize_voice_bulletin(self, commune_id: str) -> dict:
        """Spoken Khmer MP3 bulletin for a commune; text when TTS is unavailable."""
        try:
            assessment = await self._ctx.pipeline.assess_commune(
                commune_id, CropStage.RIPENING, with_audio=True
            )
        except (CommuneNotFound, AssessmentUnavailable) as exc:
            return {"error": str(exc)}
        if assessment.audio is not None:
            return {
                "audio_url": assessment.audio.url,
                "duration_seconds": assessment.audio.duration_seconds,
                "risk_tier": assessment.risk_tier.value,
            }
        return {
            "audio_url": None,
            "reason": "voice synthesis unavailable; reply with the Khmer text bulletin",
            "risk_tier": assessment.risk_tier.value,
            "khmer_bulletin": assessment.khmer_bulletin,
        }
