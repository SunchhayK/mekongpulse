"""Evidence endpoint: deterministic provenance for the officials' console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mekong_shared.models import StationSnapshot, WeatherSnapshot

COMMUNE = "030502"  # Kampong Cham town, served by station 019802 (0.47 km)
STATION = "019802"

CONTRACT_KEYS = {
    "commune_code", "commune_name_kh", "commune_name_en", "generated_at", "risk_tier",
    "score", "confidence", "confidence_reasons", "station", "qc", "cross_checks",
    "evidence_chain", "limitations",
}


async def _seed_series(repo, *, rate: float = 0.02, rain: float = 45.0) -> None:
    """25 varied hourly readings ending now, plus the province forecast."""
    now = datetime.now(timezone.utc)
    for i in range(25):
        await repo.save_observation(
            StationSnapshot(
                station_id=STATION,
                name="Kompong Cham",
                river="Mekong",
                level_m=12.0 + 0.02 * i,
                alarm_stage_m=15.2,
                flood_stage_m=16.2,
                rate_of_rise_m_per_hr=rate,
                recorded_at=now - timedelta(hours=24 - i),
            )
        )
    commune = await repo.get_commune(COMMUNE)
    await repo.save_weather(
        WeatherSnapshot(
            province_code=commune.province_code,
            latitude=commune.lat or 12.0,
            longitude=commune.lng or 105.46,
            precipitation_48h_mm=rain,
            precipitation_7d_mm=rain,
            max_rain_24h_mm=rain,
            soil_moisture_pct=50.0,
            fetched_at=now,
        )
    )


async def test_evidence_payload_contract(client, repo):
    await _seed_series(repo)
    response = await client.get(f"/api/v1/communes/{COMMUNE}/evidence")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == CONTRACT_KEYS
    assert "field_reports" not in body  # ground truth is a separate call
    assert body["commune_code"] == COMMUNE
    assert body["risk_tier"] == "ADVISORY"
    assert body["confidence"] == "high"
    assert body["confidence_reasons"] == [
        "fresh_telemetry", "qc_clean", "near_station", "sources_agree",
    ]
    assert body["generated_at"]

    station = body["station"]
    assert station["station_id"] == STATION
    assert station["distance_km"] == 0.47
    assert station["source"] == "live"
    assert station["freshness"] == "fresh"
    assert station["age_minutes"] < 90

    assert body["qc"]["status"] == "pass"
    assert [c["id"] for c in body["qc"]["checks"]] == ["gaps", "stuck", "spike", "range"]
    assert all(c["detail"] and c["detail_kh"] for c in body["qc"]["checks"])

    assert [c["id"] for c in body["cross_checks"]] == [
        "rainfall_agreement", "upstream_coherence",
    ]
    assert body["cross_checks"][0]["status"] == "agree"

    assert [s["id"] for s in body["evidence_chain"]] == [
        "reading", "change", "threshold", "tier", "directive",
    ]
    assert all(s["text_en"] and s["text_kh"] for s in body["evidence_chain"])
    assert body["limitations"]["text_en"] and body["limitations"]["text_kh"]


async def test_evidence_unknown_commune_is_404_problem(client):
    response = await client.get("/api/v1/communes/999999/evidence")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"].endswith("/not-found")
    assert "999999" in body["detail"]


async def test_evidence_stationless_commune_is_409(client, repo):
    communes = await repo.list_communes()
    orphan = next(c for c in communes if not c.nearest_station_id)
    response = await client.get(f"/api/v1/communes/{orphan.code}/evidence")
    assert response.status_code == 409
    assert response.json()["type"].endswith("assessment-unavailable")


async def test_evidence_fetches_live_reading_when_repo_empty(client, repo):
    response = await client.get(f"/api/v1/communes/{COMMUNE}/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["station"]["source"] == "live"
    assert body["station"]["level_m"] == 12.5  # healthy_handlers default

    saved = await repo.latest_observation(STATION)
    assert saved is not None and saved.source == "live"
