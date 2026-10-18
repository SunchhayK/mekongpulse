"""FastAPI application factory (TRD §2.2 presentation layer).

Wires settings, repository, pipeline, sentinel, and (when a token is present)
the Telegram webhook application. Everything heavy is injectable so tests can
run offline against the in-memory repository and mock transports.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mekong_shared.config import Settings, get_settings
from mekong_shared.logging_utils import configure_logging, log_event
from mekong_shared.pipeline import Pipeline
from mekong_shared.repository import create_audio_store, create_repository
from mekong_shared.security import new_trace_id, parse_traceparent
from mekong_shared.sentinel import SentinelPatrol

from .problems import register_exception_handlers
from .routers import (
    alerts,
    communes,
    health,
    officer,
    patrol,
    subscriptions,
    telegram,
    telemetry,
    watch,
)

log = logging.getLogger("mekongpulse.backend")


def create_app(
    *,
    settings: Settings | None = None,
    repo=None,
    pipeline: Pipeline | None = None,
    telegram_app=None,
) -> FastAPI:
    app_settings = settings or get_settings()
    logger = configure_logging("mekong-backend")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        repository = repo or create_repository(app_settings)
        await repository.init()
        app.state.repo = repository

        pl = pipeline
        if pl is None:
            pl = Pipeline(
                settings=app_settings,
                repo=repository,
                audio_store=create_audio_store(app_settings),
            )
        app.state.pipeline = pl
        await pl.ensure_seeded()

        tg = telegram_app
        if tg is None and app_settings.has_telegram:
            try:
                from mekong_bot.app import build_application

                tg = build_application(app_settings, pipeline=pl, repo=repository)
                if tg is not None:
                    await tg.initialize()
            except Exception as exc:  # noqa: BLE001 - bot is optional at runtime
                log_event(logger, "TELEGRAM_INIT_FAILED", error=str(exc))
                tg = None
        app.state.telegram_app = tg

        dispatcher = None
        if tg is not None:
            try:
                from mekong_bot.dispatcher import make_telegram_dispatcher

                dispatcher = make_telegram_dispatcher(pl, tg.bot)
            except Exception as exc:  # noqa: BLE001
                log_event(logger, "DISPATCHER_INIT_FAILED", error=str(exc))
        app.state.sentinel = SentinelPatrol(pl, settings=app_settings, dispatcher=dispatcher)

        log_event(
            logger,
            "BACKEND_STARTED",
            environment=app_settings.environment,
            repository=app_settings.repository_backend or "auto",
        )
        try:
            yield
        finally:
            if tg is not None:
                try:
                    await tg.shutdown()
                except Exception:  # noqa: BLE001
                    pass
            await repository.close()

    app = FastAPI(title="MekongPulse API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = parse_traceparent(request.headers.get("traceparent")) or new_trace_id()
        request.state.trace_id = trace_id
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - started) * 1000)
        response.headers["traceparent"] = (
            f"00-{trace_id}-{new_trace_id()[:16]}-01"
        )
        if request.url.path.startswith("/api/"):
            log_event(
                logger,
                "HTTP_REQUEST",
                trace_id=trace_id,
                duration_ms=duration_ms,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
        return response

    app.include_router(health.router)
    app.include_router(telemetry.router)
    app.include_router(communes.router)
    app.include_router(subscriptions.router)
    app.include_router(patrol.router)
    app.include_router(alerts.router)
    app.include_router(telegram.router)
    app.include_router(officer.router)
    app.include_router(watch.router)

    if not app_settings.is_production:
        app_settings.audio_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/audio", StaticFiles(directory=str(app_settings.audio_dir)), name="audio")

    return app
