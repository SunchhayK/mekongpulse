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
