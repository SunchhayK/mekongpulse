"""AC-04: advisor ReAct loop calls the tools with grounded data.

The loop is engine-agnostic; tests drive it with a ScriptedLLM, reproducing the
AC-04 scenario: agronomist asks about rising water at harvest time, the agent
calls `get_station_telemetry` and `evaluate_crop_directive` (crop_stage
RIPENING) and composes a reply from the tool results.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pytest

from mekong_shared.adk_agent import (
    AdvisorUnavailable,
    ScriptedLLM,
    StepResult,
    answer,
    answer_detailed,
    run_react,
)
from mekong_shared.adk_tools import AdvisorToolContext, AdvisorTools
from mekong_shared.digest import build_digest
from mekong_shared.models import (
    CommuneRisk,
    FloodReason,
    RiskTier,
    StationSnapshot,
    WeatherSnapshot,
)
from mekong_shared.stations import load_stations

from support import healthy_handlers

COMMUNE = "140601"  # Angkor Angk, Peam Chor district (Prey Veng)


def _snapshot(station_id: str, level: float, alarm: float, flood: float) -> StationSnapshot:
    return StationSnapshot(
        station_id=station_id,
        name=f"Station {station_id}",
        river="Test",
        level_m=level,
        alarm_stage_m=alarm,
        flood_stage_m=flood,
        rate_of_rise_m_per_hr=0.0,
        recorded_at=datetime.now(timezone.utc),
    )


@pytest.fixture
async def advisor_tools(repo, settings, make_pipeline, gazetteer):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    # Warning-level readings everywhere so tier is deterministic for any commune.
    await repo.save_observation(_snapshot("019802", 15.5, 15.2, 16.2))
    await repo.save_observation(_snapshot("020102", 9.6, 9.5, 10.0))
    await repo.save_observation(_snapshot("033401", 10.6, 10.5, 12.0))
    await repo.save_observation(_snapshot("033402", 8.0, 7.9, 8.4))
    commune = gazetteer.get(COMMUNE)
    await repo.save_weather(
        WeatherSnapshot(
            province_code=commune.province_code or "14",
            latitude=commune.lat or 11.5,
            longitude=commune.lng or 105.3,
            precipitation_48h_mm=0.0,
            precipitation_7d_mm=0.0,
            max_rain_24h_mm=0.0,
            soil_moisture_pct=50.0,
            fetched_at=datetime.now(timezone.utc),
        )
    )
    pipeline = make_pipeline(repo, healthy_handlers())
    return AdvisorTools(AdvisorToolContext(pipeline))


async def test_ac04_scripted_agent_calls_tools_and_reasons(advisor_tools):
    scripted = ScriptedLLM(
        [
            StepResult(
                calls=[
                    ("get_station_telemetry", {"station_id": "019802"}),
                    ("evaluate_crop_directive", {"commune_id": COMMUNE, "crop_stage": "RIPENING"}),
                ]
            ),
            StepResult(
                text=(
                    "Kompong Cham is at 15.5m (alarm 15.2m). With ripening rice and a WARNING "
                    "tier, accelerate harvest immediately — the Bassac pulse reaches Peam Chor "
                    "within 24 hours."
                )
            ),
        ]
    )
    reply = await run_react(
        advisor_tools,
        [],
        "If the water rises 25cm tonight at Peam Chor, should I harvest my ripening rice?",
        scripted,
    )
    assert "harvest" in reply.lower()

    # The second LLM turn must carry grounded function responses.
    second_turn = scripted.contents_seen[1]
    responses = {
        part["function_response"]["name"]: part["function_response"]["response"]
        for content in second_turn
        if content.get("role") == "user"
        for part in content["parts"]
        if "function_response" in part
    }
    assert responses["get_station_telemetry"]["water_level_m"] == 15.5
    assert responses["get_station_telemetry"]["alarm_stage_m"] == 15.2
    directive = responses["evaluate_crop_directive"]
    assert directive["risk_tier"] in {"WARNING", "DANGER"}
    assert directive["primary_directive"] == "EMERGENCY_HARVEST_ACCELERATION"
    # flat river in the fixture => no arrival estimate; field must still be present
    assert "lead_time_hours" in directive


async def test_tool_errors_are_returned_to_the_model(advisor_tools):
    scripted = ScriptedLLM(
        [
            StepResult(
                calls=[
                    ("get_station_telemetry", {"station_id": "999999"}),
                    ("evaluate_crop_directive", {"commune_id": COMMUNE, "crop_stage": "HARVEST"}),
                ]
            ),
            StepResult(text="I could not find that station or stage."),
        ]
    )
    await run_react(advisor_tools, [], "check station 999999", scripted)
    responses = {
        part["function_response"]["name"]: part["function_response"]["response"]
        for content in scripted.contents_seen[1]
        if content.get("role") == "user"
        for part in content["parts"]
        if "function_response" in part
    }
    assert "error" in responses["get_station_telemetry"]
    assert responses["get_station_telemetry"]["known_stations"]
    assert "error" in responses["evaluate_crop_directive"]


async def test_resolve_tool_rejects_vietnam_location(advisor_tools):
    result = await advisor_tools.resolve_commune_by_location(14.058, 108.277)
    assert "error" in result and "Cambodia" in result["error"]


async def test_resolve_tool_maps_demo_point(advisor_tools):
    result = await advisor_tools.resolve_commune_by_location(11.266, 105.033)
    assert result["commune_code"] == "081001"
    assert result["method"] == "polygon"


async def test_search_tool_transliteration(advisor_tools):
    result = await advisor_tools.search_commune("Koh Thom")
    codes = {r["commune_code"] for r in result["results"]}
    assert {"080404", "080405"} & codes


async def test_telemetry_tool_marks_estimated_readings(repo, settings, make_pipeline, gazetteer):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    estimated = _snapshot("019802", 15.5, 15.2, 16.2).model_copy(
        update={"is_stale_fallback": True, "source": "fallback", "fallback_offset_m": -0.25}
    )
    await repo.save_observation(estimated)
    tools = AdvisorTools(AdvisorToolContext(make_pipeline(repo, healthy_handlers())))
    result = await tools.get_station_telemetry("019802")
    assert result["estimated"] is True
    assert result["source"] == "fallback"
    assert result["water_level_m"] == 15.5


async def test_answer_without_gemini_key_raises(advisor_tools, settings):
    with pytest.raises(AdvisorUnavailable):
        await answer(advisor_tools, [], "hello", settings)


# --- agentic officer assistant: evidence, drafting, actions -------------------


def _risk(
    code: str,
    name_kh: str,
    name_en: str,
    province: str,
    tier: RiskTier,
    score: int,
    lead_time_hours: int | None = None,
) -> CommuneRisk:
    return CommuneRisk(
        commune_code=code,
        commune_name_kh=name_kh,
        commune_name_en=name_en,
        province=province,
        tier=tier,
        score=score,
        reason=FloodReason.RIVER_PULSE,
        lead_time_hours=lead_time_hours,
        updated_at=datetime.now(timezone.utc),
    )


async def test_get_commune_evidence_tolerates_missing_module(advisor_tools, monkeypatch):
    # `mekong_shared.evidence` is optional at runtime (concurrent workstream).
    monkeypatch.setitem(sys.modules, "mekong_shared.evidence", None)
    result = await advisor_tools.get_commune_evidence(COMMUNE)
    assert "error" in result


async def test_get_commune_evidence_passes_through_payload(advisor_tools, monkeypatch):
    module = types.ModuleType("mekong_shared.evidence")

    async def build_evidence(pipeline, commune_code):  # mirrors the real contract
        return {
            "commune_code": commune_code,
            "confidence": 0.82,
            "freshness": "fresh",
            "qc": {"passed": True},
            "chain": [],
        }

    module.build_evidence = build_evidence
    monkeypatch.setitem(sys.modules, "mekong_shared.evidence", module)
    result = await advisor_tools.get_commune_evidence(COMMUNE)
    assert result["commune_code"] == COMMUNE
    assert result["confidence"] == 0.82


async def test_get_commune_evidence_surfaces_builder_failures(advisor_tools, monkeypatch):
    module = types.ModuleType("mekong_shared.evidence")

    async def build_evidence(pipeline, commune_code):
        raise RuntimeError("no qc rows")

    module.build_evidence = build_evidence
    monkeypatch.setitem(sys.modules, "mekong_shared.evidence", module)
    result = await advisor_tools.get_commune_evidence(COMMUNE)
    assert "no qc rows" in result["error"]


async def test_draft_status_update_uses_stored_risk_rows(advisor_tools, repo, settings):
    await repo.save_commune_risks(
        [_risk(COMMUNE, "អង្គរអង្គ", "Angkor Angk", "Prey Veng", RiskTier.WARNING, 72, 12)]
    )
    result = await advisor_tools.draft_status_update([COMMUNE, "999999"])

    for text in (result["khmer"], result["english"]):
        assert settings.web_base_url in text
        assert COMMUNE in text
        assert "999999" in text  # unknown commune -> explicit error entry
    assert "Angkor Angk" in result["english"]
    assert "~12h to flooding" in result["english"]
    assert "No stored risk data for commune 999999" in result["english"]
    assert "មិនមានទិន្នន័យហានិភ័យសម្រាប់ឃុំ 999999" in result["khmer"]
    assert "ព្រមាន" in result["khmer"]
    assert "ប្រហែល 12 ម៉ោងទៀត" in result["khmer"]


async def test_publish_denied_without_officer_authorization(advisor_tools):
    result = await advisor_tools.publish_to_channel("សារសាធារណៈ")
    assert result == {"status": "denied", "detail": "Officer authorization required"}


async def test_publish_unavailable_without_publisher(repo, make_pipeline):
    context = AdvisorToolContext(make_pipeline(repo), authorized=True)
    result = await AdvisorTools(context).publish_to_channel("សារសាធារណៈ")
    assert result == {"status": "unavailable"}


async def test_publish_posts_truncated_bilingual_text(repo, make_pipeline):
    sent: list[str] = []

    async def fake_publisher(text: str) -> dict:
        sent.append(text)
        return {"message_id": 7}

    context = AdvisorToolContext(
        make_pipeline(repo), authorized=True, publisher=fake_publisher
    )
    result = await AdvisorTools(context).publish_to_channel("ក" * 5000, "hello officers")
    assert result == {"status": "posted"}
    assert sent == ["ក" * 4096]  # Telegram limit


async def test_publish_surfaces_publisher_failures(repo, make_pipeline):
    async def broken_publisher(text: str) -> dict:
        raise RuntimeError("telegram down")

    context = AdvisorToolContext(
        make_pipeline(repo), authorized=True, publisher=broken_publisher
    )
    result = await AdvisorTools(context).publish_to_channel("សារសាធារណៈ")
    assert result["status"] == "error"
    assert "telegram down" in result["detail"]


async def test_answer_detailed_traces_ok_tool_calls(advisor_tools, settings):
    scripted = ScriptedLLM(
        [
            StepResult(calls=[("get_station_telemetry", {"station_id": "019802"})]),
            StepResult(text="Kompong Cham is at 15.5m."),
        ]
    )
    outcome = await answer_detailed(advisor_tools, [], "river level?", settings, llm=scripted)

    assert outcome.text == "Kompong Cham is at 15.5m."
    assert len(outcome.calls) == 1
    call = outcome.calls[0]
    assert call.name == "get_station_telemetry"
    assert call.args == {"station_id": "019802"}
    assert call.status == "ok"
    assert "water_level_m=15.5" in call.summary


async def test_answer_detailed_recovers_from_malformed_tool_calls(advisor_tools, settings):
    scripted = ScriptedLLM(
        [
            StepResult(
                calls=[
                    ("does_not_exist", {}),
                    ("get_station_telemetry", {"bogus_argument": 1}),
                ]
            ),
            StepResult(text="Recovered after the bad calls."),
        ]
    )
    outcome = await answer_detailed(advisor_tools, [], "status?", settings, llm=scripted)

    assert outcome.text == "Recovered after the bad calls."
    assert [call.name for call in outcome.calls] == ["get_station_telemetry"]
    assert outcome.calls[0].status == "error"
    responses = {
        part["function_response"]["name"]: part["function_response"]["response"]
        for content in scripted.contents_seen[1]
        if content.get("role") == "user"
        for part in content["parts"]
        if "function_response" in part
    }
    assert "error" in responses["does_not_exist"]
    assert "error" in responses["get_station_telemetry"]


# --- deterministic digest builder ---------------------------------------------


async def test_digest_summarizes_tiers_and_elevated_communes(repo, settings):
    await repo.save_commune_risks(
        [
            _risk("080404", "កោះធំ", "Koh Thom", "Kandal", RiskTier.DANGER, 95, 6),
            _risk(COMMUNE, "អង្គរអង្គ", "Angkor Angk", "Prey Veng", RiskTier.WARNING, 72, 12),
            _risk("081001", "ស្វាយជ្រំ", "Svay Chrum", "Kandal", RiskTier.ADVISORY, 45),
            _risk("080405", "សំរោង", "Samrong", "Kandal", RiskTier.NORMAL, 5),
        ]
    )
    khmer, english = await build_digest(repo, settings)

    assert settings.web_base_url in khmer
    assert settings.web_base_url in english
    assert "🔴 DANGER 1" in english
    assert "🟡 ADVISORY 1" in english
    assert "គ្រោះថ្នាក់ 1" in khmer
    # Elevated section is ordered by severity, then score; NORMAL is omitted.
    assert english.index("Koh Thom") < english.index("Angkor Angk") < english.index("Svay Chrum")
    assert "~6h to flooding" in english
    assert "Samrong" not in english


async def test_digest_is_complete_with_no_stored_risks(repo, settings):
    khmer, english = await build_digest(repo, settings)

    assert "No communes at ADVISORY or above." in english
    assert settings.web_base_url in english
    assert settings.web_base_url in khmer


async def test_digest_notes_stale_stations(repo, settings):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    stale = _snapshot("019802", 15.5, 15.2, 16.2).model_copy(
        update={"is_stale_fallback": True, "source": "fallback"}
    )
    await repo.save_observation(stale)

    khmer, english = await build_digest(repo, settings)

    assert "1 stale/fallback reading(s)" in english
    assert "ទិន្នន័យប៉ាន់ស្មាន 1 ស្ថានីយ" in khmer


class _QuotaLLM:
    """LLM step that fails the way google-genai does when the daily quota is spent."""

    async def step(self, contents):
        from google.genai import errors

        raise errors.ClientError(429, {"error": {"code": 429, "message": "quota exceeded"}}, None)


class _BoomLLM:
    async def step(self, contents):
        raise RuntimeError("boom")


async def test_llm_quota_error_degrades_to_advisor_unavailable(advisor_tools, settings):
    # Live 429s must surface as AdvisorUnavailable (503 / friendly bot text), not a 500.
    with pytest.raises(AdvisorUnavailable, match="LLM provider error"):
        await answer(advisor_tools, [], "status?", settings, llm=_QuotaLLM())


async def test_non_llm_errors_still_propagate(advisor_tools, settings):
    # Only provider failures degrade; real bugs must stay visible.
    with pytest.raises(RuntimeError, match="boom"):
        await answer(advisor_tools, [], "status?", settings, llm=_BoomLLM())
