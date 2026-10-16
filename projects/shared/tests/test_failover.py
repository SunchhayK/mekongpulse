"""TEST-HYD-02, AC-06, INV-02: station outage failover ladder.

Live -> adjacent station (empirical offset) -> cached reading (stale) -> skip.
None of these may raise; every outcome is logged as a telemetry warning.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mekong_shared.models import StationSnapshot
from mekong_shared.stations import load_stations

from support import mrc_payload


async def test_failover_to_adjacent_station_with_empirical_offset(repo, stations, make_pipeline):
    """TEST-HYD-02 / AC-06: 020102 -> 033401 fallback, explicit staleness."""
    await repo.save_failover_offset("020102", "033401", -0.25)
    handlers = {
        "020102": 500,
        "033401": mrc_payload("033401", level=9.25),
    }
    pipeline = make_pipeline(repo, handlers)
    snapshot, warnings = await pipeline.poll_station(stations["020102"], stations)

    assert snapshot is not None
    assert snapshot.station_id == "020102"
    assert snapshot.is_stale_fallback is True
    assert snapshot.source == "fallback"
    assert snapshot.fallback_offset_m == pytest.approx(-0.25)
    assert snapshot.level_m == pytest.approx(9.0, abs=1e-6)  # 9.25 + (-0.25)
    # stages still come from the roster of the requested station
    assert snapshot.alarm_stage_m == 9.5 and snapshot.flood_stage_m == 10.0
    kinds = [w.kind for w in warnings]
    assert "STATION_UNAVAILABLE" in kinds and "FALLBACK_USED" in kinds
    # AC-06: the warning is persisted (Firestore in prod, repo here)
    assert any(w.station_id == "020102" for w in repo.warnings)


async def test_failover_falls_back_to_cache_when_all_endpoints_down(repo, stations, make_pipeline):
    """INV-02: last resort is the previous reading, with an explicit staleness age."""
    cached = StationSnapshot(
        station_id="020102",
        name="Prek Kdam",
        river="Tonlesap",
        level_m=6.4,
        alarm_stage_m=9.5,
        flood_stage_m=10.0,
        rate_of_rise_m_per_hr=0.01,
        recorded_at=datetime.now(timezone.utc),
    )
    await repo.save_observation(cached)
    pipeline = make_pipeline(repo, {"020102": 500, "033401": 500})
    snapshot, warnings = await pipeline.poll_station(stations["020102"], stations)

    assert snapshot is not None
    assert snapshot.source == "cache"
    assert snapshot.is_stale_fallback is True
    assert snapshot.level_m == 6.4
    assert any(w.kind == "CACHE_USED" for w in warnings)


async def test_all_sources_down_skips_station_without_crashing(repo, stations, make_pipeline):
    """INV-02: a fully dead station must not fail the ingestion run."""
    pipeline = make_pipeline(repo, {"020102": 500, "033401": 500})
    snapshot, warnings = await pipeline.poll_station(stations["020102"], stations)

    assert snapshot is None
    assert [w.kind for w in warnings][-1] == "STATION_DROPPED"
    assert any(w.kind == "STATION_DROPPED" for w in repo.warnings)


async def test_force_fallback_skips_live_call(repo, stations, make_pipeline):
    await repo.save_failover_offset("020102", "033401", -0.5)
    handlers = {
        "020102": mrc_payload("020102", level=6.5),
        "033401": mrc_payload("033401", level=9.0),
    }
    pipeline = make_pipeline(repo, handlers)
    snapshot, _ = await pipeline.poll_station(stations["020102"], stations, force_fallback=True)
    assert snapshot is not None and snapshot.source == "fallback"
    assert snapshot.level_m == pytest.approx(8.5, abs=1e-6)


async def test_sync_runs_with_one_station_down(repo, make_pipeline, settings):
    """A full sync with one dead station still evaluates the other corridors."""
    stations = load_stations(str(settings.data_dir))
    await repo.seed_stations(list(stations.values()))
    handlers = {
        "019802": 500,
        "020102": mrc_payload("020102", level=6.5),
        "033401": mrc_payload("033401", level=7.8),
        "033402": mrc_payload("033402", level=5.2),
    }
    pipeline = make_pipeline(repo, handlers)
    summary, _ = await pipeline.sync()
    assert summary.stations_polled == 3
    assert "019802" in summary.stations_failed
    assert summary.communes_evaluated > 1000
