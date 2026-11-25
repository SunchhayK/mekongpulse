"""Ground-truth verification and per-commune threshold calibration API (IMP-07)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from mekong_shared.logging_utils import log_event
from mekong_shared.models import VerificationSummary
from mekong_shared.verification import (
    calibrate_commune_thresholds,
    compute_verification_summary,
)

from ..deps import require_admin
from ..officer_auth import resolve_officer_identity

log = logging.getLogger("mekongpulse.backend")

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


async def _require_officer_or_admin(request: Request) -> None:
    """Allow either an authenticated officer or an admin/OIDC caller."""
    settings = request.app.state.settings
    identity = await resolve_officer_identity(
        settings,
        request.headers,
        firebase_verifier=getattr(request.app.state, "firebase_verifier", None),
    )
    if identity is not None:
        return
    try:
        await require_admin(request)
    except HTTPException as exc:
        raise HTTPException(
            status_code=401, detail="officer or admin authorization required"
        ) from exc


@router.get("/verification")
async def get_verification(
    request: Request,
    limit: int = 500,
    match_window_hours: float = 72.0,
) -> VerificationSummary:
    """Return alert-vs-field-report verification summary (precision, recall, lead-time error)."""
    await _require_officer_or_admin(request)
    repo = request.app.state.repo
    clamped = max(1, min(limit, 2000))
    alerts = await repo.recent_sentinel_alerts(limit=clamped)
    reports = await repo.list_field_reports(None, limit=clamped)
    return compute_verification_summary(
        alerts,
        reports,
        match_window_hours=max(1.0, min(match_window_hours, 240.0)),
    )


@router.post("/calibrate")
async def run_calibration(
    request: Request,
    limit: int = 1000,
    match_window_hours: float = 72.0,
) -> dict:
    """Compute and persist per-commune levee_margin_m and lead_time_multiplier calibrations."""
    await _require_officer_or_admin(request)
    repo = request.app.state.repo
    clamped = max(1, min(limit, 5000))
    alerts = await repo.recent_sentinel_alerts(limit=clamped)
    reports = await repo.list_field_reports(None, limit=clamped)
    existing = await repo.list_commune_calibrations()

    calibrations = calibrate_commune_thresholds(
        alerts,
        reports,
        existing=existing,
        match_window_hours=max(1.0, min(match_window_hours, 240.0)),
    )
    for cal in calibrations:
        await repo.save_commune_calibration(cal)

    log_event(
        log,
        "CALIBRATION_UPDATED",
        trace_id=getattr(request.state, "trace_id", None),
        calibrated=len(calibrations),
    )
    return {
        "calibrated": len(calibrations),
        "calibrations": [cal.model_dump(mode="json") for cal in calibrations],
    }
