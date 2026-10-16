"""Security helpers: hashing, anonymization, W3C trace correlation.

TRD §1.5: subscriber identifiers and GPS coordinates are SHA-256 salted before
persistent logging. TRD §1.6: traceparent context is propagated for
correlation; we carry the trace id through structured logs instead of a full
OpenTelemetry SDK.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid

_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-(?P<trace_id>[0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$"
)


def sha256_hex(value: str | int | float, salt: str) -> str:
    """Salted SHA-256 hex digest for anonymized identifiers / coordinates."""
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


def anonymize_location(lat: float, lng: float, salt: str) -> str:
    # Coordinates rounded to ~1.1 km before hashing: log-friendly, not reversible.
    return sha256_hex(f"{round(lat, 2)}:{round(lng, 2)}", salt)[:16]


def anonymize_chat_id(chat_id: int | str, salt: str) -> str:
    return sha256_hex(str(chat_id), salt)[:16]


def parse_traceparent(header: str | None) -> str | None:
    """Extract the W3C trace id from a traceparent header, when valid."""
    if not header:
        return None
    match = _TRACEPARENT_RE.match(header.strip().lower())
    return match.group("trace_id") if match else None


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_traceparent() -> str:
    """A fresh, valid traceparent for outbound synthetic traces (tests)."""
    return f"00-{new_trace_id()}-{os.urandom(8).hex()}-01"
