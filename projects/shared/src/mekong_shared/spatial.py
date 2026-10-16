"""Spatial reasoner: GPS -> commune resolution and gazetteer search (FR-03/FR-06).

Loads the bundled 2025 MEF gazetteer (1,661 communes) and the official commune
boundary polygons into an in-memory Shapely STRtree (ADR-0004) for sub-15ms
point-in-polygon resolution. Communes added after the 2018 boundary vintage
(117 of 1,661) have no polygon and are reachable through name search and
nearest-centroid fallback (flagged, never silent).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .models import Commune

# Cambodia bounding box; anything beyond is outside the monitored basin.
KH_BBOX = {"min_lat": 10.35, "max_lat": 14.75, "min_lng": 102.30, "max_lng": 107.75}

NEAREST_CENTROID_MAX_KM = 20.0


class OutsideBasinError(Exception):
    """GPS coordinate is outside Cambodia / the monitored basin."""


@dataclass(frozen=True)
class ResolvedCommune:
    commune: Commune
    method: str  # "polygon" | "nearest_centroid"
    distance_km: float = 0.0


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


_TRANSLITERATION_PAIRS = [
    ("koh", "kaoh"), ("kaoh", "koh"),
    ("thom", "thum"), ("thum", "thom"),
    ("kompong", "kampong"), ("kampong", "kompong"),
    ("prek", "preaek"), ("preaek", "prek"),
    ("moung", "maung"), ("maung", "moung"),
]


def _variants(query: str) -> list[str]:
    """Chained transliteration variants (MEF romanization differs from common usage)."""
    base = query.strip().lower()
    seen = {base}
    frontier = [base]
    for _ in range(2):
        nxt: list[str] = []
        for variant in frontier:
            for a, b in _TRANSLITERATION_PAIRS:
                if a in variant:
                    replaced = variant.replace(a, b)
                    if replaced not in seen:
                        seen.add(replaced)
                        nxt.append(replaced)
        frontier = nxt
    return sorted(seen)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


class Gazetteer:
    def __init__(self, data_dir: Path) -> None:
        import json

        gaz = json.loads((data_dir / "commune_gazetteer_2025.json").read_text(encoding="utf-8"))
        self.communes: dict[str, Commune] = {}
        for row in gaz["communes"]:
            self.communes[row["code"]] = Commune(**row)
        bounds = json.loads(
            (data_dir / "raw" / "mef_commune_boundaries.geojson").read_text(encoding="utf-8")
        )
        self._codes: list[str] = []
        geometries = []
        for feat in bounds["features"]:
            pcode = (feat["properties"].get("ADM3_PCODE") or "")[2:]
            if pcode in self.communes and feat.get("geometry"):
                self._codes.append(pcode)
                geometries.append(shape(feat["geometry"]))
        self._tree = STRtree(geometries)

    # ---- resolution ------------------------------------------------------
    def resolve(self, lat: float, lng: float) -> ResolvedCommune:
        if not (
            KH_BBOX["min_lat"] <= lat <= KH_BBOX["max_lat"]
            and KH_BBOX["min_lng"] <= lng <= KH_BBOX["max_lng"]
        ):
            raise OutsideBasinError(f"({lat}, {lng}) is outside Cambodia")
        point = Point(lng, lat)
        # STRtree predicates evaluate as predicate(input_geometry, tree_geometry),
        # so "covered_by" asks: which tree polygon covers this point? (boundary-inclusive)
        hits = self._tree.query(point, predicate="covered_by")
        if len(hits):
            code = self._codes[int(hits[0])]
            return ResolvedCommune(self.communes[code], "polygon", 0.0)
        # No polygon (hydrology gaps, post-2018 communes): nearest centroid inside bbox.
        best: tuple[str, float] | None = None
        for code, commune in self.communes.items():
            if commune.lat is None or commune.lng is None:
                continue
            d = _haversine_km(lat, lng, commune.lat, commune.lng)
            if best is None or d < best[1]:
                best = (code, d)
        if best is None or best[1] > NEAREST_CENTROID_MAX_KM:
            raise OutsideBasinError(f"({lat}, {lng}) has no commune within {NEAREST_CENTROID_MAX_KM}km")
        return ResolvedCommune(self.communes[best[0]], "nearest_centroid", round(best[1], 2))

    # ---- lookup ----------------------------------------------------------
    def get(self, code: str) -> Commune | None:
        return self.communes.get(code)

    def all_communes(self) -> list[Commune]:
        return list(self.communes.values())

    def province_points(self) -> dict[str, tuple[float, float]]:
        """Mean commune centroid per province, used to sample weather forecasts."""
        acc: dict[str, list[float]] = {}
        for c in self.communes.values():
            if c.lat is None or c.lng is None or c.province_code is None:
                continue
            entry = acc.setdefault(c.province_code, [0.0, 0.0, 0.0])
            entry[0] += c.lat
            entry[1] += c.lng
            entry[2] += 1
        return {
            code: (round(v[0] / v[2], 4), round(v[1] / v[2], 4))
            for code, v in acc.items()
            if v[2] > 0
        }

    # ---- search ----------------------------------------------------------
    def search(self, query: str, limit: int = 10) -> list[Commune]:
        """Commune search by Khmer or English name, district, or province.

        District matches return that district's communes (docs use district
        names as commune examples, e.g. "Peam Chor", "Moung Ruessei").
        """
        q_variants = _variants(_strip_accents(query))
        if not query.strip():
            return []
        best: dict[str, tuple[int, Commune]] = {}

        def add(score: int, commune: Commune) -> None:
            current = best.get(commune.code)
            if current is None or score > current[0]:
                best[commune.code] = (score, commune)

        for c in self.communes.values():
            name_en = _strip_accents(c.name_en or "").lower()
            name_kh = c.name_kh or ""
            district_en = _strip_accents(c.district_en or "").lower()
            province_en = _strip_accents(c.province_en or "").lower()
            for q in q_variants:
                if query.strip() == name_kh:
                    add(120, c)
                    continue
                if name_kh and query.strip() in name_kh:
                    add(100, c)
                    continue
                if name_en.startswith(q):
                    add(90, c)
                elif any(w.startswith(q) for w in name_en.split()):
                    add(80, c)
                elif q and q in name_en:
                    add(60, c)
                if c.district_kh and query.strip() in c.district_kh:
                    add(50, c)
                elif district_en and q and q in district_en:
                    add(45, c)
                if c.province_kh and query.strip() in c.province_kh:
                    add(35, c)
                elif province_en and q and q in province_en:
                    add(30, c)
        ranked = sorted(best.values(), key=lambda t: (-t[0], t[1].name_en or t[1].code))
        return [commune for _, commune in ranked[:limit]]


@lru_cache(maxsize=2)
def load_gazetteer(data_dir: str) -> Gazetteer:
    """Process-wide singleton; ~1s first load (ADR-0004 cold-cache note)."""
    return Gazetteer(Path(data_dir))
