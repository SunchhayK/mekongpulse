"""Deterministic evidence layer: show how a commune's warning was reached.

`build_evidence` mirrors `assess_commune`'s resolution (gazetteer -> nearest
station -> stored snapshot or live MRC -> province weather -> risk classifier)
and adds provenance on top: reading freshness, deterministic QC over the stored
station series, heuristic cross-checks, a readable evidence chain, a confidence
label, and the MRC-style limitations notice. No LLM and no audio: every verdict
is a documented threshold and every string a template, so the payload is
deterministic, fast, and safe to cache (verification layer, research §6.4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel

from .agronomy import primary_directive
from .models import Commune, CommuneRisk, CropStage, Directive, RiskTier, StationSnapshot, WeatherSnapshot
from .pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline
from .risk import (
    RAIN_ADVISORY_48H_MM,
    RATE_PULSE_M_PER_HR,
    WATER_SURFACE_PROXY_MAX_KM,
)
from .spatial import _haversine_km
from .stations import load_stations

# --- tunables (tests pin these) ----------------------------------------------
QC_WINDOW_HOURS = 168  # ~7 days of stored series
QC_GAP_WARN_RATIO = 0.20  # share of expected hourly readings missing
QC_GAP_FAIL_RATIO = 0.50
QC_STUCK_WARN_HOURS = 3.0  # identical level held for this long
QC_STUCK_FAIL_HOURS = 6.0
QC_STUCK_MAX_GAP_HOURS = 2.0  # a reporting gap breaks a "stuck" run
QC_SPIKE_WARN_M = 0.5  # step between two readings close in time
QC_SPIKE_FAIL_M = 1.0
QC_SPIKE_MAX_INTERVAL_HOURS = 3.0  # only steps across a short interval are spikes
QC_RANGE_LOW_MARGIN_M = 10.0  # plausibly below alarm stage
QC_RANGE_HIGH_MARGIN_M = 3.0  # implausibly above flood stage
FRESH_MAX_MINUTES = 90  # MRC cadence is 15 min; tolerate a few missed polls
RECENT_MAX_MINUTES = 360
RISE_EPSILON_M_PER_HR = 0.005  # mirrors risk.py's "no meaningful rise" cut-off
CROSS_CHECK_WINDOW_HOURS = 24
DIRECTIVE_STAGE = CropStage.RIPENING  # the assess API default; evidence takes no stage

QCStatus = Literal["pass", "warn", "fail", "unavailable"]
CrossCheckStatus = Literal["agree", "disagree", "unavailable"]
Confidence = Literal["high", "medium", "low"]
Freshness = Literal["fresh", "recent", "stale"]


class QCCheck(BaseModel):
    id: Literal["gaps", "stuck", "spike", "range"]
    status: QCStatus
    detail: str
    detail_kh: str


class QCBlock(BaseModel):
    status: QCStatus
    checks: list[QCCheck]


class CrossCheck(BaseModel):
    id: Literal["rainfall_agreement", "upstream_coherence"]
    status: CrossCheckStatus
    detail: str
    detail_kh: str


class StationEvidence(BaseModel):
    station_id: str
    name: str
    distance_km: float | None
    source: str  # live | fallback | cache
    recorded_at: datetime
    age_minutes: int
    freshness: Freshness
    level_m: float
    rate_of_rise_m_per_hr: float
    alarm_stage_m: float
    flood_stage_m: float


class ChainStep(BaseModel):
    id: Literal["reading", "change", "threshold", "tier", "directive"]
    text_en: str
    text_kh: str


class Limitations(BaseModel):
    text_en: str
    text_kh: str


class EvidencePayload(BaseModel):
    commune_code: str
    commune_name_kh: str
    commune_name_en: str
    generated_at: datetime
    risk_tier: RiskTier
    score: int
    confidence: Confidence
    confidence_reasons: list[str]
    station: StationEvidence
    qc: QCBlock
    cross_checks: list[CrossCheck]
    evidence_chain: list[ChainStep]
    limitations: Limitations


# --- QC ----------------------------------------------------------------------

def _freshness(age_minutes: int) -> Freshness:
    if age_minutes <= FRESH_MAX_MINUTES:
        return "fresh"
    if age_minutes <= RECENT_MAX_MINUTES:
        return "recent"
    return "stale"


def _check_gaps(points: list[tuple[datetime, float]]) -> QCCheck:
    if len(points) < 2:
        return QCCheck(
            id="gaps", status="unavailable",
            detail="Fewer than two readings in the window; gap check skipped.",
            detail_kh="មានការអានតិចជាងពីរក្នុងរយៈពេលនេះ — ការពិនិត្យចន្លោះខ្វះត្រូវបានឆ្លងកាត់។",
        )
    span_h = (points[-1][0] - points[0][0]).total_seconds() / 3600.0
    if span_h < 1.0:
        return QCCheck(
            id="gaps", status="unavailable",
            detail="Less than one hour of readings; gap check skipped.",
            detail_kh="មានទិន្នន័យតិចជាងមួយម៉ោង — ការពិនិត្យចន្លោះខ្វះត្រូវបានឆ្លងកាត់។",
        )
    expected = int(span_h) + 1  # one expected point per hour
    present = len({(at.year, at.month, at.day, at.hour) for at, _ in points})
    missing = max(0.0, 1.0 - present / expected)
    pct = int(round(missing * 100))
    if missing >= QC_GAP_FAIL_RATIO:
        status: QCStatus = "fail"
    elif missing >= QC_GAP_WARN_RATIO:
        status = "warn"
    else:
        status = "pass"
    if status == "pass":
        detail = f"No hourly gaps: {present} reading hours present over {span_h:.0f} h."
        detail_kh = f"មិនមានចន្លោះខ្វះទេ៖ មានការអាន {present} ម៉ោងក្នុងរយៈពេល {span_h:.0f} ម៉ោង។"
    else:
        detail = f"{pct}% of expected hourly readings missing over {span_h:.0f} h."
        detail_kh = f"ខ្វះទិន្នន័យ {pct}% នៃចំនួនម៉ោងរំពឹងទុកក្នុងរយៈពេល {span_h:.0f} ម៉ោង។"
    return QCCheck(id="gaps", status=status, detail=detail, detail_kh=detail_kh)


def _check_stuck(points: list[tuple[datetime, float]]) -> QCCheck:
    if len(points) < 2:
        return QCCheck(
            id="stuck", status="unavailable",
            detail="Fewer than two readings in the window; stuck-value check skipped.",
            detail_kh="មានការអានតិចជាងពីរក្នុងរយៈពេលនេះ — ការពិនិត្យតម្លៃជាប់គាំងត្រូវបានឆ្លងកាត់។",
        )
    longest = 0.0
    longest_value = points[0][1]
    longest_start = points[0][0]
    run_value = round(points[0][1], 3)
    run_start = run_end = points[0][0]
    for at, level in points[1:]:
        gap_h = (at - run_end).total_seconds() / 3600.0
        if round(level, 3) == run_value and gap_h <= QC_STUCK_MAX_GAP_HOURS:
            run_end = at
            continue
        run_h = (run_end - run_start).total_seconds() / 3600.0
        if run_h > longest:
            longest, longest_value, longest_start = run_h, run_value, run_start
        run_value, run_start, run_end = round(level, 3), at, at
    run_h = (run_end - run_start).total_seconds() / 3600.0
    if run_h > longest:
        longest, longest_value, longest_start = run_h, run_value, run_start

    if longest >= QC_STUCK_FAIL_HOURS:
        status: QCStatus = "fail"
    elif longest >= QC_STUCK_WARN_HOURS:
        status = "warn"
    else:
        status = "pass"
    if status == "pass":
        detail = f"No identical-value run lasting {QC_STUCK_WARN_HOURS:.0f} h or more."
        detail_kh = f"មិនមានលំដាប់តម្លៃដូចគ្នា {QC_STUCK_WARN_HOURS:.0f} ម៉ោង ឬច្រើនជាងនេះទេ។"
    else:
        detail = (
            f"Level held at {longest_value:.2f} m for {longest:.1f} h "
            f"from {longest_start:%Y-%m-%d %H:%M} UTC."
        )
        detail_kh = (
            f"កម្រិតទឹកនៅដូចគ្នា {longest_value:.2f} ម៉ែត្រ អស់រយៈពេល {longest:.1f} ម៉ោង "
            f"ចាប់ពីម៉ោង {longest_start:%H:%M} UTC ថ្ងៃទី {longest_start:%d/%m/%Y}។"
        )
    return QCCheck(id="stuck", status=status, detail=detail, detail_kh=detail_kh)


def _check_spike(points: list[tuple[datetime, float]]) -> QCCheck:
    if len(points) < 2:
        return QCCheck(
            id="spike", status="unavailable",
            detail="Fewer than two readings in the window; spike check skipped.",
            detail_kh="មានការអានតិចជាងពីរក្នុងរយៈពេលនេះ — ការពិនិត្យការលោតខុសប្រក្រតីត្រូវបានឆ្លងកាត់។",
        )
    worst = 0.0
    worst_pair: tuple[datetime, datetime] | None = None
    for (t1, l1), (t2, l2) in zip(points, points[1:]):
        span_h = (t2 - t1).total_seconds() / 3600.0
        if span_h <= 0 or span_h > QC_SPIKE_MAX_INTERVAL_HOURS:
            continue  # a jump across a long gap is a change, not a spike
        step = abs(l2 - l1)
        if step > worst:
            worst, worst_pair = step, (t1, t2)
    if worst_pair is None:
        return QCCheck(
            id="spike", status="unavailable",
            detail="No two readings close enough in time; spike check skipped.",
            detail_kh="មិនមានការអានជាប់គ្នាក្នុងចន្លោះពេលខ្លីគ្រប់គ្រាន់ — ការពិនិត្យការលោតខុសប្រក្រតីត្រូវបានឆ្លងកាត់។",
        )
    if worst >= QC_SPIKE_FAIL_M:
        status: QCStatus = "fail"
    elif worst >= QC_SPIKE_WARN_M:
        status = "warn"
    else:
        status = "pass"
    if status == "pass":
        detail = f"Largest step between readings: {worst:.2f} m."
        detail_kh = f"គម្លាតធំបំផុតរវាងការអានជាប់គ្នា៖ {worst:.2f} ម៉ែត្រ។"
    else:
        t1, t2 = worst_pair
        detail = f"Implausible step of {worst:.2f} m between {t1:%H:%M} and {t2:%H:%M} UTC."
        detail_kh = f"ការលោតខុសប្រក្រតី {worst:.2f} ម៉ែត្រ រវាងម៉ោង {t1:%H:%M} និង {t2:%H:%M} UTC។"
    return QCCheck(id="spike", status=status, detail=detail, detail_kh=detail_kh)


def _check_range(points: list[tuple[datetime, float]], station: StationSnapshot) -> QCCheck:
    if not points:
        return QCCheck(
            id="range", status="unavailable",
            detail="No readings in the window; range check skipped.",
            detail_kh="គ្មានទិន្នន័យក្នុងរយៈពេលនេះ — ការពិនិត្យចន្លោះតម្លៃត្រូវបានឆ្លងកាត់។",
        )
    low = station.alarm_stage_m - QC_RANGE_LOW_MARGIN_M
    high = station.flood_stage_m + QC_RANGE_HIGH_MARGIN_M
    levels = [level for _, level in points]
    outside = [level for level in levels if level < low or level > high]
    if outside:
        return QCCheck(
            id="range", status="fail",
            detail=(
                f"{len(outside)} of {len(levels)} readings outside the plausible "
                f"{low:.2f}-{high:.2f} m range (min {min(levels):.2f}, max {max(levels):.2f})."
            ),
            detail_kh=(
                f"ការអាន {len(outside)} ក្នុងចំណោម {len(levels)} ក្រៅចន្លោះដែលអាចទទួលយកបាន "
                f"{low:.2f}-{high:.2f} ម៉ែត្រ (ទាបបំផុត {min(levels):.2f} ខ្ពស់បំផុត {max(levels):.2f})។"
            ),
        )
    return QCCheck(
        id="range", status="pass",
        detail=f"All {len(levels)} readings within the plausible {low:.2f}-{high:.2f} m range.",
        detail_kh=f"ការអានទាំង {len(levels)} ស្ថិតក្នុងចន្លោះដែលអាចទទួលយកបាន {low:.2f}-{high:.2f} ម៉ែត្រ។",
    )


def _qc_block(checks: list[QCCheck]) -> QCBlock:
    """Overall QC is the worst verdict; "pass" requires every check to have run."""
    statuses = {c.status for c in checks}
    if "fail" in statuses:
        status: QCStatus = "fail"
    elif "warn" in statuses:
        status = "warn"
    elif statuses == {"pass"}:
        status = "pass"
    else:
        status = "unavailable"
    return QCBlock(status=status, checks=checks)


# --- cross-checks (heuristics; the detail text says so) ------------------------

def _rainfall_agreement(station: StationSnapshot, weather: WeatherSnapshot | None) -> CrossCheck:
    if weather is None:
        return CrossCheck(
            id="rainfall_agreement", status="unavailable",
            detail="No rainfall forecast stored for this province; heuristic cross-check skipped.",
            detail_kh="គ្មានព្យាករណ៍ភ្លៀងសម្រាប់ខេត្តនេះទេ — ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មានត្រូវបានឆ្លងកាត់។",
        )
    rate = station.rate_of_rise_m_per_hr
    rain = weather.precipitation_48h_mm
    rising = rate >= RISE_EPSILON_M_PER_HR
    rainy = rain >= RAIN_ADVISORY_48H_MM
    agree = rising == rainy
    if rising:
        detail = (
            f"Heuristic: river rising {rate:+.2f} m/hr "
            + (f"matches {rain:.0f} mm rain forecast (48 h)." if rainy
               else f"but only {rain:.0f} mm rain forecast (48 h).")
        )
        detail_kh = (
            f"ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មាន៖ ទឹកកំពុងឡើង {rate:+.2f} ម៉ែត្រ/ម៉ោង "
            + (f"ស្របនឹងភ្លៀងព្យាករណ៍ {rain:.0f} មីលីម៉ែត្រ (48 ម៉ោង)។" if rainy
               else f"តែភ្លៀងព្យាករណ៍មានតែ {rain:.0f} មីលីម៉ែត្រ (48 ម៉ោង)។")
        )
    else:
        detail = (
            f"Heuristic: river not rising ({rate:+.2f} m/hr) "
            + (f"while {rain:.0f} mm rain is forecast (48 h)." if rainy
               else f"with light rain forecast ({rain:.0f} mm, 48 h).")
        )
        detail_kh = (
            f"ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មាន៖ ទឹកមិនឡើង ({rate:+.2f} ម៉ែត្រ/ម៉ោង) "
            + (f"តែភ្លៀងព្យាករណ៍ {rain:.0f} មីលីម៉ែត្រ (48 ម៉ោង)។" if rainy
               else f"ទន្ទឹមនឹងភ្លៀងតិចតួច ({rain:.0f} មីលីម៉ែត្រ 48 ម៉ោង)។")
        )
    return CrossCheck(
        id="rainfall_agreement", status="agree" if agree else "disagree",
        detail=detail, detail_kh=detail_kh,
    )


_DIRECTION_EN = {1: "rising", 0: "steady", -1: "falling"}
_DIRECTION_KH = {1: "កំពុងឡើង", 0: "នៅស្ថេរភាព", -1: "កំពុងស្រក"}


def _trend_24h(series: list[tuple[datetime, float, float | None]]) -> tuple[int, float] | None:
    """Sign and rate (m/hr) of the series' net change, None when too short."""
    if len(series) < 2:
        return None
    span_h = (series[-1][0] - series[0][0]).total_seconds() / 3600.0
    if span_h < 1.0:
        return None
    rate = (series[-1][1] - series[0][1]) / span_h
    if rate >= RISE_EPSILON_M_PER_HR:
        return 1, rate
    if rate <= -RISE_EPSILON_M_PER_HR:
        return -1, rate
    return 0, rate


async def _upstream_coherence(
    pipeline: Pipeline,
    station: StationSnapshot,
    own_series: list[tuple[datetime, float, float | None]],
) -> CrossCheck:
    own = _trend_24h(own_series)
    if own is None:
        return CrossCheck(
            id="upstream_coherence", status="unavailable",
            detail="Local series too short for a 24 h trend; heuristic cross-check skipped.",
            detail_kh="ទិន្នន័យនៅទីនេះខ្លីពេកសម្រាប់រកទិសដៅ 24 ម៉ោង — ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មានត្រូវបានឆ្លងកាត់។",
        )
    stations = load_stations(str(pipeline.settings.data_dir))
    cfg = stations.get(station.station_id)
    if cfg is None:
        return CrossCheck(
            id="upstream_coherence", status="unavailable",
            detail="Station not in the configured roster; heuristic cross-check skipped.",
            detail_kh="ស្ថានីយ៍នេះមិនស្ថិតក្នុងបញ្ជីដែលបានកំណត់ទេ — ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មានត្រូវបានឆ្លងកាត់។",
        )
    others = sorted(
        (s for sid, s in stations.items() if sid != station.station_id),
        key=lambda s: _haversine_km(cfg.lat, cfg.lng, s.lat, s.lng),
    )
    for other in others:
        peer = _trend_24h(await pipeline.repo.telemetry_series(other.id, CROSS_CHECK_WINDOW_HOURS))
        if peer is None:
            continue  # nearest station with data, not merely the nearest station
        distance_km = _haversine_km(cfg.lat, cfg.lng, other.lat, other.lng)
        own_word, peer_word = _DIRECTION_EN[own[0]], _DIRECTION_EN[peer[0]]
        disagree = own[0] * peer[0] == -1  # flat is compatible with either direction
        if disagree:
            detail = (
                f"Heuristic: 24 h trends disagree ({own_word} here vs {peer_word} at "
                f"{other.name_en}, {distance_km:.0f} km away)."
            )
            detail_kh = (
                f"ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មាន៖ ទិសដៅទឹក 24 ម៉ោងមិនស្របគ្នា — {_DIRECTION_KH[own[0]]} "
                f"នៅទីនេះ តែ {_DIRECTION_KH[peer[0]]} នៅស្ថានីយ៍ {other.name_en} "
                f"(ចម្ងាយ {distance_km:.0f} គ.ម)។"
            )
        else:
            detail = (
                f"Heuristic: 24 h trend {own_word} here matches {other.name_en} "
                f"({distance_km:.0f} km away), also {peer_word}."
            )
            detail_kh = (
                f"ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មាន៖ ទិសដៅទឹក 24 ម៉ោង {_DIRECTION_KH[own[0]]} នៅទីនេះ "
                f"ស្របនឹងស្ថានីយ៍ {other.name_en} (ចម្ងាយ {distance_km:.0f} គ.ម) "
                f"ដែល{_DIRECTION_KH[peer[0]]}ផងដែរ។"
            )
        return CrossCheck(
            id="upstream_coherence", status="disagree" if disagree else "agree",
            detail=detail, detail_kh=detail_kh,
        )
    return CrossCheck(
        id="upstream_coherence", status="unavailable",
        detail="No other station has enough recent data; heuristic cross-check skipped.",
        detail_kh="គ្មានស្ថានីយ៍ផ្សេងទៀតមានទិន្នន័យថ្មីគ្រប់គ្រាន់ទេ — ការផ្ទៀងផ្ទាត់បែបប៉ាន់ស្មានត្រូវបានឆ្លងកាត់។",
    )


# --- confidence ----------------------------------------------------------------

def _confidence(
    station: StationSnapshot,
    freshness: Freshness,
    qc: QCBlock,
    commune: Commune,
    cross_checks: list[CrossCheck],
) -> tuple[Confidence, list[str]]:
    """Documented deterministic rules.

    Start high; downgrade one step per: stale/fallback telemetry (source, flag,
    or an old reading), any QC warn, a station beyond the water-surface proxy
    radius (risk.WATER_SURFACE_PROXY_MAX_KM), any cross-check disagreement.
    A QC fail drops straight to low: a failed series cannot support confidence.
    Positive ids record which checks held; missing ids (QC unavailable, all
    cross-checks unavailable, unknown distance) mean the check did not run, so
    nothing is claimed either way.
    """
    level = 2
    reasons: list[str] = []

    if station.is_stale_fallback or station.source in ("fallback", "cache") or freshness == "stale":
        level -= 1
        reasons.append("stale_telemetry")
    else:
        reasons.append("fresh_telemetry")

    if qc.status == "fail":
        reasons.append("qc_fail")
    elif qc.status == "warn":
        level -= 1
        reasons.append("qc_warning")
    elif qc.status == "pass":
        reasons.append("qc_clean")

    distance_km = commune.distance_to_station_km
    if distance_km is not None and distance_km > WATER_SURFACE_PROXY_MAX_KM:
        level -= 1
        reasons.append("far_from_station")
    elif distance_km is not None:
        reasons.append("near_station")

    if any(c.status == "disagree" for c in cross_checks):
        level -= 1
        reasons.append("source_disagree")
    elif any(c.status == "agree" for c in cross_checks):
        reasons.append("sources_agree")

    if qc.status == "fail":
        level = 0  # never claim more confidence than a failed series supports
    level = max(0, min(2, level))
    return ("low", "medium", "high")[level], reasons


# --- evidence chain --------------------------------------------------------------

_FRESHNESS_KH: dict[Freshness, str] = {"fresh": "ថ្មី", "recent": "មធ្យម", "stale": "ចាស់"}

_LIMITATIONS = Limitations(
    text_en=(
        "A station reading alone cannot say whether a specific field or floodplain is flooded. "
        "Low-lying areas may flood before the gauge reaches alarm level, and the accuracy of "
        "this evidence decays with distance from the station."
    ),
    text_kh=(
        "ការអានកម្រិតទឹកនៅស្ថានីយ៍តែម្នាក់ឯង មិនអាចបញ្ជាក់ថាស្រែ ឬតំបន់ទំនាបជាក់លាក់ណាមួយលិចនោះទេ។ "
        "តំបន់ទំនាបអាចលិចមុនពេលទឹកឡើងដល់កម្រិតប្រុងប្រយ័ត្ន ហើយភាពត្រឹមត្រូវនៃភស្តុតាងនេះ "
        "ថយចុះតាមចម្ងាយពីស្ថានីយ៍។"
    ),
)


def _chain(
    station: StationSnapshot,
    age_minutes: int,
    freshness: Freshness,
    risk: CommuneRisk,
    primary: Directive,
) -> list[ChainStep]:
    rate = station.rate_of_rise_m_per_hr
    level, alarm, flood = station.level_m, station.alarm_stage_m, station.flood_stage_m

    reading = ChainStep(
        id="reading",
        text_en=(
            f"{station.name} gauge ({station.station_id}): {level:.2f} m recorded "
            f"{station.recorded_at:%Y-%m-%d %H:%M} UTC, {age_minutes} min ago "
            f"({freshness}, source: {station.source})."
        ),
        text_kh=(
            f"ស្ថានីយ៍ {station.name} ({station.station_id})៖ កម្រិតទឹក {level:.2f} ម៉ែត្រ "
            f"កត់ត្រានៅម៉ោង {station.recorded_at:%H:%M} UTC ថ្ងៃទី {station.recorded_at:%d/%m/%Y} "
            f"អាយុ {age_minutes} នាទី ({_FRESHNESS_KH[freshness]}, ប្រភព៖ {station.source})។"
        ),
    )

    if rate >= RATE_PULSE_M_PER_HR:
        change = ChainStep(
            id="change",
            text_en=f"Change: rising fast {rate:.2f} m/hr over the last 3 h.",
            text_kh=f"ការប្រែប្រួល៖ ទឹកឡើងលឿន {rate:.2f} ម៉ែត្រ/ម៉ោង ក្នុង 3 ម៉ោងចុងក្រោយ។",
        )
    elif rate >= RISE_EPSILON_M_PER_HR:
        change = ChainStep(
            id="change",
            text_en=f"Change: rising {rate:.2f} m/hr over the last 3 h.",
            text_kh=f"ការប្រែប្រួល៖ ទឹកឡើង {rate:.2f} ម៉ែត្រ/ម៉ោង ក្នុង 3 ម៉ោងចុងក្រោយ។",
        )
    elif rate <= -RISE_EPSILON_M_PER_HR:
        change = ChainStep(
            id="change",
            text_en=f"Change: falling {abs(rate):.2f} m/hr over the last 3 h.",
            text_kh=f"ការប្រែប្រួល៖ ទឹកស្រក {abs(rate):.2f} ម៉ែត្រ/ម៉ោង ក្នុង 3 ម៉ោងចុងក្រោយ។",
        )
    else:
        change = ChainStep(
            id="change",
            text_en="Change: level steady over the last 3 h.",
            text_kh="ការប្រែប្រួល៖ កម្រិតទឹកនៅស្ថេរភាព ក្នុង 3 ម៉ោងចុងក្រោយ។",
        )

    if level >= flood:
        threshold = ChainStep(
            id="threshold",
            text_en=f"Threshold: {level:.2f} m is above the flood stage {flood:.2f} m.",
            text_kh=f"កម្រិតសំខាន់៖ កម្រិតទឹក {level:.2f} ម៉ែត្រ លើសកម្រិតគ្រោះថ្នាក់ {flood:.2f} ម៉ែត្រ។",
        )
    elif level >= alarm:
        threshold = ChainStep(
            id="threshold",
            text_en=f"Threshold: {level:.2f} m is above the alarm stage {alarm:.2f} m (flood {flood:.2f} m).",
            text_kh=f"កម្រិតសំខាន់៖ កម្រិតទឹក {level:.2f} ម៉ែត្រ លើសកម្រិតប្រុងប្រយ័ត្ន {alarm:.2f} ម៉ែត្រ (គ្រោះថ្នាក់ {flood:.2f} ម៉ែត្រ)។",
        )
    else:
        threshold = ChainStep(
            id="threshold",
            text_en=(
                f"Threshold: {level:.2f} m is {alarm - level:.2f} m below the alarm stage "
                f"{alarm:.2f} m (flood {flood:.2f} m)."
            ),
            text_kh=(
                f"កម្រិតសំខាន់៖ កម្រិតទឹក {level:.2f} ម៉ែត្រ ទាបជាងកម្រិតប្រុងប្រយ័ត្ន "
                f"{alarm - level:.2f} ម៉ែត្រ (គ្រោះថ្នាក់ {flood:.2f} ម៉ែត្រ)។"
            ),
        )

    lead = risk.lead_time_hours
    if lead is None:
        lead_en = " No meaningful lead time from the current rate of rise."
        lead_kh = " មិនមានការព្រមានជាមុនច្បាស់លាស់ពីអត្រាឡើងបច្ចុប្បន្ន។"
    elif lead <= 0:
        lead_en = " Lead time near zero: water may already be at ground level."
        lead_kh = " ការព្រមានជាមុនជិតសូន្យ៖ ទឹកអាចមកដល់ផ្ទៃដីរួចហើយ។"
    else:
        lead_en = f" Estimated lead time to flood stage: about {lead} hours."
        lead_kh = f" ការព្រមានជាមុនប្រហែល {lead} ម៉ោង មុនពេលទឹកដល់កម្រិតគ្រោះថ្នាក់។"
    tier = ChainStep(
        id="tier",
        text_en=f"Risk tier: {risk.tier.value} (score {risk.score}/100).{lead_en}",
        text_kh=f"កម្រិតហានិភ័យ៖ {risk.tier.label_kh} ({risk.tier.value}) ពិន្ទុ {risk.score}/100។{lead_kh}",
    )

    directive = ChainStep(
        id="directive",
        text_en=(
            f"Directive: primary action {primary.action_code} ({primary.title_en}) "
            f"for the default {DIRECTIVE_STAGE.value.lower()} stage."
        ),
        text_kh=(
            f"សកម្មភាពចម្បង៖ {primary.title_kh} ({primary.action_code}) "
            f"សម្រាប់ដំណាក់កាលលំនាំដើម {DIRECTIVE_STAGE.label_kh}។"
        ),
    )
    return [reading, change, threshold, tier, directive]


# --- payload --------------------------------------------------------------------

async def build_evidence(pipeline: Pipeline, commune_code: str) -> EvidencePayload:
    """Same resolution as `assess_commune`, plus provenance; no LLM, no audio."""
    commune = pipeline.gazetteer.get(commune_code) or await pipeline.repo.get_commune(commune_code)
    if commune is None:
        raise CommuneNotFound(commune_code)
    if not commune.nearest_station_id:
        raise AssessmentUnavailable(f"commune {commune_code} has no station assignment")

    station = await pipeline.repo.latest_observation(commune.nearest_station_id)
    if station is None:
        stations = load_stations(str(pipeline.settings.data_dir))
        cfg = stations.get(commune.nearest_station_id)
        if cfg is None:
            raise AssessmentUnavailable(f"station {commune.nearest_station_id} not configured")
        live = await pipeline.mrc.fetch_station(cfg.id)  # type: ignore[union-attr]
        await pipeline.repo.save_observation(live)
        station = live

    weather_by_province = await pipeline.repo.latest_weather_by_province()
    weather = weather_by_province.get(commune.province_code or "")
    risk = pipeline.classifier.classify(commune, station, weather)

    generated_at = datetime.now(timezone.utc)
    age_minutes = max(0, int((generated_at - station.recorded_at).total_seconds() // 60))
    freshness = _freshness(age_minutes)

    series = await pipeline.repo.telemetry_series(station.station_id, QC_WINDOW_HOURS)
    points = sorted((at, level) for at, level, _ in series)
    qc = _qc_block([
        _check_gaps(points),
        _check_stuck(points),
        _check_spike(points),
        _check_range(points, station),
    ])

    own_24h = [
        (at, level, rain)
        for at, level, rain in series
        if at >= generated_at - timedelta(hours=CROSS_CHECK_WINDOW_HOURS)
    ]
    cross_checks = [
        _rainfall_agreement(station, weather),
        await _upstream_coherence(pipeline, station, own_24h),
    ]

    confidence, confidence_reasons = _confidence(station, freshness, qc, commune, cross_checks)

    directives = pipeline.agri.evaluate(
        risk.tier,
        DIRECTIVE_STAGE,
        rain_48h_mm=weather.precipitation_48h_mm if weather else 0.0,
        soil_moisture_pct=weather.soil_moisture_pct if weather else None,
        lead_time_hours=risk.lead_time_hours,
    )

    return EvidencePayload(
        commune_code=commune.code,
        commune_name_kh=commune.name_kh,
        commune_name_en=commune.name_en,
        generated_at=generated_at,
        risk_tier=risk.tier,
        score=risk.score,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
        station=StationEvidence(
            station_id=station.station_id,
            name=station.name,
            distance_km=commune.distance_to_station_km,
            source=station.source,
            recorded_at=station.recorded_at,
            age_minutes=age_minutes,
            freshness=freshness,
            level_m=station.level_m,
            rate_of_rise_m_per_hr=station.rate_of_rise_m_per_hr,
            alarm_stage_m=station.alarm_stage_m,
            flood_stage_m=station.flood_stage_m,
        ),
        qc=qc,
        cross_checks=cross_checks,
        evidence_chain=_chain(station, age_minutes, freshness, risk, primary_directive(directives)),
        limitations=_LIMITATIONS,
    )
