"""Commune endpoints: risk map, GPS resolve, search, on-demand assessment,
evidence payloads, and ground-truth field reports."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mekong_shared.evidence import EvidencePayload, build_evidence
from mekong_shared.logging_utils import log_event
from mekong_shared.models import (
    AssessmentResult,
    CommuneRisk,
    CropStage,
    FieldReport,
    FieldReportStatus,
)
from mekong_shared.pipeline import CommuneNotFound

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/communes", tags=["communes"])


class AssessRequest(BaseModel):
    crop_stage: CropStage = CropStage.RIPENING
    with_audio: bool = False


class FieldReportCreate(BaseModel):
    status: FieldReportStatus
    note: str | None = None
    reporter_label: str | None = None


class FieldReportList(BaseModel):
    reports: list[FieldReport]


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


@router.get("/{commune_code}/evidence")
async def evidence(commune_code: str, request: Request) -> EvidencePayload:
    """Deterministic provenance for the commune's current risk (no field reports here)."""
    pipeline = request.app.state.pipeline
    payload = await build_evidence(pipeline, commune_code)
    log_event(
        log,
        "EVIDENCE_BUILT",
        trace_id=getattr(request.state, "trace_id", None),
        commune=commune_code,
        tier=payload.risk_tier.value,
        confidence=payload.confidence,
    )
    return payload


@router.post("/{commune_code}/reports", status_code=201)
async def create_field_report(
    commune_code: str, body: FieldReportCreate, request: Request
) -> FieldReport:
    """Ground truth from officials: did water reach the fields in this commune?"""
    repo = request.app.state.repo
    commune = await repo.get_commune(commune_code)
    if commune is None:
        raise CommuneNotFound(commune_code)
    report = FieldReport(
        id=uuid4().hex,
        commune_code=commune_code,
        status=body.status,
        note=body.note,
        reporter_label=body.reporter_label,
        source="web",
        reported_at=datetime.now(timezone.utc),
    )
    saved = await repo.add_field_report(report)
    log_event(
        log,
        "FIELD_REPORT_ADDED",
        trace_id=getattr(request.state, "trace_id", None),
        commune=commune_code,
        status=body.status.value,
    )
    return saved


@router.get("/{commune_code}/reports")
async def list_field_reports(
    commune_code: str, request: Request, limit: int = 20
) -> FieldReportList:
    repo = request.app.state.repo
    reports = await repo.list_field_reports(commune_code, limit=max(1, min(limit, 100)))
    return FieldReportList(reports=reports)


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
