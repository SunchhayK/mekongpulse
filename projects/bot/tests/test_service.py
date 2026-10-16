"""BotService flows: subscribe, risk, location, advisor, callbacks."""

from __future__ import annotations

from mekong_shared.adk_agent import ScriptedLLM, StepResult
from mekong_shared.models import CropStage, RiskTier

from mekong_bot.service import BotService

from support import seed_warning_observations, warning_snapshot

COMMUNE = "030502"  # Kampong Cham town, served by 019802


async def test_start_returns_bilingual_welcome(service):
    reply = await service.start("1")
    assert "MekongPulse" in reply.text
    assert "/subscribe" in reply.text
    assert "ជំនន់" in reply.text
    assert reply.buttons is None


async def test_subscribe_by_code_offers_stage_buttons(service):
    reply = await service.subscribe("1", COMMUNE)
    assert "កំពង់ចាម" in reply.text
    assert reply.buttons is not None
    data = {row[0][1] for row in reply.buttons}
    assert data == {f"crop:{COMMUNE}:{stage.value}" for stage in CropStage}


async def test_subscribe_multi_match_returns_pick_list(service):
    reply = await service.subscribe("1", "Koh Thom")
    assert reply.buttons is not None
    data = {row[0][1] for row in reply.buttons}
    assert {"sub:080404", "sub:080405"} <= data
    assert any("Kaoh Thum" in row[0][0] for row in reply.buttons)


async def test_subscribe_unknown_query(service):
    reply = await service.subscribe("1", "zzzz")
    assert "Could not find" in reply.text
    assert reply.buttons is None


async def test_subscribe_stage_persists(service, repo):
    reply = await service.subscribe_stage("1", COMMUNE, "RIPENING")
    assert "✅" in reply.text
    assert "/risk" in reply.text
    sub = repo.subscriptions[("1", COMMUNE)]
    assert sub.crop_stage is CropStage.RIPENING


async def test_subscribe_stage_unknown_code_and_stage(service):
    missing = await service.subscribe_stage("1", "999999", "RIPENING")
    assert "Could not find" in missing.text
    bad_stage = await service.subscribe_stage("1", COMMUNE, "HARVEST")
    assert "Unknown crop stage" in bad_stage.text


async def test_my_subscriptions_empty_then_listed(service):
    empty = await service.my_subscriptions("1")
    assert "No subscriptions yet" in empty.text
    await service.subscribe_stage("1", COMMUNE, "TILLERING")
    listed = await service.my_subscriptions("1")
    assert "កំពង់ចាម" in listed.text
    assert "TILLERING" in listed.text
    assert f"/risk {COMMUNE}" in listed.text


async def test_unsubscribe_flow(service):
    await service.subscribe_stage("1", COMMUNE, "RIPENING")
    removed = await service.unsubscribe("1", COMMUNE)
    assert "🔕" in removed.text
    again = await service.unsubscribe("1", COMMUNE)
    assert "Not subscribed" in again.text


async def test_risk_card_uses_subscription_stage_and_warning_telemetry(service, repo):
    await seed_warning_observations(repo)
    await service.subscribe_stage("1", COMMUNE, "RIPENING")
    reply = await service.risk("1")
    assert "កំពង់ចាម" in reply.text
    assert "ព្រមាន" in reply.text  # WARNING label
    assert "ប្រមូលផល" in reply.text  # harvest instruction
    assert "harvest" in reply.text.lower()
    assert reply.buttons is None  # already subscribed


async def test_risk_for_unsubscribed_offers_subscribe_button(service, repo):
    await seed_warning_observations(repo)
    reply = await service.risk("9", COMMUNE)
    assert reply.buttons == [[("🔔 ចុះឈ្មោះតាមដាន / Subscribe to alerts", f"sub:{COMMUNE}")]]


async def test_risk_without_subscription_hint(service):
    reply = await service.risk("1")
    assert "/subscribe" in reply.text


async def test_location_resolves_and_reports(service, repo, pipeline):
    await seed_warning_observations(repo)
    reply = await service.location("1", 11.266, 105.033)
    assert "ខ្ពប" in reply.text  # Khpob, the commune the demo pin lands in
    assert "polygon" in reply.text
    assert reply.buttons is not None  # offering subscribe


async def test_location_outside_basin_is_polite(service):
    reply = await service.location("1", 14.058, 108.277)
    assert "outside" in reply.text.lower()
    assert reply.buttons is None


async def test_location_already_subscribed_has_no_button(service, repo):
    await seed_warning_observations(repo)
    await service.subscribe_stage("1", "081001", "RIPENING")
    reply = await service.location("1", 11.266, 105.033)
    assert reply.buttons is None


async def test_advisor_without_gemini_key_friendly_fallback(service):
    reply = await service.advisor("1", "Should I harvest tonight?")
    assert "/risk" in reply.text
    assert "GEMINI_API_KEY" in reply.text


async def test_advisor_scripted_llm_grounds_answer_and_persists_turns(
    settings, pipeline, repo
):
    await seed_warning_observations(repo)
    scripted = ScriptedLLM(
        [
            StepResult(
                calls=[
                    ("get_station_telemetry", {"station_id": "019802"}),
                    (
                        "evaluate_crop_directive",
                        {"commune_id": COMMUNE, "crop_stage": "RIPENING"},
                    ),
                ]
            ),
            StepResult(text="Water at Kompong Cham is 15.5m; harvest now."),
        ]
    )
    service = BotService(settings, pipeline, repo, llm=scripted)

    reply = await service.advisor("1", "Rising water tonight at Kampong Cham?")
    assert reply.text == "Water at Kompong Cham is 15.5m; harvest now."

    # grounded tool responses were handed back to the model
    responses = {
        part["function_response"]["name"]: part["function_response"]["response"]
        for content in scripted.contents_seen[1]
        if content.get("role") == "user"
        for part in content["parts"]
        if "function_response" in part
    }
    assert responses["get_station_telemetry"]["water_level_m"] == 15.5
    assert responses["evaluate_crop_directive"]["primary_directive"] == (
        "EMERGENCY_HARVEST_ACCELERATION"
    )

    # conversation persisted for future context
    turns = await repo.recent_turns("1")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[-1].content == reply.text


async def test_callback_routing(service, repo):
    stage_prompt = await service.callback("1", f"sub:{COMMUNE}")
    assert stage_prompt.buttons is not None

    subscribed = await service.callback("1", f"crop:{COMMUNE}:TILLERING")
    assert "✅" in subscribed.text
    assert repo.subscriptions[("1", COMMUNE)].crop_stage is CropStage.TILLERING

    await seed_warning_observations(repo)
    card = await service.callback("1", f"risk:{COMMUNE}")
    assert "កំពង់ចាម" in card.text

    unknown = await service.callback("1", "bogus")
    assert "Unknown action" in unknown.text


async def test_risk_stationless_commune_is_graceful(service):
    orphan = next(c for c in service.pipeline.gazetteer.all_communes() if not c.nearest_station_id)
    reply = await service.risk("1", orphan.code)
    assert "No station telemetry" in reply.text


async def test_estimated_telemetry_noted_in_card(settings, pipeline, repo):
    """INV-03: fallback readings are labelled in the farmer-facing card."""
    snapshot = warning_snapshot("019802").model_copy(
        update={"is_stale_fallback": True, "source": "fallback", "fallback_offset_m": -0.25}
    )
    await repo.save_observation(snapshot)
    service = BotService(settings, pipeline, repo)
    reply = await service.risk("1", COMMUNE)
    assert "estimated" in reply.text.lower()
    assert RiskTier.DANGER.value in reply.text  # escalated conservatively
