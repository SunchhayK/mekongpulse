"""Digest trigger: admin guard, unavailable path, channel post."""

from __future__ import annotations

from types import SimpleNamespace

from support import running_client


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id, text):
        self.messages.append((str(chat_id), text))
        return SimpleNamespace(message_id=11)


class FakeTelegramApp:
    def __init__(self) -> None:
        self.bot = FakeBot()

    async def shutdown(self) -> None:
        pass


async def test_digest_requires_admin_when_configured(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update={"admin_token": "tok-123"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)
    async with running_client(app) as client:
        unauth = await client.post("/api/v1/digest/send")
        assert unauth.status_code == 401
        assert unauth.headers["content-type"].startswith("application/problem+json")

        response = await client.post(
            "/api/v1/digest/send", headers={"authorization": "Bearer tok-123"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"  # Telegram not wired


async def test_digest_is_unavailable_without_telegram(client):
    response = await client.post("/api/v1/digest/send")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["digest_preview"]
    assert len(body["digest_preview"]) <= 200


async def test_digest_posts_to_channel_when_wired(repo, settings, make_pipeline, make_app):
    wired = settings.model_copy(update={"telegram_broadcast_channel_id": "chan-42"})
    telegram_app = FakeTelegramApp()
    app = make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        settings_override=wired,
        telegram_app=telegram_app,
    )
    async with running_client(app) as client:
        response = await client.post("/api/v1/digest/send")

    body = response.json()
    assert body["status"] == "posted"
    assert len(telegram_app.bot.messages) == 1
    chat_id, text = telegram_app.bot.messages[0]
    assert chat_id == "chan-42"
    assert "MekongPulse" in text
    assert body["digest_preview"] in text
