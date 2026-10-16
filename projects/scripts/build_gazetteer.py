#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["shapely>=2.0", "httpx>=0.27"]
# ///
"""Build data/commune_gazetteer_2025.json from raw MEF sources.

Sources (bundled in data/raw/, downloaded from the MEF DataEF public portal):
  - mef_commune_list_2025.json   -- 1,661 communes, official Khmer + English names
  - mef_district_list_2025.json  -- 210 districts
  - mef_province_list_2025.json  -- 25 provinces
  - mef_commune_boundaries.geojson -- MLMUPC Geography Dept / OCHA boundaries (2018 vintage)

Enrichment:
  - Centroids via Shapely representative_point.
  - Ground elevation via Open-Meteo Elevation API (Copernicus DEM GLO-90).
    Re-runnable in top-up mode: only communes missing elevation are fetched.

Usage:
  uv run scripts/build_gazetteer.py            # full build (top-up elevation gaps)
  uv run scripts/build_gazetteer.py --no-elev  # skip elevation entirely
"""

import json
import sys
import time
from pathlib import Path

import httpx
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent  # projects/
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "commune_gazetteer_2025.json"

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
ELEVATION_BATCH = 90
ELEVATION_RETRIES = 3


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def haversine_km(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt

    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def fetch_elevations(coords: list[tuple[float, float]]) -> list[float | None]:
    """coords: list of (lat, lng). Returns list of elevations (m), None on failure."""
    out: list[float | None] = []
    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(coords), ELEVATION_BATCH):
            batch = coords[i : i + ELEVATION_BATCH]
            lats = ",".join(f"{c[0]:.5f}" for c in batch)
            lngs = ",".join(f"{c[1]:.5f}" for c in batch)
            for attempt in range(ELEVATION_RETRIES):
                try:
                    r = client.get(ELEVATION_URL, params={"latitude": lats, "longitude": lngs})
                    r.raise_for_status()
                    data = r.json()
                    vals = data.get("elevation")
                    if not isinstance(vals, list) or len(vals) != len(batch):
                        raise ValueError(f"unexpected elevation payload: {data}")
                    out.extend(vals)
                    time.sleep(0.5)  # be gentle with the free-tier rate limit
                    break
                except Exception as exc:  # noqa: BLE001 - tolerated, top-up re-runs fill gaps
                    if attempt == ELEVATION_RETRIES - 1:
                        print(f"  elevation batch {i // ELEVATION_BATCH} failed: {exc}")
                        out.extend([None] * len(batch))
                    else:
                        time.sleep(2 * (attempt + 1))
            done = min(i + ELEVATION_BATCH, len(coords))
            print(f"  elevation {done}/{len(coords)}")
    return out


def clean_name(value: str | None) -> str | None:
    """Strip MEF data artifacts (`"`, `‹›`) and collapse whitespace in names."""
    if value is None:
        return None
    for ch in '"‹›':
        value = value.replace(ch, " ")
    return " ".join(value.split())


def main() -> int:
    skip_elevation = "--no-elev" in sys.argv

    provinces = {p["province_code"]: p for p in load_json(RAW / "mef_province_list_2025.json")["items"]}
    districts = {d["district_code"]: d for d in load_json(RAW / "mef_district_list_2025.json")["items"]}
    communes = load_json(RAW / "mef_commune_list_2025.json")
    boundaries = load_json(RAW / "mef_commune_boundaries.geojson")
    stations = load_json(DATA / "stations.json")["stations"]

    # Map boundary features by numeric pcode suffix ("KH110202" -> "110202")
    by_pcode: dict[str, dict] = {}
    for feat in boundaries["features"]:
        pcode = (feat["properties"].get("ADM3_PCODE") or "").strip()
        if pcode.startswith("KH") and len(pcode) > 2:
            by_pcode[pcode[2:]] = feat

    merged = []
    matched = 0
    for c in communes:
        code = c["commune_code"]
        prov = provinces.get(c["province_code"], {})
        dist = districts.get(c["district_code"], {})
        feat = by_pcode.get(code)
        lat = lng = None
        if feat and feat.get("geometry"):
            try:
                geom = shape(feat["geometry"])
                pt = geom.representative_point()
                lat, lng = round(pt.y, 6), round(pt.x, 6)
                matched += 1
            except Exception:  # noqa: BLE001 - malformed geometry tolerated
                feat = None

        nearest_id, nearest_km = None, None
        if lat is not None:
            for st in stations:
                d = haversine_km(lat, lng, st["lat"], st["lng"])
                if nearest_km is None or d < nearest_km:
                    nearest_id, nearest_km = st["id"], round(d, 2)

        merged.append(
            {
                "code": code,
                "name_kh": clean_name(c["commune_kh"]),
                "name_en": clean_name(c["commune_en"]),
                "district_code": c["district_code"],
                "district_en": clean_name(dist.get("district_en")),
                "district_kh": clean_name(dist.get("district_kh")),
                "province_code": c["province_code"],
                "province_en": clean_name(prov.get("province_en")),
                "province_kh": clean_name(prov.get("province_kh")),
                "lat": lat,
                "lng": lng,
                "has_boundary": feat is not None,
                "ground_elevation_m": None,
                "nearest_station_id": nearest_id,
                "distance_to_station_km": nearest_km,
            }
        )

    print(f"communes: {len(merged)}, boundary-matched: {matched}, unmatched: {len(merged) - matched}")

    # Elevation top-up: only for entries without a value
    if not skip_elevation:
        prev = {}
        if OUT.exists():
            for pc in load_json(OUT).get("communes", []):
                if pc.get("ground_elevation_m") is not None:
                    prev[pc["code"]] = pc["ground_elevation_m"]
        for m in merged:
            if m["code"] in prev:
                m["ground_elevation_m"] = prev[m["code"]]
        todo = [m for m in merged if m["ground_elevation_m"] is None and m["lat"] is not None]
        if todo:
            print(f"fetching elevation for {len(todo)} communes...")
            vals = fetch_elevations([(m["lat"], m["lng"]) for m in todo])
            for m, v in zip(todo, vals):
                m["ground_elevation_m"] = v
        with_elev = sum(1 for m in merged if m["ground_elevation_m"] is not None)
        print(f"elevation filled: {with_elev}/{len(merged)}")

    payload = {
        "version": "1.0.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": {
            "names": "Cambodia Commune / District / Province List 2025 - MEF DataEF public portal (data.mef.gov.kh)",
            "boundaries": "Cambodia Commune Boundaries - MLMUPC Dept. of Geography, published via MEF DataEF (OCHA lineage, validOn 2018-10-04)",
            "elevation": "Open-Meteo Elevation API (Copernicus DEM GLO-90), sampled at commune representative points",
        },
        "stats": {
            "communes": len(merged),
            "with_boundary": matched,
            "without_boundary": len(merged) - matched,
            "with_elevation": sum(1 for m in merged if m["ground_elevation_m"] is not None),
        },
        "communes": merged,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
