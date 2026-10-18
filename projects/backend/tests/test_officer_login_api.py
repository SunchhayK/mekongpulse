"""Officer sign-in API: passcode -> session, problem+json failures, rate limit."""

from __future__ import annotations

from datetime import datetime, timezone

from support import running_client

from mekong_backend.officer_auth import verify_session

LOCKED = {"admin_token": "tok-123", "officer_passcode": "pass-9"}


async def test_login_unavailable_without_secrets(client):
    response = await client.post("/api/v1/officer/login", json={"passcode": "whatever"})
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["type"].endswith("officer-sign-in-unavailable")


async def test_login_issues_verifiable_session(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update=LOCKED)
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)

    async with running_client(app) as client:
        response = await client.post("/api/v1/officer/login", json={"passcode": "pass-9"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"session", "expires_at"}
    assert verify_session(locked, body["session"]) is True
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(timezone.utc)


async def test_login_falls_back_to_admin_token_as_passcode(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update={"admin_token": "tok-123"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)

    async with running_client(app) as client:
        response = await client.post("/api/v1/officer/login", json={"passcode": "tok-123"})

    assert response.status_code == 200
    assert verify_session(locked, response.json()["session"]) is True


async def test_login_rejects_wrong_passcode(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update=LOCKED)
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)

    async with running_client(app) as client:
        response = await client.post("/api/v1/officer/login", json={"passcode": "wrong"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("invalid-passcode")


async def test_login_rate_limits_failed_attempts(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update=LOCKED)
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)

    async with running_client(app) as client:
        for _ in range(5):
            failed = await client.post("/api/v1/officer/login", json={"passcode": "wrong"})
            assert failed.status_code == 401

        blocked = await client.post("/api/v1/officer/login", json={"passcode": "pass-9"})

    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")
    assert blocked.json()["type"].endswith("too-many-attempts")


async def test_successful_login_resets_failure_count(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update=LOCKED)
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)

    async with running_client(app) as client:
        for _ in range(4):
            assert (
                await client.post("/api/v1/officer/login", json={"passcode": "wrong"})
            ).status_code == 401
        assert (
            await client.post("/api/v1/officer/login", json={"passcode": "pass-9"})
        ).status_code == 200
        # the counter was reset: two more failures must not trip the limiter
        for _ in range(2):
            assert (
                await client.post("/api/v1/officer/login", json={"passcode": "wrong"})
            ).status_code == 401
