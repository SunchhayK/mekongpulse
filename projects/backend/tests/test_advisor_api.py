"""Officer advisor API: 503 without Gemini, traced happy path, token gate."""

from __future__ import annotations

from types import SimpleNamespace

from mekong_shared.adk_agent import AdvisorCall, AdvisorOutcome

from mekong_backend.routers import officer

from support import running_client


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id, text):
        self.messages.append((str(chat_id), text))
        return SimpleNamespace(message_id=7)


class FakeTelegramApp:
    def __init__(self) -> None:
        self.bot = FakeBot()

    async def shutdown(self) -> None:
        pass


async def test_advisor_returns_problem_503_without_gemini(client):
    response = await client.post("/api/v1/advisor", json={"message": "សួស្តី"})
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["type"].endswith("advisor-unavailable")
    assert body["detail"]


async def test_advisor_validates_message_bounds(client):
    assert (await client.post("/api/v1/advisor", json={"message": ""})).status_code == 422
    assert (
        await client.post("/api/v1/advisor", json={"message": "x" * 2001})
    ).status_code == 422


async def test_advisor_happy_path_renders_tool_calls_and_actions(client, monkeypatch):
    outcome = AdvisorOutcome(
        text="របាយការណ៍សង្ខេប / Status summary",
        calls=[
            AdvisorCall(
                "evaluate_crop_directive", {"commune_id": "140601"}, "ok", "risk_tier=WARNING"
            ),
            AdvisorCall("publish_to_channel", {"khmer_text": "សារ"}, "ok", "posted"),
            AdvisorCall(
                "publish_to_channel",
                {"khmer_text": "សារ"},
                "ok",
                "denied: Officer authorization required",
            ),
        ],
    )

    async def fake_answer_detailed(tools, history, user_text, settings, *, llm=None):
        return outcome

    monkeypatch.setattr(officer, "answer_detailed", fake_answer_detailed)
    response = await client.post("/api/v1/advisor", json={"message": "តើស្ថានភាពយ៉ាងណា?"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == outcome.text
    assert body["tool_calls"] == [
        {"name": "evaluate_crop_directive", "status": "ok", "summary": "risk_tier=WARNING"},
        {"name": "publish_to_channel", "status": "ok", "summary": "posted"},
        {
            "name": "publish_to_channel",
            "status": "ok",
            "summary": "denied: Officer authorization required",
        },
    ]
    assert body["actions"] == [
        {"type": "telegram_post", "status": "posted", "detail": None},
        {"type": "telegram_post", "status": "denied", "detail": "Officer authorization required"},
    ]


async def test_officer_token_gates_actions_and_wires_publisher(
    repo, settings, make_pipeline, make_app, monkeypatch
):
    locked = settings.model_copy(
        update={"admin_token": "tok-123", "telegram_broadcast_channel_id": "chan-9"}
    )
    telegram_app = FakeTelegramApp()
    app = make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        settings_override=locked,
        telegram_app=telegram_app,
    )
    captured: dict = {}

    async def fake_answer_detailed(tools, history, user_text, settings, *, llm=None):
        captured["authorized"] = tools._ctx.authorized
        captured["user_text"] = user_text
        captured["history"] = [(turn.role, turn.content) for turn in history]
        captured["publisher"] = tools._ctx.publisher
        return AdvisorOutcome(text="ok", calls=[])

    monkeypatch.setattr(officer, "answer_detailed", fake_answer_detailed)

    async with running_client(app) as client:
        await client.post("/api/v1/advisor", json={"message": "របាយការណ៍"})
        assert captured["authorized"] is False

        await client.post(
            "/api/v1/advisor",
            json={
                "message": "publish please",
                "commune_code": "140601",
                "history": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ],
            },
            headers={"X-Officer-Token": "tok-123"},
        )
        assert captured["authorized"] is True
        assert "140601" in captured["user_text"]
        assert captured["history"] == [("user", "hi"), ("assistant", "hello")]

        posted = await captured["publisher"]("សារសាធារណៈ")
        assert posted == {"message_id": 7}

    assert telegram_app.bot.messages == [("chan-9", "សារសាធារណៈ")]


async def test_session_bearer_authorizes_advisor(
    repo, settings, make_pipeline, make_app, monkeypatch
):
    """Sign-in flow: passcode -> session -> advisor publishing authorized."""
    locked = settings.model_copy(
        update={"admin_token": "tok-123", "officer_passcode": "pass-9"}
    )
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)
    captured: dict = {}

    async def fake_answer_detailed(tools, history, user_text, settings, *, llm=None):
        captured["authorized"] = tools._ctx.authorized
        return AdvisorOutcome(text="ok", calls=[])

    monkeypatch.setattr(officer, "answer_detailed", fake_answer_detailed)

    async with running_client(app) as client:
        await client.post(
            "/api/v1/advisor",
            json={"message": "publish please"},
            headers={"Authorization": "Bearer v1.123.bogus"},
        )
        assert captured["authorized"] is False

        login = await client.post("/api/v1/officer/login", json={"passcode": "pass-9"})
        assert login.status_code == 200
        session = login.json()["session"]

        response = await client.post(
            "/api/v1/advisor",
            json={"message": "publish please"},
            headers={"Authorization": f"Bearer {session}"},
        )

    assert response.status_code == 200
    assert captured["authorized"] is True

