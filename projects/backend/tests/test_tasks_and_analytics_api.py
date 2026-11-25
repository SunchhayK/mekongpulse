"""Tests for Cloud Tasks endpoints, OIDC admin auth, analytics verification/calibration,
weekly stage-advance digest, and advisor rate limiting."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from mekong_shared.models import (
    FieldReport,
    FieldReportStatus,
    RiskTier,
    SentinelAlert,
)
from mekong_shared.stations import load_stations
from mekong_shared.tasks import LocalTaskQueue

from support import healthy_handlers, running_client, weather_payload

COMMUNE = "030502"
STATION = "019802"


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[object, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.messages.append((chat_id, text, reply_markup))
        return SimpleNamespace(message_id=101)


async def test_patrol_enqueues_watch_runs_onto_task_queue(
    repo, settings, make_pipeline, make_app
):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.upsert_subscription("12345", COMMUNE, "RIPENING")

    queue = LocalTaskQueue()
    rising = make_pipeline(
        repo,
        healthy_handlers(levels={STATION: 15.6}, rates={STATION: 0.02}),
        weather_payload(0.0),
    )
    app_settings = settings.model_copy(update={"watch_auto_max_runs": 2})
    app = make_app(repository=repo, pipeline=rising, settings_override=app_settings)

    async with running_client(app) as client:
        app.state.task_queue = queue
        resp = await client.post("/api/v1/patrol/run")
        assert resp.status_code == 200
        body = resp.json()
        assert body["watch_runs_queued"] == len(queue.enqueued)
        assert body["watch_runs_queued"] >= 1


async def test_task_watch_is_idempotent_and_dispatch_batch_sends_messages(
    repo, settings, make_pipeline, make_app
):
    pipeline = make_pipeline(repo, healthy_handlers(), weather_payload(0.0))
    await pipeline.sync()
    bot = FakeBot()
    app_settings = settings.model_copy(
        update={
            "oidc_audience": "https://api.mekongpulse.test",
            "scheduler_service_account_email": "scheduler@proj.iam.gserviceaccount.com",
        }
    )
    app = make_app(
        repository=repo,
        pipeline=pipeline,
        settings_override=app_settings,
        telegram_app=SimpleNamespace(bot=bot),
    )

    async with running_client(app) as client:
        app.state.oidc_verifier = lambda tok, aud: (
            {
                "aud": aud,
                "email": "scheduler@proj.iam.gserviceaccount.com",
                "email_verified": True,
            }
            if tok == "oidc-ok"
            else None
        )

        # Unauthenticated rejected
        assert (
            await client.post("/api/v1/tasks/watch", json={"commune_code": COMMUNE})
        ).status_code == 401

        headers = {"Authorization": "Bearer oidc-ok"}
        first = await client.post(
            "/api/v1/tasks/watch",
            json={"commune_code": COMMUNE, "trigger": "transition", "dedup_key": "k1"},
            headers=headers,
        )
        assert first.status_code == 200
        assert first.json()["status"] == "completed"
        run_id = first.json()["run"]["id"]

        second = await client.post(
            "/api/v1/tasks/watch",
            json={"commune_code": COMMUNE, "trigger": "transition", "dedup_key": "k1"},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["status"] == "deduplicated"
        assert second.json()["run_id"] == run_id

        alert = SentinelAlert(
            commune_id=COMMUNE,
            station_id=STATION,
            risk_tier=RiskTier.WARNING,
            lead_time_hours=12,
            directive_title="Harvest",
            bulletin_text="សារព្រមាន",
            dispatched_at=datetime.now(timezone.utc),
        )
        batch_resp = await client.post(
            "/api/v1/tasks/dispatch-batch",
            json={"alert": alert.model_dump(mode="json"), "chat_ids": ["111", "222"]},
            headers=headers,
        )
        assert batch_resp.status_code == 200
        assert batch_resp.json()["delivered"] == 2
        assert {chat_id for chat_id, _, _ in bot.messages} == {111, 222}


async def test_analytics_verification_and_calibrate_endpoints(
    repo, settings, make_pipeline, make_app
):
    app_settings = settings.model_copy(update={"admin_token": "adm-1"})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=app_settings)

    now = datetime.now(timezone.utc)
    await repo.save_sentinel_alert(
        SentinelAlert(
            commune_id=COMMUNE,
            station_id=STATION,
            risk_tier=RiskTier.WARNING,
            lead_time_hours=10,
            directive_title="Harvest",
            bulletin_text="Warning",
            dispatched_at=now - timedelta(hours=12),
        )
    )
    await repo.add_field_report(
        FieldReport(
            id="r1",
            commune_code=COMMUNE,
            status=FieldReportStatus.WATER_REACHED,
            source="web",
            reported_at=now - timedelta(hours=2),
        )
    )

    async with running_client(app) as client:
        assert (await client.get("/api/v1/analytics/verification")).status_code == 401
        assert (await client.post("/api/v1/analytics/calibrate")).status_code == 401

        headers = {"X-Officer-Token": "adm-1"}
        ver = await client.get("/api/v1/analytics/verification", headers=headers)
        assert ver.status_code == 200
        summary = ver.json()
        assert summary["total_alerts"] == 1
        assert summary["true_positives"] == 1
        assert summary["precision"] == 1.0

        cal = await client.post("/api/v1/analytics/calibrate", headers=headers)
        assert cal.status_code == 200
        body = cal.json()
        assert body["calibrated"] == 1
        assert body["calibrations"][0]["commune_code"] == COMMUNE
        stored = await repo.list_commune_calibrations()
        assert COMMUNE in stored


async def test_digest_stage_advance_prompts_eligible_rice_subscribers(
    repo, settings, make_pipeline, make_app
):
    bot = FakeBot()
    app = make_app(
        repository=repo,
        pipeline=make_pipeline(repo),
        telegram_app=SimpleNamespace(bot=bot),
    )
    # Planted 75 days ago -> should recommend FLOWERING while currently TILLERING
    planted = date.today() - timedelta(days=75)
    await repo.upsert_subscription(
        "5001", COMMUNE, "TILLERING", crop_type="RICE", planting_date=planted
    )
    # Vegetables should be ignored
    await repo.upsert_subscription(
        "5002", COMMUNE, None, crop_type="VEGETABLES", planting_date=planted
    )

    async with running_client(app) as client:
        resp = await client.post("/api/v1/digest/stage-advance")
        assert resp.status_code == 200
        body = resp.json()
        assert body["checked"] == 2
        assert body["candidates"] == 1
        assert body["prompted"] == 1
        assert body["advancements"][0]["recommended_stage"] == "FLOWERING"
        assert len(bot.messages) == 1
        chat_id, text, markup = bot.messages[0]
        assert chat_id == 5001
        assert "FLOWERING" in text or "Flowering" in text
        assert markup is not None


async def test_advisor_and_transcribe_rate_limiting(repo, settings, make_pipeline, make_app):
    tight = settings.model_copy(update={"advisor_rate_limit_per_min": 1})
    app = make_app(repository=repo, pipeline=make_pipeline(repo), settings_override=tight)

    async with running_client(app) as client:
        # First request hits advisor (503 since no Gemini key), second is 429 rate-limited
        first = await client.post("/api/v1/advisor", json={"message": "hello"})
        assert first.status_code == 503
        second = await client.post("/api/v1/advisor", json={"message": "hello again"})
        assert second.status_code == 429

        # First transcribe request (422 invalid base64), second is 429 rate-limited
        t1 = await client.post(
            "/api/v1/advisor/transcribe",
            json={"audio_base64": "!!!", "mime_type": "audio/ogg"},
        )
        assert t1.status_code == 422
        t2 = await client.post(
            "/api/v1/advisor/transcribe",
            json={"audio_base64": "!!!", "mime_type": "audio/ogg"},
        )
        assert t2.status_code == 429
