"""Officer sign-in, Firebase ID token auth, Cloud Scheduler OIDC, and rate limiting.

Supports three officer authentication mechanisms:
1. Firebase Authentication ID token (`Authorization: Bearer <firebase_jwt>`) when
   `FIREBASE_PROJECT_ID` (or an injectable verifier) is configured.
2. Stateless HMAC passcode session (`POST /api/v1/officer/login`) returning either:
   - `v1.<exp_unix>.<hmac_sha256_hex>` (anonymous officer session)
   - `v2.<exp_unix>.<b64url_identity>.<hmac_sha256_hex>` (named officer session)
3. Legacy `X-Officer-Token` header for scripts.

Every secret comparison goes through `hmac.compare_digest`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from mekong_shared.config import Settings

log = logging.getLogger("mekongpulse.backend")

SESSION_VERSION = "v1"
NAMED_SESSION_VERSION = "v2"
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60.0
REPORT_DEDUP_WINDOW_SECONDS = 300.0


@dataclass(frozen=True)
class OfficerIdentity:
    subject: str
    email: str | None = None
    auth_method: str = "passcode"

    @property
    def label(self) -> str:
        return self.email or self.subject or "officer"


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


def _b64url_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> str | None:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def issue_session(
    settings: Settings, *, officer_id: str | None = None
) -> tuple[str, datetime]:
    """Mint a session token and its expiry. Raises SignInUnavailable without ADMIN_TOKEN."""
    key = _signing_key(settings)
    expires_at_epoch = int(time.time()) + settings.officer_session_ttl_hours * 3600
    cleaned = (officer_id or "").strip()
    if cleaned:
        encoded_id = _b64url_encode(cleaned[:128])
        payload = f"{NAMED_SESSION_VERSION}.{expires_at_epoch}.{encoded_id}"
    else:
        payload = f"{SESSION_VERSION}.{expires_at_epoch}"
    token = f"{payload}.{_signature(key, payload)}"
    return token, datetime.fromtimestamp(expires_at_epoch, tz=timezone.utc)


def verify_session_identity(settings: Settings, token: str | None) -> OfficerIdentity | None:
    """Return OfficerIdentity when `token` is a valid, unexpired v1 or v2 session."""
    if not token or not settings.admin_token:
        return None
    parts = token.split(".")
    if len(parts) == 3 and parts[0] == SESSION_VERSION and parts[1].isdigit():
        expected = _signature(settings.admin_token, f"{SESSION_VERSION}.{parts[1]}")
        if hmac.compare_digest(expected.encode(), parts[2].encode()) and int(parts[1]) > int(
            time.time()
        ):
            return OfficerIdentity(subject="officer", email=None, auth_method="passcode")
        return None

    if len(parts) == 4 and parts[0] == NAMED_SESSION_VERSION and parts[1].isdigit():
        payload = f"{NAMED_SESSION_VERSION}.{parts[1]}.{parts[2]}"
        expected = _signature(settings.admin_token, payload)
        if not hmac.compare_digest(expected.encode(), parts[3].encode()):
            return None
        if int(parts[1]) <= int(time.time()):
            return None
        decoded = _b64url_decode(parts[2])
        if not decoded:
            return None
        email = decoded if "@" in decoded else None
        return OfficerIdentity(subject=decoded, email=email, auth_method="passcode")

    return None


def verify_session(settings: Settings, token: str | None) -> bool:
    """True when `token` has a valid signature and is unexpired."""
    return verify_session_identity(settings, token) is not None


def _bearer_credential(headers: Mapping[str, str]) -> str | None:
    lowered = {name.lower(): value for name, value in headers.items()}
    scheme, _, credential = lowered.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    cleaned = credential.strip()
    return cleaned or None


def authorized_for(settings: Settings, headers: Mapping[str, str]) -> bool:
    """Synchronous check for legacy `X-Officer-Token` or HMAC `Authorization: Bearer <session>`."""
    lowered = {name.lower(): value for name, value in headers.items()}
    legacy = lowered.get("x-officer-token")
    if legacy is not None and settings.admin_token is not None:
        if hmac.compare_digest(legacy.encode(), settings.admin_token.encode()):
            return True
    credential = _bearer_credential(headers)
    if not credential:
        return False
    return verify_session(settings, credential)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _verify_firebase_sync(token: str, project_id: str) -> dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_firebase_token(
        token,
        google_requests.Request(),
        audience=project_id,
    )


async def verify_firebase_id_token(
    settings: Settings,
    token: str | None,
    *,
    verifier: Callable[[str, str | None], Any | Awaitable[Any]] | None = None,
) -> OfficerIdentity | None:
    """Verify a Firebase Auth ID token, returning OfficerIdentity or None."""
    if not token:
        return None
    project_id = getattr(settings, "firebase_project_id", None)
    if verifier is None and not project_id:
        return None

    try:
        if verifier is not None:
            claims = await _maybe_await(verifier(token, project_id))
        else:
            claims = await asyncio.to_thread(_verify_firebase_sync, token, project_id)
    except Exception as exc:  # noqa: BLE001 - invalid/unverifiable token -> unauthorized
        log.debug("firebase token verification failed: %s", exc)
        return None

    if isinstance(claims, OfficerIdentity):
        return claims
    if not isinstance(claims, dict):
        return None

    if project_id:
        aud = claims.get("aud")
        if aud and aud != project_id:
            return None
        iss = claims.get("iss")
        expected_iss = f"https://securetoken.google.com/{project_id}"
        if iss and iss != expected_iss:
            return None

    exp = claims.get("exp")
    if exp is not None:
        try:
            if int(exp) <= int(time.time()):
                return None
        except (TypeError, ValueError):
            return None

    subject = str(claims.get("sub") or claims.get("user_id") or claims.get("uid") or "").strip()
    email = claims.get("email")
    email_str = str(email).strip() if email else None
    if not subject and not email_str:
        return None
    return OfficerIdentity(
        subject=subject or email_str or "officer",
        email=email_str,
        auth_method="firebase",
    )


def _verify_oidc_sync(token: str, audience: str | None) -> dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        audience=audience,
    )


async def verify_oidc_token(
    settings: Settings,
    token: str | None,
    *,
    verifier: Callable[[str, str | None], Any | Awaitable[Any]] | None = None,
) -> dict[str, Any] | None:
    """Verify a Google Cloud Scheduler OIDC ID token."""
    if not token:
        return None
    audience = getattr(settings, "oidc_audience", None)
    expected_sa = getattr(settings, "scheduler_service_account_email", None)
    if verifier is None and not audience and not expected_sa:
        return None

    try:
        if verifier is not None:
            claims = await _maybe_await(verifier(token, audience))
        else:
            claims = await asyncio.to_thread(_verify_oidc_sync, token, audience)
    except Exception as exc:  # noqa: BLE001
        log.debug("oidc token verification failed: %s", exc)
        return None

    if not isinstance(claims, dict):
        return None

    if audience and claims.get("aud") != audience:
        return None
    if expected_sa:
        email = str(claims.get("email") or "").strip().lower()
        if email != expected_sa.strip().lower():
            return None
        if claims.get("email_verified") is False:
            return None
    exp = claims.get("exp")
    if exp is not None:
        try:
            if int(exp) <= int(time.time()):
                return None
        except (TypeError, ValueError):
            return None
    return claims


async def resolve_officer_identity(
    settings: Settings,
    headers: Mapping[str, str],
    *,
    firebase_verifier: Callable[[str, str | None], Any | Awaitable[Any]] | None = None,
) -> OfficerIdentity | None:
    """Authenticate an officer via X-Officer-Token, HMAC session, or Firebase ID token."""
    lowered = {name.lower(): value for name, value in headers.items()}
    legacy = lowered.get("x-officer-token")
    if legacy is not None and settings.admin_token is not None:
        if hmac.compare_digest(legacy.encode(), settings.admin_token.encode()):
            return OfficerIdentity(subject="officer", email=None, auth_method="legacy_token")

    credential = _bearer_credential(headers)
    if not credential:
        return None

    session_identity = verify_session_identity(settings, credential)
    if session_identity is not None:
        return session_identity

    return await verify_firebase_id_token(settings, credential, verifier=firebase_verifier)


class PasscodeRateLimiter:
    """Per-client-IP failure window backed by StateStore when available, else in-memory.

    After `max_failures` failures within `window_seconds` the IP is locked out
    until the window expires; a successful sign-in resets the count.
    """

    def __init__(
        self,
        *,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        state_store=None,
    ) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._state_store = state_store
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

    async def ablocked(self, client_ip: str) -> bool:
        if self._state_store is None:
            return self.blocked(client_ip)
        key = f"officer:login_fail:{client_ip}"
        data = await self._state_store.get_json(key)
        if not isinstance(data, list):
            return False
        now = time.time()
        cutoff = now - self._window_seconds
        recent = [float(ts) for ts in data if float(ts) > cutoff]
        return len(recent) >= self._max_failures

    async def arecord_failure(self, client_ip: str) -> None:
        if self._state_store is None:
            self.record_failure(client_ip)
            return
        key = f"officer:login_fail:{client_ip}"
        now = time.time()
        cutoff = now - self._window_seconds
        data = await self._state_store.get_json(key)
        recent = [float(ts) for ts in data if float(ts) > cutoff] if isinstance(data, list) else []
        recent.append(now)
        await self._state_store.set_json(key, recent, ttl_seconds=int(self._window_seconds) + 5)

    async def areset(self, client_ip: str) -> None:
        if self._state_store is None:
            self.reset(client_ip)
            return
        await self._state_store.delete(f"officer:login_fail:{client_ip}")


class EndpointRateLimiter:
    """Per-client-IP rate limiter + duplicate report spam guard backed by StateStore."""

    def __init__(self, state_store=None) -> None:
        self._state_store = state_store
        self._windows: dict[str, list[float]] = {}
        self._dedup: dict[str, float] = {}

    async def allow(self, scope: str, client_ip: str, *, limit: int, window_seconds: int = 60) -> bool:
        """Return True if the request is within `limit` per `window_seconds`."""
        if limit <= 0:
            return True
        key = f"rl:{scope}:{client_ip}"
        if self._state_store is not None:
            count = await self._state_store.incr_window(key, window_seconds)
            return count <= limit

        now = time.monotonic()
        cutoff = now - window_seconds
        hits = [ts for ts in self._windows.get(key, []) if ts > cutoff]
        hits.append(now)
        self._windows[key] = hits
        return len(hits) <= limit

    async def check_and_mark_duplicate(
        self,
        *,
        commune_code: str,
        client_ip: str,
        status: str,
        note: str | None,
        window_seconds: int = int(REPORT_DEDUP_WINDOW_SECONDS),
    ) -> bool:
        """Return True when an identical report was submitted recently by the same client."""
        digest = hashlib.sha256(
            f"{commune_code}|{client_ip}|{status}|{(note or '').strip().lower()}".encode("utf-8")
        ).hexdigest()[:24]
        key = f"report:dedup:{digest}"
        now = time.time()
        if self._state_store is not None:
            prev = await self._state_store.get_timestamp(key)
            if prev is not None and (now - prev) < window_seconds:
                return True
            await self._state_store.set_timestamp(key, now, ttl_seconds=window_seconds)
            return False

        prev = self._dedup.get(key)
        if prev is not None and (now - prev) < window_seconds:
            return True
        self._dedup[key] = now
        return False
