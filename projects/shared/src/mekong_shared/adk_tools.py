"""Advisor tool registry (FR-08, Slice 5.1).

Plain async methods carrying tool descriptions, consumed both by the
google-genai function-calling loop and by Google ADK when available. Every
tool returns a JSON-serializable dict and degrades with {"error": ...} instead
of raising, so the LLM can recover conversationally.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from .agronomy import primary_directive
from .models import CommuneRisk, CropStage
from .mrc import MRCTelemetryError
from .pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline
from .spatial import OutsideBasinError
from .stations import load_stations

log = logging.getLogger("mekongpulse.advisor")

TELEGRAM_MESSAGE_LIMIT = 4096

ChannelPublisher = Callable[[str], Awaitable[dict]]


class AdvisorToolContext:
    """Holds the per-request dependencies injected into every tool call.

    `authorized` gates the publish action (the officer token); `publisher` is
    the async callable that posts to the public Telegram channel. Both are
    optional so existing constructions with just a pipeline keep working.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        *,
        authorized: bool = False,
        publisher: ChannelPublisher | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.repo = pipeline.repo
        self.authorized = authorized
        self.publisher = publisher

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
    "get_commune_evidence": (
        "Get the compact evidence pack behind a commune's risk row: data confidence, "
        "telemetry freshness, QC summary, and the evidence chain. Call it before "
        "reporting a tier to an official; treat missing evidence as unknown."
    ),
    "draft_status_update": (
        "Draft a deterministic bilingual (Khmer/English) official status update for the "
        "given commune codes from stored risk rows only. No invented readings. Draft "
        "first; publish only when the officer explicitly asks."
    ),
    "publish_to_channel": (
        "ACTION: post a bilingual update to the public Telegram channel (Khmer text "
        "required, English optional). Requires officer authorization; publish only after "
        "drafting with draft_status_update and only when the officer asks."
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
    {
        "name": "get_commune_evidence",
        "description": TOOL_DESCRIPTIONS["get_commune_evidence"],
        "parameters": {
            "type": "object",
            "properties": {
                "commune_id": {"type": "string", "description": "MEF commune code, e.g. 080404"}
            },
            "required": ["commune_id"],
        },
    },
    {
        "name": "draft_status_update",
        "description": TOOL_DESCRIPTIONS["draft_status_update"],
        "parameters": {
            "type": "object",
            "properties": {
                "commune_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "MEF commune codes to include, e.g. [\"080404\"]",
                },
                "locale": {
                    "type": "string",
                    "enum": ["km", "en"],
                    "description": "Primary audience language (both texts are returned)",
                },
            },
            "required": ["commune_ids"],
        },
    },
    {
        "name": "publish_to_channel",
        "description": TOOL_DESCRIPTIONS["publish_to_channel"],
        "parameters": {
            "type": "object",
            "properties": {
                "khmer_text": {"type": "string", "description": "Khmer message to publish"},
                "english_text": {
                    "type": "string",
                    "description": "Optional English message appended below the Khmer text",
                },
            },
            "required": ["khmer_text"],
        },
    },
]


def _status_line_kh(risk: CommuneRisk) -> str:
    province = f", {risk.province}" if risk.province else ""
    lead = (
        f" — ប្រហែល {risk.lead_time_hours} ម៉ោងទៀត"
        if risk.lead_time_hours is not None
        else ""
    )
    return (
        f"• {risk.commune_name_kh} ({risk.commune_code}{province}): "
        f"{risk.tier.emoji} {risk.tier.label_kh}{lead}"
    )


def _status_line_en(risk: CommuneRisk) -> str:
    province = f", {risk.province}" if risk.province else ""
    lead = (
        f" — ~{risk.lead_time_hours}h to flooding"
        if risk.lead_time_hours is not None
        else ""
    )
    return (
        f"• {risk.commune_name_en} ({risk.commune_code}{province}): "
        f"{risk.tier.emoji} {risk.tier.label_en}{lead}"
    )


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

    async def get_commune_evidence(self, commune_id: str) -> dict:
        """Compact evidence pack for a commune (confidence, freshness, QC, chain).

        `mekong_shared.evidence` is optional at runtime (added by a separate
        workstream): the import is lazy and a missing module degrades to an
        {"error": ...} payload the LLM can recover from.
        """
        try:
            from mekong_shared.evidence import build_evidence
        except Exception as exc:  # noqa: BLE001 - evidence module is optional
            return {"error": f"evidence module unavailable: {exc}"}
        try:
            payload = build_evidence(self._ctx.pipeline, commune_id)
            if inspect.isawaitable(payload):
                payload = await payload
        except Exception as exc:  # noqa: BLE001 - tool contract: never raise
            return {"error": f"evidence unavailable: {exc}"}
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        if not isinstance(payload, dict):
            return {"error": "evidence module returned an unsupported payload type"}
        return payload

    async def draft_status_update(self, commune_ids: list[str], locale: str = "km") -> dict:
        """Deterministic bilingual official status text from stored risk rows.

        Same data source as the risk-map endpoint (`repo.risk_map()`); templates
        only, no LLM and no invented readings. Unknown commune codes produce an
        explicit error line in both languages.
        """
        risks = {risk.commune_code: risk for risk in await self._ctx.repo.risk_map()}
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        khmer = [f"📣 ស្ថានភាពទឹក និងហានិភ័យ — {stamp}"]
        english = [f"📣 Water and flood status — {stamp}"]
        requested = [str(code) for code in (commune_ids or [])]
        if not requested:
            khmer.append("⚠️ គ្មានឃុំត្រូវបានស្នើទេ")
            english.append("⚠️ No commune ids provided")
        seen: set[str] = set()
        for commune_id in requested:
            if commune_id in seen:
                continue
            seen.add(commune_id)
            risk = risks.get(commune_id)
            if risk is None:
                khmer.append(f"⚠️ មិនមានទិន្នន័យហានិភ័យសម្រាប់ឃុំ {commune_id}")
                english.append(f"⚠️ No stored risk data for commune {commune_id}")
                continue
            khmer.append(_status_line_kh(risk))
            english.append(_status_line_en(risk))
        khmer.append(f"🗺 ផែនទី: {self._ctx.pipeline.settings.web_base_url}")
        english.append(f"🗺 Dashboard: {self._ctx.pipeline.settings.web_base_url}")
        return {"khmer": "\n".join(khmer), "english": "\n".join(english)}

    async def publish_to_channel(self, khmer_text: str, english_text: str | None = None) -> dict:
        """ACTION: post a bilingual update to the public Telegram channel.

        Result statuses: denied (no officer authorization), unavailable (no
        publisher wired), posted, or error with a detail.
        """
        if not self._ctx.authorized:
            return {"status": "denied", "detail": "Officer authorization required"}
        if self._ctx.publisher is None:
            return {"status": "unavailable"}
        text = str(khmer_text or "").strip()
        if english_text and str(english_text).strip():
            text = f"{text}\n\n{str(english_text).strip()}"
        text = text[:TELEGRAM_MESSAGE_LIMIT]
        if not text:
            return {"status": "error", "detail": "empty message"}
        try:
            result = await self._ctx.publisher(text)
        except Exception as exc:  # noqa: BLE001 - action failures are values, not exceptions
            return {"status": "error", "detail": str(exc)}
        if isinstance(result, dict) and (result.get("status") == "error" or "error" in result):
            return {"status": "error", "detail": str(result.get("detail") or result.get("error"))}
        return {"status": "posted"}
