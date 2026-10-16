"""Commune endpoints: risk map, GPS resolve, search, on-demand assessment."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mekong_shared.logging_utils import log_event
from mekong_shared.models import AssessmentResult, CommuneRisk, CropStage
from mekong_shared.pipeline import CommuneNotFound

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/communes", tags=["communes"])


class AssessRequest(BaseModel):
    crop_stage: CropStage = CropStage.RIPENING
    with_audio: bool = False


class CommuneSummary(BaseModel):
    commune_code: str
    name_kh: str
    name_en: str
    district_en: str | None = None
    province_en: str | None = None
    lat: float | None = None
    lng: float | None = None
    has_boundary: bool = False


@router.get("/risk-map")
async def risk_map(request: Request, province: str | None = None) -> list[CommuneRisk]:
    repo = request.app.state.repo
    return await repo.risk_map(province)


@router.get("/resolve")
async def resolve(request: Request, lat: float, lng: float) -> dict:
    """GPS pin -> commune. Outside-basin pins raise a 422 ProblemDetails."""
    gazetteer = request.app.state.pipeline.gazetteer
    resolved = gazetteer.resolve(lat, lng)
    commune = resolved.commune
    return {
        "commune_code": commune.code,
        "name_kh": commune.name_kh,
        "name_en": commune.name_en,
        "district_en": commune.district_en,
        "province_en": commune.province_en,
        "nearest_station_id": commune.nearest_station_id,
        "lat": commune.lat,
        "lng": commune.lng,
        "method": resolved.method,
    }


@router.get("/search")
async def search(request: Request, q: str, limit: int = 10) -> list[CommuneSummary]:
    gazetteer = request.app.state.pipeline.gazetteer
    hits = gazetteer.search(q, limit=max(1, min(limit, 50)))
    return [
        CommuneSummary(
            commune_code=c.code,
            name_kh=c.name_kh,
            name_en=c.name_en,
            district_en=c.district_en,
            province_en=c.province_en,
            lat=c.lat,
            lng=c.lng,
            has_boundary=c.has_boundary,
        )
        for c in hits
    ]


@router.post("/{commune_code}/assess")
async def assess(commune_code: str, body: AssessRequest, request: Request) -> AssessmentResult:
    pipeline = request.app.state.pipeline
    result = await pipeline.assess_commune(
        commune_code, body.crop_stage, with_audio=body.with_audio
    )
    log_event(
        log,
        "ASSESSMENT_GENERATED",
        trace_id=getattr(request.state, "trace_id", None),
        commune=commune_code,
        tier=result.risk_tier.value,
        directive=result.directive,
        crop_stage=body.crop_stage.value,
    )
    return result


@router.get("/{commune_code}")
async def commune_detail(commune_code: str, request: Request) -> CommuneSummary:
    repo = request.app.state.repo
    commune = await repo.get_commune(commune_code)
    if commune is None:
        raise CommuneNotFound(commune_code)
    return CommuneSummary(
        commune_code=commune.code,
        name_kh=commune.name_kh,
        name_en=commune.name_en,
        district_en=commune.district_en,
        province_en=commune.province_en,
        lat=commune.lat,
        lng=commune.lng,
        has_boundary=commune.has_boundary,
    )
