"""Station roster loader (data/stations.json).

The four stations verified live against the MRC API on 2026-10-17. The
technical report v1.1.0 listed `019803`/`019806` for Koh Khel/Kampong Cham;
those ids belong to Tan Chau (VN) and Neak Luong in the live API, so the
verified ids are `033402` and `019802`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class StationConfig(BaseModel):
    id: str
    name_en: str
    name_kh: str | None = None
    river: str
    lat: float
    lng: float
    alarm_stage_m: float
    flood_stage_m: float
    zero_gauge_elevation_m: float | None = None
    fallback_id: str | None = None


@lru_cache(maxsize=2)
def load_stations(data_dir: str) -> dict[str, StationConfig]:
    payload = json.loads((Path(data_dir) / "stations.json").read_text(encoding="utf-8"))
    return {s["id"]: StationConfig(**s) for s in payload["stations"]}
