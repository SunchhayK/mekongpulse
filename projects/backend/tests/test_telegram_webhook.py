"""Telegram webhook ingress: secret validation, processing, dev fallbacks."""

from __future__ import annotations

import pytest

from support import running_client


class FakeTelegramApp:
    def __init__(self) -> None:
        self.bot = object()
        self.processed: list = []

    async def process_update(self, update) -> None:
        self.processed.append(update)


@pytest.fixture
def fake_telegram(monkeypatch):
    # payload passthrough so tests never construct real telegram objects
    monkeypatch.setattr(
        "mekong_backend.routers.telegram._deserialize_update",
        lambda payload, bot: payload,
    )
    return FakeTelegramApp()


async def test_webhook_validates_secret_token(repo, settings, make_pipeline, make_app, fake_telegram):
    secured = settings.model_copy(update={"telegram_webhook_secret": "s3cret"})
    app = make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        settings_override=secured,
        telegram_app=fake_telegram,
    )
    async with running_client(app) as client:
        missing = await client.post("/api/v1/telegram/webhook", json={"update_id": 1})
        assert missing.status_code == 401
        assert missing.json()["type"].endswith("unauthorized")

        wrong = await client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert wrong.status_code == 401
        assert fake_telegram.processed == []

        good = await client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 7},
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        )
        assert good.status_code == 200
        assert good.json() == {"ok": True}
        assert fake_telegram.processed == [{"update_id": 7}]


async def test_webhook_without_bot_is_503(client):
    response = await client.post("/api/v1/telegram/webhook", json={"update_id": 1})
    assert response.status_code == 503
    assert response.json()["type"].endswith("telegram-unavailable")


async def test_webhook_production_requires_secret(repo, settings, make_pipeline, make_app):
    prod = settings.model_copy(update={"environment": "production"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=prod)
    async with running_client(app) as client:
        response = await client.post("/api/v1/telegram/webhook", json={"update_id": 1})
        assert response.status_code == 503
        assert response.json()["type"].endswith("misconfigured")


async def test_webhook_malformed_payload_is_400(
    repo, settings, make_pipeline, make_app, fake_telegram
):
    secured = settings.model_copy(update={"telegram_webhook_secret": "s3cret"})
    app = make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        settings_override=secured,
        telegram_app=fake_telegram,
    )
    async with running_client(app) as client:
        response = await client.post(
            "/api/v1/telegram/webhook",
            content=b"{not json",
            headers={
                "content-type": "application/json",
                "X-Telegram-Bot-Api-Secret-Token": "s3cret",
            },
        )
        assert response.status_code == 400
        assert response.json()["type"].endswith("bad-request")
