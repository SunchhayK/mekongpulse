"""Telemetry read APIs + the sync trigger."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.models import StationSnapshot

from support import healthy_handlers, running_client, weather_payload


async def test_latest_empty_until_sync_then_populated(client):
    assert (await client.get("/api/v1/telemetry/latest")).json() == []

    response = await client.post("/api/v1/telemetry/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["stations_polled"] == 4
    assert body["stations_failed"] == []
    assert body["communes_evaluated"] > 1000
    assert sum(body["risk_counts"].values()) == body["communes_evaluated"]
    assert body["worst_tier"] in {"NORMAL", "ADVISORY", "WARNING", "DANGER"}
    assert body["duration_ms"] >= 0

    latest = (await client.get("/api/v1/telemetry/latest")).json()
    by_id = {s["station_id"]: s for s in latest}
    assert set(by_id) == {"019802", "020102", "033401", "033402"}
    assert by_id["019802"]["level_m"] == 12.5
    assert by_id["019802"]["is_stale_fallback"] is False
    assert by_id["019802"]["source"] == "live"
    assert by_id["020102"]["river"] == "Tonlesap"


async def test_sync_degrades_gracefully_with_dead_station(repo, make_pipeline, make_app):
    handlers = {**healthy_handlers(), "019802": 500}
    pipeline = make_pipeline(repo, handlers, weather_payload(0.0))
    app = make_app(repository=repo, pipeline=pipeline)
    async with running_client(app) as client:
        body = (await client.post("/api/v1/telemetry/sync")).json()
        assert body["stations_failed"] == ["019802"]
        assert body["stations_polled"] == 3
        kinds = {w["kind"] for w in body["warnings"] if w["station_id"] == "019802"}
        assert kinds == {"STATION_UNAVAILABLE", "STATION_DROPPED"}
        latest = (await client.get("/api/v1/telemetry/latest")).json()
        assert {s["station_id"] for s in latest} == {"020102", "033401", "033402"}


async def test_hydrograph_returns_series(client, repo):
    await repo.save_observation(
        StationSnapshot(
            station_id="020102",
            name="Prek Kdam",
            river="Tonlesap",
            level_m=6.5,
            alarm_stage_m=9.5,
            flood_stage_m=10.0,
            rate_of_rise_m_per_hr=0.0,
            recorded_at=datetime.now(timezone.utc),
        )
    )
    body = (await client.get("/api/v1/telemetry/hydrograph/020102", params={"hours": 48})).json()
    assert body["station_id"] == "020102"
    assert body["hours"] == 48
    assert len(body["points"]) == 1
    assert body["points"][0]["level_m"] == 6.5
    assert body["points"][0]["t"]


async def test_scheduler_endpoints_require_admin_token_when_configured(
    repo, settings, make_pipeline, make_app
):
    locked = settings.model_copy(update={"admin_token": "tok-123"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)
    async with running_client(app) as client:
        response = await client.post("/api/v1/telemetry/sync")
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
        response = await client.post("/api/v1/patrol/run")
        assert response.status_code == 401
        response = await client.post(
            "/api/v1/telemetry/sync", headers={"authorization": "Bearer tok-123"}
        )
        assert response.status_code == 200
