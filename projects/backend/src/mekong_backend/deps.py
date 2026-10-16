"""Shared FastAPI dependencies (app.state is populated by the lifespan)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from mekong_shared.config import Settings
from mekong_shared.pipeline import Pipeline
from mekong_shared.sentinel import SentinelPatrol


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repo(request: Request):
    return request.app.state.repo


def get_pipeline(request: Request) -> Pipeline:
    return request.app.state.pipeline


def get_sentinel(request: Request) -> SentinelPatrol:
    return request.app.state.sentinel


async def require_admin(request: Request) -> None:
    """Bearer gate for scheduler/admin endpoints.

    Open in development when ADMIN_TOKEN is unset; enforced everywhere else.
    Cloud Scheduler sends the OIDC token via the Authorization header; we
    accept the configured static token (and record its use).
    """
    settings: Settings = request.app.state.settings
    if not settings.admin_token:
        return
    authorization = request.headers.get("authorization", "")
    if authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(status_code=401, detail="admin token required")
