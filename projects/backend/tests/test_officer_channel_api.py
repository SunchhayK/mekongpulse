"""Channel diagnostic and actionable Telegram publish errors."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mekong_shared.adk_agent import AdvisorCall, AdvisorOutcome

from mekong_backend.routers import officer

from support import running_client

CHAT_ID = "-1004467864590"


class FakeBot:
    def __init__(self, *, chat=None, get_chat_error=None, send_error=None) -> None:
        self.chat = chat
        self.get_chat_error = get_chat_error
        self.send_error = send_error
        self.checked: list[str] = []
        self.sent: list[tuple[str, str]] = []

    async def get_chat(self, chat_id):
        self.checked.append(str(chat_id))
        if self.get_chat_error is not None:
            raise self.get_chat_error
        return self.chat

    async def send_message(self, chat_id, text):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((str(chat_id), text))
        return SimpleNamespace(message_id=7)


class FakeTelegramApp:
    def __init__(self, bot: FakeBot) -> None:
        self.bot = bot

    async def shutdown(self) -> None:
        pass


def _wired_app(make_app, repo, make_pipeline, settings, bot: FakeBot, **updates):
    wired = settings.model_copy(
        update={"telegram_broadcast_channel_id": CHAT_ID, **updates}
    )
    return make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        settings_override=wired,
        telegram_app=FakeTelegramApp(bot),
    )


async def test_channel_check_reports_configured_chat(
    repo, settings, make_pipeline, make_app
):
    bot = FakeBot(
        chat=SimpleNamespace(
            id=-1004467864590,
            type="channel",
            title="MekongPulse",
            username="mekongpulse",
        )
    )
    app = _wired_app(make_app, repo, make_pipeline, settings, bot)
    async with running_client(app) as client:
        response = await client.get("/api/v1/telegram/channel")

    assert response.status_code == 200
    assert response.json() == {
        "configured_id": CHAT_ID,
        "ok": True,
        "id": -1004467864590,
        "type": "channel",
        "title": "MekongPulse",
        "username": "mekongpulse",
    }
    assert bot.checked == [CHAT_ID]


async def test_channel_check_trims_null_fields(repo, settings, make_pipeline, make_app):
    bot = FakeBot(chat=SimpleNamespace(id=-1004467864590, type="channel", title=None))
    app = _wired_app(make_app, repo, make_pipeline, settings, bot)
    async with running_client(app) as client:
        body = (await client.get("/api/v1/telegram/channel")).json()

    assert body == {
        "configured_id": CHAT_ID,
        "ok": True,
        "id": -1004467864590,
        "type": "channel",
    }


async def test_channel_check_explains_chat_not_found(
    repo, settings, make_pipeline, make_app
):
    bot = FakeBot(get_chat_error=Exception("Bad Request: chat not found"))
    app = _wired_app(make_app, repo, make_pipeline, settings, bot)
    async with running_client(app) as client:
        response = await client.get("/api/v1/telegram/channel")

    assert response.status_code == 200
    body = response.json()
    assert body["configured_id"] == CHAT_ID
    assert body["ok"] is False
    assert "administrator" in body["detail"]
    assert "-100..." in body["detail"]
    assert "TELEGRAM_BROADCAST_CHANNEL_ID" in body["detail"]
    assert "chat not found" not in body["detail"].lower()


async def test_channel_check_is_503_when_unconfigured(client):
    response = await client.get("/api/v1/telegram/channel")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("telegram-not-configured")


async def test_channel_check_requires_admin(repo, settings, make_pipeline, make_app):
    bot = FakeBot(chat=SimpleNamespace(id=-1004467864590, type="channel"))
    app = _wired_app(make_app, repo, make_pipeline, settings, bot, admin_token="tok-123")
    async with running_client(app) as client:
        unauth = await client.get("/api/v1/telegram/channel")
        authed = await client.get(
            "/api/v1/telegram/channel", headers={"authorization": "Bearer tok-123"}
        )

    assert unauth.status_code == 401
    assert authed.status_code == 200


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (Exception("Bad Request: chat not found"), ("administrator", "-100...")),
        (
            Exception("Forbidden: not enough rights to send text messages to the chat"),
            ("Post messages", "administrator"),
        ),
        (
            Exception("Forbidden: bot was kicked from the channel chat"),
            ("re-add", "administrator"),
        ),
        (TimeoutError("telegram timed out"), ("unreachable", "retry")),
    ],
)
async def test_publish_failure_becomes_actionable_action(
    repo, settings, make_pipeline, make_app, monkeypatch, error, expected
):
    bot = FakeBot(send_error=error)
    app = _wired_app(
        make_app, repo, make_pipeline, settings, bot, admin_token="tok-123"
    )

    async def fake_answer_detailed(tools, history, user_text, settings, *, llm=None):
        result = await tools.publish_to_channel("សារសាធារណៈ")
        call = AdvisorCall(
            "publish_to_channel",
            {"khmer_text": "សារសាធារណៈ"},
            result["status"],
            f"{result['status']}: {result.get('detail', '')}".strip(),
        )
        return AdvisorOutcome(text="ok", calls=[call])

    monkeypatch.setattr(officer, "answer_detailed", fake_answer_detailed)
    async with running_client(app) as client:
        response = await client.post(
            "/api/v1/advisor",
            json={"message": "publish please"},
            headers={"X-Officer-Token": "tok-123"},
        )

    assert response.status_code == 200
    action = response.json()["actions"][0]
    assert action["status"] == "error"
    for phrase in expected:
        assert phrase in action["detail"]
    assert "chat not found" not in action["detail"].lower()
