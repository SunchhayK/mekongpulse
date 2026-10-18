"""Officer auth unit tests: session wire format, verification, header gate, limiter."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone

import pytest

from mekong_shared.config import Settings

from mekong_backend.officer_auth import (
    PasscodeRateLimiter,
    SignInUnavailable,
    authorized_for,
    effective_passcode,
    issue_session,
    passcode_matches,
    sign_in_configured,
    verify_session,
)

ADMIN = "tok-123"


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, environment="development", **overrides)


def _sign(key: str, exp: int) -> str:
    return hmac.new(key.encode(), f"v1.{exp}".encode(), hashlib.sha256).hexdigest()


def test_session_token_pins_wire_format():
    settings = make_settings(admin_token=ADMIN, officer_session_ttl_hours=2)
    before = int(time.time())

    token, expires_at = issue_session(settings)

    version, exp_raw, signature = token.split(".")
    assert version == "v1"
    assert exp_raw.isdigit()
    assert signature == _sign(ADMIN, int(exp_raw))
    assert before + 2 * 3600 <= int(exp_raw) <= before + 2 * 3600 + 5
    assert expires_at == datetime.fromtimestamp(int(exp_raw), tz=timezone.utc)


def test_verify_session_accepts_fresh_token():
    settings = make_settings(admin_token=ADMIN)
    token, _ = issue_session(settings)
    assert verify_session(settings, token) is True


def test_verify_session_rejects_expired_token():
    settings = make_settings(admin_token=ADMIN)
    exp = int(time.time()) - 10
    assert verify_session(settings, f"v1.{exp}.{_sign(ADMIN, exp)}") is False


def test_verify_session_rejects_tampered_signature():
    settings = make_settings(admin_token=ADMIN)
    token, _ = issue_session(settings)
    head, exp, signature = token.split(".")
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    assert verify_session(settings, f"{head}.{exp}.{flipped}") is False
    # a session signed with another key must not verify
    assert verify_session(settings, f"{head}.{exp}.{_sign('other-key', int(exp))}") is False


@pytest.mark.parametrize(
    "token",
    [
        "",
        "session",
        "v2.123.deadbeef",
        "v1.not-a-number.deadbeef",
        "v1.123",
        "v1.123.deadbeef.extra",
        "v1.123.héllo",
    ],
)
def test_verify_session_rejects_wrong_format(token):
    assert verify_session(make_settings(admin_token=ADMIN), token) is False


def test_session_requires_admin_token_as_signing_key():
    settings = make_settings(officer_passcode="pass-9")
    assert verify_session(settings, "v1.123.deadbeef") is False
    with pytest.raises(SignInUnavailable):
        issue_session(settings)
    assert sign_in_configured(settings) is False


def test_passcode_falls_back_to_admin_token():
    assert effective_passcode(make_settings(officer_passcode="pass-9", admin_token=ADMIN)) == "pass-9"
    assert effective_passcode(make_settings(admin_token=ADMIN)) == ADMIN
    assert effective_passcode(make_settings()) is None

    settings = make_settings(admin_token=ADMIN)
    assert sign_in_configured(settings) is True
    assert passcode_matches(settings, ADMIN) is True
    assert passcode_matches(settings, "nope") is False
    assert passcode_matches(make_settings(), "anything") is False


def test_authorized_for_legacy_header():
    settings = make_settings(admin_token=ADMIN)
    assert authorized_for(settings, {"x-officer-token": ADMIN}) is True
    assert authorized_for(settings, {"X-Officer-Token": ADMIN}) is True
    assert authorized_for(settings, {"x-officer-token": "wrong"}) is False
    assert authorized_for(make_settings(), {"x-officer-token": ADMIN}) is False


def test_authorized_for_bearer_session():
    settings = make_settings(admin_token=ADMIN)
    token, _ = issue_session(settings)
    assert authorized_for(settings, {"authorization": f"Bearer {token}"}) is True
    assert authorized_for(settings, {"Authorization": f"bearer {token}"}) is True
    assert authorized_for(settings, {"authorization": f"Bearer {token}x"}) is False
    assert authorized_for(settings, {"authorization": token}) is False
    assert authorized_for(settings, {}) is False

    exp = int(time.time()) - 5
    stale = f"Bearer v1.{exp}.{_sign(ADMIN, exp)}"
    assert authorized_for(settings, {"authorization": stale}) is False


def test_rate_limiter_blocks_after_five_failures_and_resets():
    limiter = PasscodeRateLimiter()
    for _ in range(4):
        limiter.record_failure("1.2.3.4")
    assert limiter.blocked("1.2.3.4") is False
    limiter.record_failure("1.2.3.4")
    assert limiter.blocked("1.2.3.4") is True
    assert limiter.blocked("5.6.7.8") is False  # per-IP

    limiter.reset("1.2.3.4")
    assert limiter.blocked("1.2.3.4") is False
