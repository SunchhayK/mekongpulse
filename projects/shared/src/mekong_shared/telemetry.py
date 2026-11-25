"""OpenTelemetry tracing and structured Cloud Monitoring SLO emitters (IMP-08).

Provides zero-overhead no-op behavior when tracing is disabled or OpenTelemetry
packages are not installed, while wiring OTLP / Cloud Trace exporters and FastAPI
instrumentation when configured.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from .config import Settings
from .logging_utils import log_event

log = logging.getLogger("mekongpulse.telemetry")

_TRACING_CONFIGURED = False


class _NoOpSpan:
    """Zero-overhead fallback span when OpenTelemetry is disabled or absent."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        return None

    def record_exception(self, exception: BaseException) -> None:
        return None


def configure_tracing(app: Any, settings: Settings, *, service_name: str = "mekongpulse") -> bool:
    """Configure OpenTelemetry tracing for FastAPI / Cloud Trace / OTLP.

    Returns True if an OTel exporter was configured, False when disabled or
    when optional opentelemetry packages are not installed.
    """
    global _TRACING_CONFIGURED

    enable_cloud_trace = bool(getattr(settings, "enable_cloud_trace", False))
    otlp_endpoint = getattr(settings, "otel_exporter_otlp_endpoint", None)
    if not enable_cloud_trace and not otlp_endpoint:
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log_event(
            log,
            "OTEL_UNAVAILABLE",
            detail="opentelemetry-sdk not installed; tracing disabled",
        )
        return False

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter_added = False

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
            exporter_added = True
        except ImportError:
            log_event(
                log,
                "OTEL_EXPORTER_UNAVAILABLE",
                exporter="otlp",
                endpoint=otlp_endpoint,
            )

    if enable_cloud_trace:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
            exporter_added = True
        except ImportError:
            log_event(
                log,
                "OTEL_EXPORTER_UNAVAILABLE",
                exporter="cloud_trace",
            )

    if not exporter_added:
        return False

    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    _TRACING_CONFIGURED = True
    log_event(
        log,
        "OTEL_CONFIGURED",
        service=service_name,
        cloud_trace=enable_cloud_trace,
        otlp=bool(otlp_endpoint),
    )
    return True


@contextmanager
def traced_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Context manager creating an OTel span when active, or a no-op otherwise."""
    if not _TRACING_CONFIGURED:
        yield _NoOpSpan()
        return

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("mekongpulse")
    except Exception:  # noqa: BLE001 - tracing must never break business logic
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span


# --- Structured SLO / Cloud Monitoring log-based metric emitters -------------

def emit_slo_event(
    event: str,
    *,
    logger: logging.Logger | None = None,
    metric_type: str | None = None,
    **fields: object,
) -> None:
    """Emit a structured Cloud Logging event formatted for log-based metrics."""
    target = logger or log
    payload: dict[str, object] = dict(fields)
    if metric_type:
        payload["metric_type"] = metric_type
    log_event(target, event, **payload)


def emit_mrc_station_timeout(station_id: str, error: str) -> None:
    emit_slo_event(
        "MRC_STATION_TIMEOUT",
        metric_type="custom.googleapis.com/mekongpulse/mrc_station_timeout",
        station_id=station_id,
        error=error,
    )


def emit_watch_publish_failed(run_id: str, commune_code: str, error: str) -> None:
    emit_slo_event(
        "WATCH_PUBLISH_FAILED",
        metric_type="custom.googleapis.com/mekongpulse/watch_publish_failed",
        run_id=run_id,
        commune_code=commune_code,
        error=error,
    )


def emit_tts_unavailable(commune_code: str, error: str) -> None:
    emit_slo_event(
        "TTS_UNAVAILABLE",
        metric_type="custom.googleapis.com/mekongpulse/tts_unavailable",
        commune_code=commune_code,
        error=error,
    )


def emit_telemetry_warning(station_id: str, kind: str, detail: str) -> None:
    emit_slo_event(
        "TELEMETRY_WARNING",
        metric_type="custom.googleapis.com/mekongpulse/telemetry_warning",
        station_id=station_id,
        warning_kind=kind,
        detail=detail,
    )


def emit_gauge_failover(station_id: str, source: str, fallback_id: str | None = None) -> None:
    emit_slo_event(
        "GAUGE_FAILOVER",
        metric_type="custom.googleapis.com/mekongpulse/gauge_failover",
        station_id=station_id,
        source=source,
        fallback_id=fallback_id,
    )
