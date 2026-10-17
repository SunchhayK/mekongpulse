"""Structured JSON logging (TRD §1.6).

Every service emits one JSON object per line with timestamp, level, service,
event, optional trace_id (from the W3C traceparent context), and extra fields.
No OTel SDK: trace ids flow through HTTP headers and are attached to log
records, which is what Cloud Logging needs for correlation.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "service": getattr(record, "service", "mekongpulse"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("event", "trace_id", "duration_ms"):
            value = record.__dict__.get(key)
            if value is not None:
                payload[key] = value
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str, level: int = logging.INFO) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logger = logging.getLogger("mekongpulse")
    logger.setLevel(level)
    # httpx logs full request URLs at INFO. Telegram API URLs embed the bot
    # token (`/bot<token>/getMe`), so keep transport loggers out of the logs;
    # warnings and errors still surface.
    for transport_logger in ("httpx", "httpcore"):
        logging.getLogger(transport_logger).setLevel(logging.WARNING)
    # Make `service` visible on every record.
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):  # noqa: ANN002, ANN003 - logging hook
        record = old_factory(*args, **kwargs)
        record.service = service
        return record

    logging.setLogRecordFactory(factory)
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    trace_id: str | None = None,
    duration_ms: int | None = None,
    **fields: object,
) -> None:
    """Emit one structured event line."""
    logger.info(
        event,
        extra={"event": event, "trace_id": trace_id, "duration_ms": duration_ms, "fields": fields},
    )
