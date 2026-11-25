"""Field report endpoints: officials' ground truth per commune."""

from __future__ import annotations

COMMUNE = "030502"
OTHER = "031402"


async def test_post_report_creates_web_report(client):
    response = await client.post(
        f"/api/v1/communes/{COMMUNE}/reports",
        json={
            "status": "water_reached",
            "note": "Water entered the paddy last night",
            "reporter_label": "Commune chief",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["id"]) == 32 and all(c in "0123456789abcdef" for c in body["id"])
    assert body["commune_code"] == COMMUNE
    assert body["status"] == "water_reached"
    assert body["note"] == "Water entered the paddy last night"
    assert body["reporter_label"] == "Commune chief"
    assert body["source"] == "web"
    assert body["reported_at"]


async def test_post_report_optional_fields_default_to_null(client):
    response = await client.post(
        f"/api/v1/communes/{COMMUNE}/reports", json={"status": "other"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["note"] is None
    assert body["reporter_label"] is None


async def test_post_report_unknown_commune_is_404_problem(client):
    response = await client.post("/api/v1/communes/999999/reports", json={"status": "other"})
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/not-found")


async def test_post_report_invalid_status_is_422(client):
    response = await client.post(
        f"/api/v1/communes/{COMMUNE}/reports", json={"status": "flooded"}
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("validation-error")


async def test_list_reports_scoped_newest_first_and_limited(client):
    for status in ("no_water", "water_reached", "other"):
        response = await client.post(
            f"/api/v1/communes/{COMMUNE}/reports", json={"status": status}
        )
        assert response.status_code == 201
    assert (
        await client.post(f"/api/v1/communes/{OTHER}/reports", json={"status": "no_water"})
    ).status_code == 201

    response = await client.get(f"/api/v1/communes/{COMMUNE}/reports")
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert [r["commune_code"] for r in reports] == [COMMUNE] * 3
    assert [r["status"] for r in reports] == ["other", "water_reached", "no_water"]

    limited = (
        await client.get(f"/api/v1/communes/{COMMUNE}/reports", params={"limit": 1})
    ).json()["reports"]
    assert len(limited) == 1
    assert limited[0]["id"] == reports[0]["id"]

    other = (await client.get(f"/api/v1/communes/{OTHER}/reports")).json()["reports"]
    assert [r["status"] for r in other] == ["no_water"]


from support import running_client


async def test_list_reports_empty_for_untouched_commune(client):
    response = await client.get(f"/api/v1/communes/{COMMUNE}/reports")
    assert response.status_code == 200
    assert response.json() == {"reports": []}


async def test_post_report_duplicate_spam_suppressed_for_public(client):
    payload = {"status": "water_reached", "note": "Same spam message"}
    first = await client.post(f"/api/v1/communes/{COMMUNE}/reports", json=payload)
    assert first.status_code == 201
    second = await client.post(f"/api/v1/communes/{COMMUNE}/reports", json=payload)
    assert second.status_code == 429
    assert second.json()["type"].endswith("/duplicate-report")


async def test_post_report_rate_limited_and_officer_bypasses(
    repo, settings, make_pipeline, make_app
):
    tight = settings.model_copy(
        update={"admin_token": "tok-123", "field_report_rate_limit_per_min": 2}
    )
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=tight)
    async with running_client(app) as client:
        assert (
            await client.post(
                f"/api/v1/communes/{COMMUNE}/reports",
                json={"status": "water_reached", "note": "first"},
            )
        ).status_code == 201
        assert (
            await client.post(
                f"/api/v1/communes/{COMMUNE}/reports",
                json={"status": "no_water", "note": "second"},
            )
        ).status_code == 201
        throttled = await client.post(
            f"/api/v1/communes/{COMMUNE}/reports",
            json={"status": "other", "note": "third"},
        )
        assert throttled.status_code == 429
        assert throttled.json()["type"].endswith("/rate-limited")

        # Authenticated officer bypasses public throttle & duplicate check
        officer_headers = {"X-Officer-Token": "tok-123"}
        for _ in range(3):
            ok = await client.post(
                f"/api/v1/communes/{COMMUNE}/reports",
                json={"status": "water_reached", "note": "officer check"},
                headers=officer_headers,
            )
            assert ok.status_code == 201
