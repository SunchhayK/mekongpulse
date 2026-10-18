"""Deterministic bilingual daily digest (no LLM, stored data only).

Renders today's persisted risk rows (the same `repo.risk_map()` source the
risk-map endpoint serves): tier counts, the top elevated communes with lead
times where present, a stale-telemetry line when any station is degraded, and
the officer dashboard link from `settings.web_base_url`. Khmer first, English
second, so the caller can post both to the public channel.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Settings
from .models import CommuneRisk, RiskTier
from .repository import Repository
from .stations import load_stations

TOP_ELEVATED = 10


async def build_digest(repo: Repository, settings: Settings) -> tuple[str, str]:
    """(khmer, english) digest text built only from persisted rows."""
    risks = await repo.risk_map()
    counts = {tier: 0 for tier in RiskTier}
    for risk in risks:
        counts[risk.tier] += 1

    elevated_all = [r for r in risks if r.tier.at_least(RiskTier.ADVISORY)]
    elevated = sorted(
        elevated_all,
        key=lambda r: (-r.tier.severity, -r.score, r.lead_time_hours or 10**9, r.commune_code),
    )[:TOP_ELEVATED]

    roster = load_stations(str(settings.data_dir))
    stale = 0
    for station_id in roster:
        snapshot = await repo.latest_observation(station_id)
        if snapshot is not None and (snapshot.is_stale_fallback or snapshot.source != "live"):
            stale += 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        _khmer(stamp, counts, elevated, len(elevated_all), stale, settings.web_base_url),
        _english(stamp, counts, elevated, len(elevated_all), stale, settings.web_base_url),
    )


def _counts_line(counts: dict[RiskTier, int], *, khmer: bool) -> str:
    parts = [
        f"{tier.emoji} {tier.label_kh if khmer else tier.label_en} {counts[tier]}"
        for tier in RiskTier
    ]
    return " · ".join(parts)


def _khmer(
    stamp: str,
    counts: dict[RiskTier, int],
    elevated: list[CommuneRisk],
    total_elevated: int,
    stale: int,
    dashboard: str,
) -> str:
    lines = [
        f"📣 របាយការណ៍ប្រចាំថ្ងៃ MekongPulse — {stamp}",
        f"កម្រិតហានិភ័យ: {_counts_line(counts, khmer=True)}",
    ]
    if elevated:
        lines.append(f"⚠️ ឃុំកម្រិតប្រុងប្រយ័ត្នឡើង ({total_elevated}):")
        for risk in elevated:
            lead = (
                f" — ប្រហែល {risk.lead_time_hours} ម៉ោងទៀត"
                if risk.lead_time_hours is not None
                else ""
            )
            lines.append(
                f"• {risk.commune_name_kh} ({risk.commune_code}): "
                f"{risk.tier.emoji} {risk.tier.label_kh}{lead}"
            )
        if total_elevated > len(elevated):
            lines.append(f"• … និង {total_elevated - len(elevated)} ផ្សេងទៀត")
    else:
        lines.append("គ្មានឃុំកម្រិតប្រុងប្រយ័ត្នឡើងទេ។")
    if stale:
        lines.append(f"📡 ស្ថានីយ: ទិន្នន័យប៉ាន់ស្មាន {stale} ស្ថានីយ")
    lines.append(f"🗺 ផែនទី: {dashboard}")
    return "\n".join(lines)


def _english(
    stamp: str,
    counts: dict[RiskTier, int],
    elevated: list[CommuneRisk],
    total_elevated: int,
    stale: int,
    dashboard: str,
) -> str:
    lines = [
        f"📣 MekongPulse daily digest — {stamp}",
        f"Risk tiers: {_counts_line(counts, khmer=False)}",
    ]
    if elevated:
        lines.append(f"⚠️ Elevated communes ({total_elevated}):")
        for risk in elevated:
            lead = (
                f" — ~{risk.lead_time_hours}h to flooding"
                if risk.lead_time_hours is not None
                else ""
            )
            lines.append(
                f"• {risk.commune_name_en} ({risk.commune_code}): "
                f"{risk.tier.emoji} {risk.tier.label_en}{lead}"
            )
        if total_elevated > len(elevated):
            lines.append(f"• … and {total_elevated - len(elevated)} more")
    else:
        lines.append("No communes at ADVISORY or above.")
    if stale:
        lines.append(f"📡 Stations: {stale} stale/fallback reading(s)")
    lines.append(f"🗺 Dashboard: {dashboard}")
    return "\n".join(lines)
