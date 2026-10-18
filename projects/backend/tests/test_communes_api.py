"""Commune endpoints: risk map, resolve, search, assessment."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.models import StationSnapshot, WeatherSnapshot

COMMUNE = "030502"  # Kampong Cham town, served by station 019802


def _warning_snapshot() -> StationSnapshot:
    return StationSnapshot(
        station_id="019802",
        name="Kompong Cham",
        river="Mekong",
        level_m=15.5,
        alarm_stage_m=15.2,
        flood_stage_m=16.2,
        rate_of_rise_m_per_hr=0.0,
        recorded_at=datetime.now(timezone.utc),
    )


async def _seed_warning_state(repo) -> None:
    await repo.save_observation(_warning_snapshot())
    commune = await repo.get_commune(COMMUNE)
    await repo.save_weather(
        WeatherSnapshot(
            province_code=commune.province_code,
            latitude=commune.lat or 12.0,
            longitude=commune.lng or 105.46,
            precipitation_48h_mm=0.0,
            precipitation_7d_mm=0.0,
            max_rain_24h_mm=0.0,
            soil_moisture_pct=50.0,
            fetched_at=datetime.now(timezone.utc),
        )
    )


async def test_assess_warning_ripening_returns_harvest_plan(client, repo):
    await _seed_warning_state(repo)
    response = await client.post(
        f"/api/v1/communes/{COMMUNE}/assess", json={"crop_stage": "RIPENING"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_tier"] == "WARNING"
    assert body["directive"] == "EMERGENCY_HARVEST_ACCELERATION"
    assert body["directives"][0]["action_code"] == "EMERGENCY_HARVEST_ACCELERATION"
    assert body["estimated"] is False
    assert body["audio"] is None  # no Gemini key configured
    assert "កំពង់ចាម" in body["khmer_bulletin"]
    assert body["english_bulletin"]


async def test_assess_force_requires_officer(client):
    response = await client.post(
        f"/api/v1/communes/{COMMUNE}/assess",
        json={"with_audio": True, "force": True},
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("officer-auth-required")


async def test_assess_unknown_commune_is_404_problem(client):
    response = await client.post("/api/v1/communes/999999/assess", json={})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"].endswith("/not-found")
    assert body["status"] == 404
    assert "999999" in body["detail"]


async def test_assess_stationless_commune_is_409(client, repo):
    communes = await repo.list_communes()
    orphan = next(c for c in communes if not c.nearest_station_id)
    response = await client.post(f"/api/v1/communes/{orphan.code}/assess", json={})
    assert response.status_code == 409
    assert response.json()["type"].endswith("assessment-unavailable")


async def test_assess_invalid_crop_stage_is_422_validation_problem(client):
    response = await client.post(f"/api/v1/communes/{COMMUNE}/assess", json={"crop_stage": "HARVEST"})
    assert response.status_code == 422
    assert response.json()["type"].endswith("validation-error")


async def test_resolve_demo_point_and_outside_basin(client):
    response = await client.get("/api/v1/communes/resolve", params={"lat": 11.266, "lng": 105.033})
    assert response.status_code == 200
    body = response.json()
    assert body["commune_code"] == "081001"
    assert body["method"] == "polygon"
    assert body["nearest_station_id"]

    response = await client.get("/api/v1/communes/resolve", params={"lat": 14.058, "lng": 108.277})
    assert response.status_code == 422
    assert response.json()["type"].endswith("outside-basin")


async def test_search_transliteration_and_commune_detail(client):
    body = (await client.get("/api/v1/communes/search", params={"q": "Koh Thom"})).json()
    codes = {c["commune_code"] for c in body}
    assert {"080404", "080405"} <= codes

    detail = (await client.get("/api/v1/communes/080404")).json()
    assert detail["name_en"] == "Kaoh Thum Ka"
    assert detail["district_en"] == "Kaoh Thum"

    assert (await client.get("/api/v1/communes/999999")).status_code == 404


async def test_risk_map_after_sync_and_province_filter(client):
    await client.post("/api/v1/telemetry/sync")
    full = (await client.get("/api/v1/communes/risk-map")).json()
    assert len(full) > 1000
    assert {"commune_code", "tier", "score", "updated_at"} <= set(full[0])

    kandal = (await client.get("/api/v1/communes/risk-map", params={"province": "Kandal"})).json()
    assert 0 < len(kandal) < len(full)
    assert {row["province"] for row in kandal} == {"Kandal"}


async def test_upstream_down_returns_502_problem(repo, make_pipeline, make_app):
    """MRCTelemetryError while fetching a missing observation -> 502."""
    from support import running_client

    app = make_app(repository=repo, pipeline=make_pipeline(repo, {}))  # every station 404s
    async with running_client(app) as client:
        response = await client.post(f"/api/v1/communes/{COMMUNE}/assess", json={})
        assert response.status_code == 502
        assert response.json()["type"].endswith("telemetry-unavailable")
