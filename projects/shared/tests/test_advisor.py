"""AC-04: advisor ReAct loop calls the tools with grounded data.

The loop is engine-agnostic; tests drive it with a ScriptedLLM, reproducing the
AC-04 scenario: agronomist asks about rising water at harvest time, the agent
calls `get_station_telemetry` and `evaluate_crop_directive` (crop_stage
RIPENING) and composes a reply from the tool results.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mekong_shared.adk_agent import (
    AdvisorUnavailable,
    ScriptedLLM,
    StepResult,
    answer,
    run_react,
)
from mekong_shared.adk_tools import AdvisorToolContext, AdvisorTools
from mekong_shared.models import StationSnapshot, WeatherSnapshot
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
