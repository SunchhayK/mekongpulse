"""ProblemDetails contract: shape, trace propagation."""

from __future__ import annotations

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


async def test_problem_shape_and_traceparent_roundtrip(client):
    response = await client.get(
        "/api/v1/communes/999999",
        headers={"traceparent": f"00-{TRACE_ID}-b7ad6b7169203331-01"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "https://mekongpulse.app/problems/not-found"
    assert body["title"] == "Commune not found"
    assert body["status"] == 404
    assert body["detail"]
    assert body["trace_id"] == TRACE_ID
    assert response.headers["traceparent"].startswith(f"00-{TRACE_ID}-")


async def test_problem_generates_trace_id_when_header_absent(client):
    response = await client.get("/api/v1/communes/999999")
    assert response.status_code == 404
    trace_id = response.json()["trace_id"]
    assert trace_id and len(trace_id) == 32
