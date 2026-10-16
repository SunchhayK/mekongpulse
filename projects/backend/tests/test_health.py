"""GET /api/v1/health — liveness + MRC connectivity signal."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.models import StationSnapshot


async def test_health_reports_liveness_and_unknown_connection(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "HEALTHY"
    assert body["mrc_station_connection"] == "UNKNOWN"
    assert body["environment"] == "development"
    assert body["repository"] == "memory"
    assert body["timestamp"]


async def test_health_connected_after_fresh_observation(client, repo):
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
    body = (await client.get("/api/v1/health")).json()
    assert body["mrc_station_connection"] == "CONNECTED"
