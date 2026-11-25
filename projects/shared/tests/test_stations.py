"""Tests for expanded 9-station MRC roster, gazetteer assignment, and Firestore indexes."""

from __future__ import annotations

import json
from pathlib import Path

from mekong_shared.config import DATA_DIR_DEFAULT, PROJECTS_ROOT
from mekong_shared.stations import load_stations


def test_stations_roster_has_eight_live_cambodian_gauges():
    load_stations.cache_clear()
    stations = load_stations(str(DATA_DIR_DEFAULT))
    expected_ids = {
        "014501",  # Stung Treng
        "014901",  # Kratie
        "019802",  # Kompong Cham
        "019806",  # Neak Luong
        "020102",  # Prek Kdam
        "020106",  # Kampong Luong
        "033401",  # Chaktomuk
        "033402",  # Koh Khel
    }
    assert set(stations.keys()) == expected_ids
    for st in stations.values():
        assert st.alarm_stage_m < st.flood_stage_m
        if st.fallback_id is not None:
            assert st.fallback_id in stations


def test_gazetteer_communes_assigned_across_expanded_stations():
    load_stations.cache_clear()
    stations = load_stations(str(DATA_DIR_DEFAULT))
    gaz = json.loads((DATA_DIR_DEFAULT / "commune_gazetteer_2025.json").read_text(encoding="utf-8"))
    communes = gaz["communes"]
    assert len(communes) == 1661

    assigned_ids = {c["nearest_station_id"] for c in communes if c["nearest_station_id"]}
    assert assigned_ids.issubset(set(stations.keys()))
    # Verify upstream/Tonle Sap/Prey Veng stations actually pick up communes
    assert {"014501", "014901", "019806", "020106"}.issubset(assigned_ids)
    # Elevations must still be preserved
    with_elev = sum(1 for c in communes if c.get("ground_elevation_m") is not None)
    assert with_elev > 1500


def test_firestore_indexes_file_covers_all_composite_queries():
    indexes_path = Path(PROJECTS_ROOT) / "firestore.indexes.json"
    payload = json.loads(indexes_path.read_text(encoding="utf-8"))
    by_col = {
        idx["collectionGroup"]: [(f["fieldPath"], f["order"]) for f in idx["fields"]]
        for idx in payload["indexes"]
    }
    assert by_col["sentinel_alerts"] == [
        ("commune_id", "ASCENDING"),
        ("dispatched_at", "DESCENDING"),
    ]
    assert by_col["conversation_turns"] == [
        ("chat_id", "ASCENDING"),
        ("created_at", "DESCENDING"),
    ]
    assert by_col["field_reports"] == [
        ("commune_code", "ASCENDING"),
        ("reported_at", "DESCENDING"),
    ]
    assert by_col["agent_runs"] == [
        ("status", "ASCENDING"),
        ("created_at", "DESCENDING"),
    ]
