"""Station roster loader (data/stations.json).

Nine Cambodian MRC telemetry gauges across the Mekong mainstream, Tonle Sap,
and Bassac rivers (expanded from the original four gauges in IMP-04).
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
