"""Watch-officer approval API: auth, create, publish, edit, reject."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from support import healthy_handlers, running_client, weather_payload

AUTH = {"X-Officer-Token": "test-admin"}


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[object, str]] = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        return SimpleNamespace(message_id=42)


class FakeTelegramApp:
    def __init__(self) -> None:
        self.bot = FakeBot()


@pytest.fixture
async def watch_client(repo, settings, make_pipeline, make_app):
    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    await pipeline.sync()
    app_settings = settings.model_copy(
        update={
            "admin_token": "test-admin",
            "telegram_broadcast_channel_id": "-1001234567890",
        }
    )
    telegram_app = FakeTelegramApp()
    app = make_app(
        repository=repo,
        pipeline=pipeline,
        settings_override=app_settings,
        telegram_app=telegram_app,
    )
    async with running_client(app) as client:
        yield client, telegram_app


async def test_watch_endpoints_require_officer(watch_client):
    client, _ = watch_client
    assert (await client.get("/api/v1/watch/runs")).status_code == 401
    assert (await client.post("/api/v1/watch/runs", json={})).status_code == 401


async def test_create_list_approve_and_publish(watch_client):
    client, telegram = watch_client
    created = await client.post(
        "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=AUTH
    )
    assert created.status_code == 200
    run = created.json()["run"]
    assert run["status"] == "pending_approval"
    assert run["draft_khmer"]
    assert run["published_at"] is None

    listed = await client.get("/api/v1/watch/runs", headers=AUTH)
    assert listed.status_code == 200
    assert listed.json()["runs"][0]["id"] == run["id"]

    approved = await client.post(
        f"/api/v1/watch/runs/{run['id']}/approve", json={}, headers=AUTH
    )
    assert approved.status_code == 200
    published = approved.json()["run"]
    assert published["status"] == "published"
    assert published["published_message_id"] == 42
    assert published["published_text"]
    assert telegram.bot.sent and run["draft_khmer"] in telegram.bot.sent[0][1]

    again = await client.post(
        f"/api/v1/watch/runs/{run['id']}/approve", json={}, headers=AUTH
    )
    assert again.status_code == 409


async def test_approve_with_edited_text(watch_client):
    client, telegram = watch_client
    created = await client.post(
        "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=AUTH
    )
    run_id = created.json()["run"]["id"]
    approved = await client.post(
        f"/api/v1/watch/runs/{run_id}/approve",
        json={"khmer_text": "សារដែលបានកែសម្រួល", "english_text": "Edited update."},
        headers=AUTH,
    )
    assert approved.status_code == 200
    run = approved.json()["run"]
    assert run["draft_khmer"] == "សារដែលបានកែសម្រួល"
    assert run["published_text"] == "សារដែលបានកែសម្រួល\n\nEdited update."
    assert "Edited update." in telegram.bot.sent[-1][1]


async def test_reject_a_run(watch_client):
    client, telegram = watch_client
    created = await client.post(
        "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=AUTH
    )
    run_id = created.json()["run"]["id"]
    rejected = await client.post(f"/api/v1/watch/runs/{run_id}/reject", headers=AUTH)
    assert rejected.status_code == 200
    assert rejected.json()["run"]["status"] == "rejected"
    assert rejected.json()["run"]["rejected_at"]
    assert telegram.bot.sent == []


async def test_concurrent_approve_posts_once_and_returns_409_to_loser(
    repo, settings, make_pipeline, make_app
):
    """BUG-04: atomic claim prevents double-post under concurrent approvals."""
    import asyncio

    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    await pipeline.sync()
    app_settings = settings.model_copy(
        update={
            "admin_token": "test-admin",
            "telegram_broadcast_channel_id": "-1001234567890",
        }
    )

    class SlowBot:
        def __init__(self) -> None:
            self.sent: list[tuple[object, str]] = []

        async def send_message(self, chat_id, text):
            await asyncio.sleep(0.05)
            self.sent.append((chat_id, text))
            return SimpleNamespace(message_id=99)

    tg = SimpleNamespace(bot=SlowBot())
    app = make_app(
        repository=repo,
        pipeline=pipeline,
        settings_override=app_settings,
        telegram_app=tg,
    )
    async with running_client(app) as client:
        created = await client.post(
            "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=AUTH
        )
        run_id = created.json()["run"]["id"]

        r1, r2 = await asyncio.gather(
            client.post(f"/api/v1/watch/runs/{run_id}/approve", json={}, headers=AUTH),
            client.post(f"/api/v1/watch/runs/{run_id}/approve", json={}, headers=AUTH),
        )
        assert sorted([r1.status_code, r2.status_code]) == [200, 409]
        assert len(tg.bot.sent) == 1


async def test_approve_failure_marks_run_failed_and_returns_502(
    repo, settings, make_pipeline, make_app
):
    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    await pipeline.sync()
    app_settings = settings.model_copy(
        update={
            "admin_token": "test-admin",
            "telegram_broadcast_channel_id": "-1001234567890",
        }
    )

    class FailingBot:
        async def send_message(self, chat_id, text):
            raise RuntimeError("telegram timeout")

    app = make_app(
        repository=repo,
        pipeline=pipeline,
        settings_override=app_settings,
        telegram_app=SimpleNamespace(bot=FailingBot()),
    )
    async with running_client(app) as client:
        created = await client.post(
            "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=AUTH
        )
        run_id = created.json()["run"]["id"]
        resp = await client.post(f"/api/v1/watch/runs/{run_id}/approve", json={}, headers=AUTH)
        assert resp.status_code == 502
        fetched = await repo.get_agent_run(run_id)
        assert fetched is not None
        assert fetched.status.value == "failed"
        assert fetched.error


async def test_approve_records_firebase_officer_email_in_approved_by(
    repo, settings, make_pipeline, make_app
):
    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    await pipeline.sync()
    app_settings = settings.model_copy(
        update={
            "admin_token": "test-admin",
            "firebase_project_id": "ai-builder-cup-9f8cd",
            "telegram_broadcast_channel_id": "-1001234567890",
        }
    )
    tg = FakeTelegramApp()
    app = make_app(
        repository=repo,
        pipeline=pipeline,
        settings_override=app_settings,
        telegram_app=tg,
    )

    def fake_firebase_verifier(token: str, project_id: str | None) -> dict | None:
        if token == "fb-valid-jwt":
            return {
                "sub": "uid-42",
                "email": "dara@mowram.gov.kh",
                "aud": project_id,
                "iss": f"https://securetoken.google.com/{project_id}",
            }
        return None

    async with running_client(app) as client:
        app.state.firebase_verifier = fake_firebase_verifier
        fb_headers = {"Authorization": "Bearer fb-valid-jwt"}
        created = await client.post(
            "/api/v1/watch/runs", json={"commune_code": "030502"}, headers=fb_headers
        )
        assert created.status_code == 200
        run_id = created.json()["run"]["id"]
        approved = await client.post(
            f"/api/v1/watch/runs/{run_id}/approve", json={}, headers=fb_headers
        )
        assert approved.status_code == 200
        assert approved.json()["run"]["approved_by"] == "dara@mowram.gov.kh"
