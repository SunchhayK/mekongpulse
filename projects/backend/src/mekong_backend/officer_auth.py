"""Officer sign-in: passcode -> short-lived signed session (stdlib only).

The browser never receives the admin token. `POST /api/v1/officer/login`
exchanges the officer passcode (OFFICER_PASSCODE, falling back to ADMIN_TOKEN
for single-secret deployments) for a stateless session token

    v1.<exp_unix>.<hmac_sha256_hex(key=ADMIN_TOKEN, msg="v1."+exp_unix)>

Advisor calls then authenticate with `Authorization: Bearer <session>`; the
legacy `X-Officer-Token` header keeps working for scripts. Every comparison
against a secret goes through `hmac.compare_digest`.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Mapping

from mekong_shared.config import Settings

SESSION_VERSION = "v1"
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60.0


class SignInUnavailable(Exception):
    """Raised when sessions cannot be issued (ADMIN_TOKEN, the signing key, is unset)."""


def effective_passcode(settings: Settings) -> str | None:
    """Passcode the officer types in the browser; falls back to the admin token."""
    return settings.officer_passcode or settings.admin_token


def sign_in_configured(settings: Settings) -> bool:
    """Sign-in needs a passcode to check and ADMIN_TOKEN as the session signing key."""
    return bool(effective_passcode(settings) and settings.admin_token)


def passcode_matches(settings: Settings, candidate: str) -> bool:
    expected = effective_passcode(settings)
    if expected is None:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def _signing_key(settings: Settings) -> str:
    if not settings.admin_token:
        raise SignInUnavailable("ADMIN_TOKEN is not configured")
    return settings.admin_token


def _signature(key: str, payload: str) -> str:
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_session(settings: Settings) -> tuple[str, datetime]:
    """Mint a session token and its expiry. Raises SignInUnavailable without ADMIN_TOKEN."""
    key = _signing_key(settings)
    expires_at_epoch = int(time.time()) + settings.officer_session_ttl_hours * 3600
    payload = f"{SESSION_VERSION}.{expires_at_epoch}"
    token = f"{payload}.{_signature(key, payload)}"
    return token, datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc)


def verify_session(settings: Settings, token: str | None) -> bool:
    """True when `token` has the pinned format, a valid signature, and is unexpired."""
    if not token or not settings.admin_token:
        return False
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != SESSION_VERSION or not parts[1].isdigit():
        return False
    expected = _signature(settings.admin_token, f"{SESSION_VERSION}.{parts[1]}")
    return hmac.compare_digest(expected.encode(), parts[2].encode()) and int(parts[1]) > int(
        time.time()
    )


def authorized_for(settings: Settings, headers: Mapping[str, str]) -> bool:
    """Legacy `X-Officer-Token` header or `Authorization: Bearer <session>`.

    Starlette Headers are case-insensitive; normalizing keeps plain dicts working too.
    """
    lowered = {name.lower(): value for name, value in headers.items()}
    legacy = lowered.get("x-officer-token")
    if legacy is not None and settings.admin_token is not None:
        if hmac.compare_digest(legacy.encode(), settings.admin_token.encode()):
            return True
    scheme, _, credential = lowered.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return verify_session(settings, credential.strip())


class PasscodeRateLimiter:
    """Tiny in-process per-client-IP failure window (single worker in staging).

    After `max_failures` failures within `window_seconds` the IP is locked out
    until the oldest failure ages out; a successful sign-in resets the count.
    """

    def __init__(
        self,
        *,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
    ) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, client_ip: str, now: float) -> list[float]:
        cutoff = now - self._window_seconds
        recent = [stamp for stamp in self._failures.get(client_ip, []) if stamp > cutoff]
        if recent:
            self._failures[client_ip] = recent
        else:
            self._failures.pop(client_ip, None)
        return recent

    def blocked(self, client_ip: str) -> bool:
        return len(self._recent(client_ip, time.monotonic())) >= self._max_failures

    def record_failure(self, client_ip: str) -> None:
        now = time.monotonic()
        self._failures[client_ip] = self._recent(client_ip, now) + [now]

    def reset(self, client_ip: str) -> None:
        self._failures.pop(client_ip, None)
