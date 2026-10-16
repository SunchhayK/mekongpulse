"""RFC 9457 ProblemDetails error contract.

Every error leaves the API as `application/problem+json` with a stable `type`
URI, a `status`, a human `detail`, and the request `trace_id` for correlation.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from mekong_shared.mrc import MRCTelemetryError
from mekong_shared.pipeline import AssessmentUnavailable, CommuneNotFound
from mekong_shared.spatial import OutsideBasinError

log = logging.getLogger("mekongpulse.backend")

PROBLEM_BASE = "https://mekongpulse.app/problems"


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    trace_id: str | None = None


def problem(
    status: int,
    title: str,
    detail: str | None,
    *,
    type_suffix: str = "about:blank",
    trace_id: str | None = None,
) -> JSONResponse:
    type_uri = (
        type_suffix if type_suffix.startswith("http") else f"{PROBLEM_BASE}/{type_suffix}"
    )
    body = ProblemDetail(
        type=type_uri, title=title, status=status, detail=detail, trace_id=trace_id
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _trace_id(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CommuneNotFound)
    async def _commune_not_found(request: Request, exc: CommuneNotFound):
        return problem(
            404, "Commune not found", str(exc), type_suffix="not-found", trace_id=_trace_id(request)
        )

    @app.exception_handler(AssessmentUnavailable)
    async def _assessment_unavailable(request: Request, exc: AssessmentUnavailable):
        return problem(
            409,
            "Assessment unavailable for this commune",
            str(exc),
            type_suffix="assessment-unavailable",
            trace_id=_trace_id(request),
        )

    @app.exception_handler(OutsideBasinError)
    async def _outside_basin(request: Request, exc: OutsideBasinError):
        return problem(
            422,
            "Location outside the monitored basin",
            str(exc),
            type_suffix="outside-basin",
            trace_id=_trace_id(request),
        )

    @app.exception_handler(MRCTelemetryError)
    async def _telemetry_error(request: Request, exc: MRCTelemetryError):
        return problem(
            502,
            "Upstream telemetry unavailable",
            str(exc),
            type_suffix="telemetry-unavailable",
            trace_id=_trace_id(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):
        title = HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus._value2member_map_ else "HTTP error"
        return problem(
            exc.status_code, title, str(exc.detail), type_suffix="http-error", trace_id=_trace_id(request)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return problem(
            422,
            "Request validation failed",
            "; ".join(str(e.get("msg")) for e in exc.errors()[:3]),
            type_suffix="validation-error",
            trace_id=_trace_id(request),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return problem(
            500,
            "Internal server error",
            type(exc).__name__,
            type_suffix="internal-error",
            trace_id=_trace_id(request),
        )
