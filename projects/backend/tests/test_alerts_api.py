"""Alert dispatch log endpoint: newest-first history with commune enrichment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mekong_shared.models import RiskTier, SentinelAlert

BASE_TIME = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def _alert(commune_id: str, dispatched_at: datetime, title: str) -> SentinelAlert:
    return SentinelAlert(
        commune_id=commune_id,
        station_id="019802",
        risk_tier=RiskTier.WARNING,
        lead_time_hours=24,
        directive_title=title,
        bulletin_text="សារជូនដំណឹង",
        dispatched_at=dispatched_at,
        recipients_count=7,
    )


async def test_alert_log_empty(client):
    response = await client.get("/api/v1/alerts/log")
    assert response.status_code == 200
    assert response.json() == []


async def test_alert_log_newest_first_with_commune_names(client, repo):
    commune = next(c for c in await repo.list_communes() if c.nearest_station_id)
    for hours, title in ((2, "oldest"), (0, "newest"), (1, "middle")):
        await repo.save_sentinel_alert(
            _alert(commune.code, BASE_TIME - timedelta(hours=hours), title)
        )

    body = (await client.get("/api/v1/alerts/log")).json()
    assert [row["directive_title"] for row in body] == ["newest", "middle", "oldest"]
    first = body[0]
    assert set(first) == {
        "id", "commune_code", "commune_name_kh", "commune_name_en", "province",
        "station_id", "risk_tier", "lead_time_hours", "directive_title",
        "bulletin_text", "audio_url", "dispatched_at", "recipients_count",
    }
    assert first["commune_code"] == commune.code
    assert first["commune_name_kh"] == commune.name_kh
    assert first["commune_name_en"] == commune.name_en
    assert first["province"] == commune.province_en
    assert first["risk_tier"] == "WARNING"
    assert first["recipients_count"] == 7
    assert first["audio_url"] is None


async def test_alert_log_unmapped_commune_blanks_names(client, repo):
    await repo.save_sentinel_alert(_alert("999999", BASE_TIME, "unknown"))
    row = (await client.get("/api/v1/alerts/log")).json()[0]
    assert row["commune_name_kh"] == ""
    assert row["commune_name_en"] == ""
    assert row["province"] is None


async def test_alert_log_limit_clamped(client, repo):
    for hours in range(3):
        await repo.save_sentinel_alert(
            _alert("030502", BASE_TIME + timedelta(hours=hours), f"alert-{hours}")
        )

    assert len((await client.get("/api/v1/alerts/log", params={"limit": 1})).json()) == 1
    assert len((await client.get("/api/v1/alerts/log", params={"limit": 0})).json()) == 1
    assert len((await client.get("/api/v1/alerts/log", params={"limit": 999})).json()) == 3
