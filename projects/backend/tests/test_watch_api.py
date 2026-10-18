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
