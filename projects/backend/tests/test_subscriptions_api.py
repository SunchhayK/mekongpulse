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


async def test_subscription_unknown_commune_is_404(client):
    response = await client.post(
        "/api/v1/subscriptions", json={"chat_id": "555", "commune_code": "999999"}
    )
    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")
