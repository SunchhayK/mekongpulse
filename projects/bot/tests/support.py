"""Bot test helpers: station payload meta + seeded warning observations."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.memory_repo import MemoryRepository
from mekong_shared.models import StationSnapshot


class FieldReportingRepository(MemoryRepository):
    """MemoryRepository + the field-report contract (concurrent shared workstream).

    Repository is gaining add_field_report/list_field_reports; until the
    in-memory backend implements them, bot tests use this local stand-in.
    """

    def __init__(self) -> None:
        super().__init__()
        self.field_reports: list = []

    async def add_field_report(self, report):
        self.field_reports.append(report)
        return report

    async def list_field_reports(self, commune_code: str | None = None, limit: int = 20):
        rows = [
            r
            for r in self.field_reports
            if commune_code is None or r.commune_code == commune_code
        ]
        rows.sort(key=lambda r: r.reported_at, reverse=True)  # newest first, like shared
        return rows[:limit]


STATION_META: dict[str, dict] = {
    "019802": {"name": "Kompong Cham", "river": "Mekong", "alarm": 15.2, "flood": 16.2},
    "020102": {"name": "Prek Kdam", "river": "Tonlesap", "alarm": 9.5, "flood": 10.0},
    "033401": {"name": "Chaktomuk", "river": "Bassac", "alarm": 10.5, "flood": 12.0},
    "033402": {"name": "Koh Khel", "river": "Bassac", "alarm": 7.9, "flood": 8.4},
}


def warning_snapshot(station_id: str, *, level: float | None = None) -> StationSnapshot:
    """A fresh reading 0.3m above alarm stage -> deterministic WARNING tier."""
    meta = STATION_META[station_id]
    return StationSnapshot(
        station_id=station_id,
        name=meta["name"],
        river=meta["river"],
        level_m=level if level is not None else round(meta["alarm"] + 0.3, 2),
        alarm_stage_m=meta["alarm"],
        flood_stage_m=meta["flood"],
        rate_of_rise_m_per_hr=0.0,
        recorded_at=datetime.now(timezone.utc),
    )


async def seed_warning_observations(repo) -> None:
    """Warning-level readings for all four stations (no network fetch needed)."""
    for station_id in STATION_META:
        await repo.save_observation(warning_snapshot(station_id))
