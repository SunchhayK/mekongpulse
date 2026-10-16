"""Spatial reasoner tests.

TEST-SPA-01 drift note: the technical report expected the demo point
(11.266, 105.033) to resolve to "Koh Thom (080402)"; in the 2025 MEF data the
point is inside Khpob (081001, S'ang district) and `080402` is Kampong Kong.
The polygon is the source of truth; the report carries a correction.
"""

from __future__ import annotations

import time

import pytest
from shapely.geometry import shape

from mekong_shared.spatial import KH_BBOX, OutsideBasinError, Gazetteer


def test_demo_point_resolves_by_polygon(gazetteer):
    resolved = gazetteer.resolve(11.266, 105.033)
    assert resolved.commune.code == "081001"
    assert resolved.commune.name_kh == "ខ្ពប"
    assert resolved.method == "polygon"
    assert resolved.commune.district_en == "S'ang"


def test_resolution_is_fast(gazetteer):
    gazetteer.resolve(11.55, 104.92)  # warm the tree
    started = time.perf_counter()
    for _ in range(25):
        gazetteer.resolve(11.55, 104.92)
    elapsed_ms = (time.perf_counter() - started) / 25 * 1000
    assert elapsed_ms < 50, f"resolve too slow: {elapsed_ms:.1f}ms"  # ADR-0004 budget: <15ms typical


def test_resolve_outside_cambodia_raises(gazetteer):
    """TEST-SPA-02: a pin in Vietnam must raise, not guess."""
    with pytest.raises(OutsideBasinError):
        gazetteer.resolve(14.058, 108.277)


def test_resolve_beyond_bbox_edges(gazetteer):
    with pytest.raises(OutsideBasinError):
        gazetteer.resolve(KH_BBOX["min_lat"] - 0.5, 105.0)
    with pytest.raises(OutsideBasinError):
        gazetteer.resolve(11.5, KH_BBOX["max_lng"] + 0.5)


def test_centroids_resolve_to_their_own_commune(gazetteer, data_dir):
    """Self-consistency: many commune interior points must round-trip."""
    import json

    bounds = json.loads((data_dir / "raw" / "mef_commune_boundaries.geojson").read_text())
    checked = 0
    for feature in bounds["features"][::40]:  # sample ~40 polygons
        code = feature["properties"]["ADM3_PCODE"][2:]
        if code not in gazetteer.communes:
            continue
        point = shape(feature["geometry"]).representative_point()
        resolved = gazetteer.resolve(point.y, point.x)
        assert resolved.commune.code == code
        checked += 1
    assert checked >= 30


def test_search_handles_meF_transliteration(gazetteer):
    """'Koh Thom' must find the MEF-spelled 'Kaoh Thum' district communes."""
    hits = gazetteer.search("Koh Thom", limit=10)
    codes = {c.code for c in hits}
    assert {"080404", "080405"} <= codes  # Kaoh Thum Ka / Kha
    assert all(c.district_en == "Kaoh Thum" for c in hits)


def test_search_khmer(gazetteer):
    hits = gazetteer.search("កោះធំ", limit=10)
    assert hits and hits[0].code in {"080404", "080405"}


def test_search_district_returns_its_communes(gazetteer):
    """Docs use district names as commune examples (Peam Chor, Moung Ruessei)."""
    peam_chor = gazetteer.search("Peam Chor", limit=10)
    assert peam_chor and all(c.district_code == "1406" for c in peam_chor)
    moung = gazetteer.search("Moung Ruessei", limit=10)
    assert moung and all(c.district_code == "0206" for c in moung)


def test_search_empty_query(gazetteer):
    assert gazetteer.search("   ") == []


def test_gazetteer_stats(gazetteer, data_dir):
    import json

    payload = json.loads((data_dir / "commune_gazetteer_2025.json").read_text())
    assert len(gazetteer.communes) == 1661
    with_boundary = [c for c in gazetteer.communes.values() if c.has_boundary]
    assert len(with_boundary) == 1544
    # demo-critical elevation coverage
    with_elevation = [c for c in gazetteer.communes.values() if c.ground_elevation_m is not None]
    assert len(with_elevation) == 1544
    assert payload["stats"]["communes"] == 1661
