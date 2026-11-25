"""Subscription CRUD endpoints."""

from __future__ import annotations


async def test_subscription_roundtrip(client):
    response = await client.post(
        "/api/v1/subscriptions",
        json={"chat_id": "555", "commune_code": "080404", "crop_stage": "RIPENING"},
    )
    assert response.status_code == 201
    sub = response.json()
    assert sub["telegram_chat_id"] == "555"
    assert sub["commune_id"] == "080404"
    assert sub["crop_stage"] == "RIPENING"

    listing = (await client.get("/api/v1/subscriptions", params={"chat_id": "555"})).json()
    assert len(listing) == 1

    removed = await client.delete("/api/v1/subscriptions/555/080404")
    assert removed.json() == {"removed": True}
    assert (await client.get("/api/v1/subscriptions", params={"chat_id": "555"})).json() == []


from support import running_client


async def test_subscription_unknown_commune_is_404(client):
    response = await client.post(
        "/api/v1/subscriptions", json={"chat_id": "555", "commune_code": "999999"}
    )
    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


async def test_subscription_crop_type_and_planting_date(client):
    response = await client.post(
        "/api/v1/subscriptions",
        json={
            "chat_id": "777",
            "commune_code": "080404",
            "crop_stage": "TILLERING",
            "crop_type": "VEGETABLES",
            "planting_date": "2026-07-15",
        },
    )
    assert response.status_code == 201
    sub = response.json()
    assert sub["crop_type"] == "VEGETABLES"
    assert sub["planting_date"] == "2026-07-15"


async def test_subscriptions_require_admin_when_configured(repo, settings, make_pipeline, make_app):
    locked = settings.model_copy(update={"admin_token": "secret-admin"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=locked)
    async with running_client(app) as client:
        assert (await client.get("/api/v1/subscriptions", params={"chat_id": "555"})).status_code == 401
        assert (
            await client.post(
                "/api/v1/subscriptions", json={"chat_id": "555", "commune_code": "080404"}
            )
        ).status_code == 401
        assert (await client.delete("/api/v1/subscriptions/555/080404")).status_code == 401

        headers = {"Authorization": "Bearer secret-admin"}
        created = await client.post(
            "/api/v1/subscriptions",
            json={"chat_id": "555", "commune_code": "080404"},
            headers=headers,
        )
        assert created.status_code == 201
        assert (
            await client.get("/api/v1/subscriptions", params={"chat_id": "555"}, headers=headers)
        ).status_code == 200
        assert (
            await client.delete("/api/v1/subscriptions/555/080404", headers=headers)
        ).status_code == 200
