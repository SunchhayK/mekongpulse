"""Sentinel patrol endpoint: baseline runs and escalation detection."""

from __future__ import annotations

from mekong_shared.stations import load_stations

from support import healthy_handlers, running_client, weather_payload

COMMUNE = "030502"
STATION = "019802"


async def test_patrol_run_baseline(client, repo):
    response = await client.post("/api/v1/patrol/run")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["stations_polled"] == 4
    assert body["run"]["communes_evaluated"] > 1000
    assert body["run"]["alerts_dispatched_count"] == len(body["alerts"])
    assert body["run"]["id"] == 1
    assert len(repo.patrol_runs) == 1
    # calm stage: this corridor must not alert
    assert [a for a in body["alerts"] if a["commune_id"] == COMMUNE] == []


async def test_patrol_detects_escalation_across_ticks(repo, settings, make_pipeline, make_app):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.upsert_subscription("12345", COMMUNE, "RIPENING")

    calm = make_pipeline(repo, healthy_handlers(levels={STATION: 12.5}), weather_payload(0.0))
    app_calm = make_app(repository=repo, pipeline=calm)
    async with running_client(app_calm) as client:
        first = (await client.post("/api/v1/patrol/run")).json()
        assert [a for a in first["alerts"] if a["commune_id"] == COMMUNE] == []

    rising = make_pipeline(
        repo,
        healthy_handlers(levels={STATION: 15.5}, rates={STATION: 0.02}),
        weather_payload(0.0),
    )
    app_rising = make_app(repository=repo, pipeline=rising)
    async with running_client(app_rising) as client:
        second = (await client.post("/api/v1/patrol/run")).json()
        escalated = [a for a in second["alerts"] if a["commune_id"] == COMMUNE]
        assert len(escalated) == 1
        alert = escalated[0]
        assert alert["risk_tier"] == "WARNING"
        assert "ប្រមូលផល" in alert["bulletin_text"]  # harvest directive for ripening rice
        assert second["run"]["alerts_dispatched_count"] == len(second["alerts"])

    assert len(repo.patrol_runs) == 2
    assert repo.patrol_runs[-1].alerts_dispatched_count >= 1
