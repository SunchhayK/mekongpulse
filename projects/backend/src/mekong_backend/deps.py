"""Shared FastAPI dependencies (app.state is populated by the lifespan)."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from mekong_shared.config import Settings
from mekong_shared.pipeline import Pipeline
from mekong_shared.sentinel import SentinelPatrol

from .officer_auth import EndpointRateLimiter, verify_oidc_token


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repo(request: Request):
    return request.app.state.repo


def get_pipeline(request: Request) -> Pipeline:
    return request.app.state.pipeline


def get_sentinel(request: Request) -> SentinelPatrol:
    return request.app.state.sentinel


def get_state_store(request: Request):
    return getattr(request.app.state, "state_store", None)


def get_task_queue(request: Request):
    return getattr(request.app.state, "task_queue", None)


def get_endpoint_limiter(request: Request) -> EndpointRateLimiter:
    limiter = getattr(request.app.state, "endpoint_limiter", None)
    if limiter is None:
        limiter = EndpointRateLimiter(state_store=get_state_store(request))
        request.app.state.endpoint_limiter = limiter
    return limiter


def client_ip_for(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def require_admin(request: Request) -> None:
    """Bearer gate for scheduler/admin endpoints.

    Open in development when neither ADMIN_TOKEN nor OIDC audience/service account
    is configured; enforced everywhere else. Accepts either the configured static
    ADMIN_TOKEN or a verified Cloud Scheduler OIDC bearer token.
    """
    settings: Settings = request.app.state.settings
    oidc_audience = getattr(settings, "oidc_audience", None)
    scheduler_sa = getattr(settings, "scheduler_service_account_email", None)
    oidc_verifier = getattr(request.app.state, "oidc_verifier", None)
    oidc_enabled = bool(oidc_audience or scheduler_sa or oidc_verifier is not None)

    if not settings.admin_token and not oidc_enabled:
        return

    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")
    token = credential.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="admin token required")

    if settings.admin_token and hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        return

    if oidc_enabled:
        claims = await verify_oidc_token(settings, token, verifier=oidc_verifier)
        if claims is not None:
            request.state.oidc_claims = claims
            return

    raise HTTPException(status_code=401, detail="admin token required")
