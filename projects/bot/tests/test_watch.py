"""Officer watch runs in Telegram: allowlist, draft, approve, reject."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.adk_agent import ScriptedLLM, StepResult
from mekong_shared.models import CommuneRisk, FloodReason, RiskTier

from mekong_bot.service import BotService

COMMUNE = "030502"


async def _seed_risk(repo) -> None:
    await repo.save_commune_risks(
        [
            CommuneRisk(
                commune_code=COMMUNE,
                commune_name_kh="កំពង់ចាម",
                commune_name_en="Kampong Cham",
                province="Kampong Cham",
                tier=RiskTier.WARNING,
                score=70,
                reason=FloodReason.RIVER_OVERFLOW,
                lead_time_hours=35,
                station_id="019802",
                station_level_m=15.5,
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )


async def test_watch_without_query_lists_top_risks(settings, pipeline, repo):
    await _seed_risk(repo)
    await repo.save_commune_risks(
        [
            CommuneRisk(
                commune_code="030101",
                commune_name_kh="បាធាយ",
                commune_name_en="Batheay",
                province="Kampong Cham",
                tier=RiskTier.DANGER,
                score=95,
                reason=FloodReason.RIVER_OVERFLOW,
                lead_time_hours=0,
                station_id="019802",
                station_level_m=15.9,
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    settings = settings.model_copy(update={"officer_telegram_ids": "123"})
    service = BotService(settings, pipeline, repo)

    reply = await service.watch("123", "")

    assert "Choose a commune" in reply.text
    assert reply.buttons is not None
    callback_data = [row[0][1] for row in reply.buttons]
    assert "watch:pick:030101" in callback_data  # DANGER first
    assert "watch:pick:030502" in callback_data
    assert "watch:menu" in callback_data


async def test_watch_pick_callback_creates_run_with_approval_buttons(settings, pipeline, repo):
    await _seed_risk(repo)
    settings = settings.model_copy(update={"officer_telegram_ids": "123"})
    service = BotService(
        settings,
        pipeline,
        repo,
        llm=ScriptedLLM([StepResult(text="Review the warning draft.")]),
        publisher=lambda text: _noop_publish(text),
    )

    reply = await service.callback("123", "watch:pick:030502")

    assert reply.edit is True
    assert reply.buttons is not None
    assert reply.buttons[0][0][1].startswith("watch:approve:")
    runs = await repo.list_agent_runs()
    assert runs and runs[0].commune_code == COMMUNE


async def _noop_publish(text: str) -> dict:
    return {"message_id": 1}


def test_command_menu_lists_the_officer_commands():
    from mekong_bot.main import BOT_COMMANDS

    names = {command.command for command in BOT_COMMANDS}
    assert {"watch", "risk", "report", "mysubs", "subscribe", "digest", "help"} <= names


async def test_watch_requires_officer_allowlist(settings, pipeline, repo):
    service = BotService(settings, pipeline, repo)
    reply = await service.watch("123", COMMUNE)
    assert "not enabled" in reply.text.lower()
    assert reply.buttons is None


async def test_watch_approve_publishes(settings, pipeline, repo):
    await _seed_risk(repo)
    settings = settings.model_copy(
        update={
            "officer_telegram_ids": "123",
            "telegram_broadcast_channel_id": "-1001234567890",
        }
    )
    sent: list[str] = []

    async def publish(text: str) -> dict:
        sent.append(text)
        return {"message_id": 7}

    service = BotService(
        settings,
        pipeline,
        repo,
        llm=ScriptedLLM([StepResult(text="The station is above the alarm stage; review the draft.")]),
        publisher=publish,
    )
    reply = await service.watch("123", COMMUNE)
    assert reply.buttons is not None
    run_id = reply.buttons[0][0][1].split(":")[2]

    approved = await service.callback("123", f"watch:approve:{run_id}")
    assert "Published" in approved.text
    assert approved.edit is True

    run = await repo.get_agent_run(run_id)
    assert run is not None
    assert run.status.value == "published"
    assert run.published_message_id == 7
    assert sent and run.draft_khmer in sent[0]


async def test_watch_reject_keeps_it_private(settings, pipeline, repo):
    await _seed_risk(repo)
    settings = settings.model_copy(update={"officer_telegram_ids": "123"})
    sent: list[str] = []

    async def publish(text: str) -> dict:
        sent.append(text)
        return {"message_id": 7}

    service = BotService(
        settings,
        pipeline,
        repo,
        llm=ScriptedLLM([StepResult(text="Review the warning draft.")]),
        publisher=publish,
    )
    reply = await service.watch("123", COMMUNE)
    run_id = reply.buttons[0][0][1].split(":")[2]

    rejected = await service.callback("123", f"watch:reject:{run_id}")
    assert "rejected" in rejected.text.lower()
    run = await repo.get_agent_run(run_id)
    assert run is not None and run.status.value == "rejected"
    assert sent == []


async def test_watch_callback_rejects_non_officer(settings, pipeline, repo):
    await _seed_risk(repo)
    settings = settings.model_copy(update={"officer_telegram_ids": "123"})
    service = BotService(
        settings,
        pipeline,
        repo,
        llm=ScriptedLLM([StepResult(text="Review the warning draft.")]),
    )
    reply = await service.watch("123", COMMUNE)
    run_id = reply.buttons[0][0][1].split(":")[2]

    denied = await service.callback("999", f"watch:reject:{run_id}")
    assert "not enabled" in denied.text.lower()
    run = await repo.get_agent_run(run_id)
    assert run is not None and run.status.value == "pending_approval"
