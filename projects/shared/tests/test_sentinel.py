"""AC-03 / FR-07: MekongSentinel patrol — escalation alerts and 6h debounce.

Drives the real Pipeline (mock MRC + weather transports, memory repo) and the
real SentinelPatrol through an escalation script using the Kampong Cham corridor
(commune 030502, served by station 019802, which has no gauge datum so the
elevation rule is inert and tiers are fully deterministic).
"""

from __future__ import annotations

from mekong_shared.models import RiskTier
from mekong_shared.sentinel import SentinelPatrol
from mekong_shared.stations import load_stations

from support import healthy_handlers, weather_payload

COMMUNE = "030502"  # Kampong Cham town commune
STATION = "019802"
ALARM, FLOOD = 15.2, 16.2


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RiskTier, int, bool, bool]] = []

    async def __call__(self, alert, subscribers, post_to_channel=True) -> int:
        self.calls.append(
            (
                alert.commune_id,
                alert.risk_tier,
                len(subscribers),
                alert.audio_url is not None,
                post_to_channel,
            )
        )
        return len(subscribers)


async def _patrol(repo, settings, make_pipeline, handlers, dispatcher):
    pipeline = make_pipeline(repo, handlers, weather=weather_payload(0.0))
    patrol = SentinelPatrol(pipeline, settings=settings, dispatcher=dispatcher)
    return await patrol.run()


async def test_ac03_escalation_dispatches_with_debounce(
    repo, settings, make_pipeline, gazetteer
):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.upsert_subscription("12345", COMMUNE, "RIPENING")
    dispatcher = RecordingDispatcher()
    commune = gazetteer.get(COMMUNE)
    assert commune is not None and commune.nearest_station_id == STATION

    # Run 1 — calm baseline (12.5m, 2.7m below alarm) => NORMAL for this corridor.
    summary1 = await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 12.5}), dispatcher
    )
    assert [a for a in summary1.alerts if a.commune_id == COMMUNE] == []
    assert repo.risks[COMMUNE].tier is RiskTier.NORMAL

    # Run 2 — stage jumps above alarm with a slow rise => NORMAL -> WARNING escalation.
    summary2 = await _patrol(
        repo,
        settings,
        make_pipeline,
        healthy_handlers(levels={STATION: 15.5}, rates={STATION: 0.02}),
        dispatcher,
    )
    escalated = [a for a in summary2.alerts if a.commune_id == COMMUNE]
    assert len(escalated) == 1, [a.commune_id for a in summary2.alerts]
    alert = escalated[0]
    assert alert.risk_tier is RiskTier.WARNING
    assert alert.recipients_count == 1  # one subscriber
    assert alert.lead_time_hours == 35  # (16.2 - 15.5) / 0.02 m/hr
    # audit trail (AC-03: log the dispatch run and recipient count)
    assert any(a.commune_id == COMMUNE for a in repo.sentinel_alerts)
    assert any(d["commune_id"] == COMMUNE for d in repo.dispatches)
    assert repo.subscriptions[("12345", COMMUNE)].last_notified_risk_tier is RiskTier.WARNING

    # Run 3 — stage floods (16.5m) => WARNING -> DANGER but 6h debounce blocks it.
    summary3 = await _patrol(
        repo,
        settings,
        make_pipeline,
        healthy_handlers(levels={STATION: 16.5}, rates={STATION: 0.02}),
        dispatcher,
    )
    assert COMMUNE in summary3.debounced
    assert [a for a in summary3.alerts if a.commune_id == COMMUNE] == []
    assert summary3.run.alerts_dispatched_count == 0
    assert len([a for a in repo.sentinel_alerts if a.commune_id == COMMUNE]) == 1

    # Patrol run audit rows
    assert len(repo.patrol_runs) == 3
    assert repo.patrol_runs[-1].communes_evaluated > 1000


async def test_escalation_personalizes_by_stored_stage(repo, settings, make_pipeline):
    """FR-09: push alerts use each subscriber's stored stage; one channel post total."""
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    await repo.upsert_subscription("12345", COMMUNE, "RIPENING")
    await repo.upsert_subscription("67890", COMMUNE, "VEGETATIVE")
    dispatcher = RecordingDispatcher()

    await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 12.5}), dispatcher
    )
    summary = await _patrol(
        repo,
        settings,
        make_pipeline,
        healthy_handlers(levels={STATION: 15.5}, rates={STATION: 0.02}),
        dispatcher,
    )

    escalated = [a for a in summary.alerts if a.commune_id == COMMUNE]
    # Ripening group is dispatched first and carries the public-channel post;
    # the vegetative group gets its own directive set and no second channel post.
    assert [a.directive_title for a in escalated] == [
        "Emergency harvest acceleration",
        "Prepare sluice gates and field drainage",
    ]
    assert [a.recipients_count for a in escalated] == [1, 1]
    commune_calls = [c for c in dispatcher.calls if c[0] == COMMUNE]
    assert [(c[2], c[4]) for c in commune_calls] == [(1, True), (1, False)]
    for chat_id in ("12345", "67890"):
        assert repo.subscriptions[(chat_id, COMMUNE)].last_notified_risk_tier is RiskTier.WARNING
    assert len([d for d in repo.dispatches if d["commune_id"] == COMMUNE]) == 2


async def test_patrol_without_subscribers_records_zero_recipients(
    repo, settings, make_pipeline, gazetteer
):
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    dispatcher = RecordingDispatcher()
    await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 12.5}), dispatcher
    )
    summary = await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 15.5}), dispatcher
    )
    alerts = [a for a in summary.alerts if a.commune_id == COMMUNE]
    assert len(alerts) == 1 and alerts[0].recipients_count == 0


async def test_patrol_alert_carries_text_when_tts_unavailable(
    repo, settings, make_pipeline
):
    """JRN-05 fallback: no Gemini key in dev => text bulletin, audio None."""
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    dispatcher = RecordingDispatcher()
    await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 12.5}), dispatcher
    )
    summary = await _patrol(
        repo, settings, make_pipeline, healthy_handlers(levels={STATION: 15.5}), dispatcher
    )
    alert = next(a for a in summary.alerts if a.commune_id == COMMUNE)
    assert alert.audio_url is None
    assert "សារព្រមាន" in alert.bulletin_text
    assert alert.directive_title
