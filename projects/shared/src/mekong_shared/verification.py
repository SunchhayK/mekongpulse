"""Ground-truth verification, threshold calibration, and BigQuery export (IMP-07).

Pairs historical `SentinelAlert` dispatches against `FieldReport` observations
to compute precision, recall, false-alarm counts, and lead-time error, and
produces per-commune `CommuneCalibration` adjustments (`levee_margin_m`,
`lead_time_multiplier`). Also provides `BigQueryExporter` for streaming domain
rows into BigQuery (graceful no-op when `bigquery_dataset` is unset).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .logging_utils import log_event
from .models import (
    CommuneCalibration,
    FieldReport,
    FieldReportStatus,
    RiskTier,
    SentinelAlert,
    StationSnapshot,
    VerificationSummary,
    WeatherSnapshot,
)

log = logging.getLogger("mekongpulse.verification")

DEFAULT_LEVEE_MARGIN_M = 0.30
MIN_LEVEE_MARGIN_M = 0.10
MAX_LEVEE_MARGIN_M = 1.00
MIN_LEAD_TIME_MULTIPLIER = 0.50
MAX_LEAD_TIME_MULTIPLIER = 2.00


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_verification_summary(
    alerts: list[SentinelAlert],
    reports: list[FieldReport],
    *,
    match_window_hours: float = 72.0,
) -> VerificationSummary:
    """Compute overall and per-commune precision, recall, and lead-time error."""
    window = timedelta(hours=match_window_hours)

    alerts_by_commune: dict[str, list[SentinelAlert]] = defaultdict(list)
    for alert in alerts:
        if alert.risk_tier.at_least(RiskTier.WARNING):
            alerts_by_commune[alert.commune_id].append(alert)

    reports_by_commune: dict[str, list[FieldReport]] = defaultdict(list)
    for report in reports:
        if report.status in (FieldReportStatus.WATER_REACHED, FieldReportStatus.NO_WATER):
            reports_by_commune[report.commune_code].append(report)

    communes = sorted(set(alerts_by_commune) | set(reports_by_commune))

    total_alerts = 0
    total_matched_reports = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0
    all_lead_errors: list[float] = []
    by_commune: dict[str, dict[str, Any]] = {}

    for code in communes:
        c_alerts = sorted(alerts_by_commune.get(code, []), key=lambda a: _utc(a.dispatched_at))
        c_reports = sorted(reports_by_commune.get(code, []), key=lambda r: _utc(r.reported_at))

        tp = 0
        fp = 0
        fn = 0
        matched_report_ids: set[str] = set()
        lead_errors: list[float] = []

        for alert in c_alerts:
            dispatched = _utc(alert.dispatched_at)
            in_window = [
                r
                for r in c_reports
                if dispatched <= _utc(r.reported_at) <= dispatched + window
            ]
            water_reports = [r for r in in_window if r.status is FieldReportStatus.WATER_REACHED]
            no_water_reports = [r for r in in_window if r.status is FieldReportStatus.NO_WATER]

            if water_reports:
                tp += 1
                for r in water_reports:
                    matched_report_ids.add(r.id)
                if alert.lead_time_hours is not None:
                    first_arrival = _utc(water_reports[0].reported_at)
                    actual_hours = (first_arrival - dispatched).total_seconds() / 3600.0
                    lead_errors.append(abs(actual_hours - float(alert.lead_time_hours)))
            elif no_water_reports:
                fp += 1
                for r in no_water_reports:
                    matched_report_ids.add(r.id)

        # Unwarned flood events (water_reached with no prior alert in window) -> FN
        for report in c_reports:
            if report.status is not FieldReportStatus.WATER_REACHED:
                continue
            reported = _utc(report.reported_at)
            had_alert = any(
                _utc(a.dispatched_at) <= reported <= _utc(a.dispatched_at) + window
                for a in c_alerts
            )
            if not had_alert:
                fn += 1

        c_precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        c_recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None
        c_mean_err = round(sum(lead_errors) / len(lead_errors), 2) if lead_errors else None

        by_commune[code] = {
            "total_alerts": len(c_alerts),
            "matched_reports": len(matched_report_ids),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": c_precision,
            "recall": c_recall,
            "mean_lead_time_error_hours": c_mean_err,
        }

        total_alerts += len(c_alerts)
        total_matched_reports += len(matched_report_ids)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        all_lead_errors.extend(lead_errors)

    precision = round(total_tp / (total_tp + total_fp), 4) if (total_tp + total_fp) > 0 else None
    recall = round(total_tp / (total_tp + total_fn), 4) if (total_tp + total_fn) > 0 else None
    mean_err = (
        round(sum(all_lead_errors) / len(all_lead_errors), 2) if all_lead_errors else None
    )

    return VerificationSummary(
        total_alerts=total_alerts,
        matched_reports=total_matched_reports,
        true_positives=total_tp,
        false_positives=total_fp,
        false_negatives=total_fn,
        precision=precision,
        recall=recall,
        mean_lead_time_error_hours=mean_err,
        by_commune=by_commune,
    )


def calibrate_commune_thresholds(
    alerts: list[SentinelAlert],
    reports: list[FieldReport],
    existing: dict[str, CommuneCalibration] | None = None,
    *,
    default_levee_margin_m: float = DEFAULT_LEVEE_MARGIN_M,
    match_window_hours: float = 72.0,
) -> list[CommuneCalibration]:
    """Calibrate per-commune levee_margin_m and lead_time_multiplier from paired data."""
    summary = compute_verification_summary(alerts, reports, match_window_hours=match_window_hours)
    existing_map = existing or {}
    window = timedelta(hours=match_window_hours)
    now = datetime.now(timezone.utc)

    # Compute per-commune actual/predicted lead-time ratios where available
    alerts_by_commune: dict[str, list[SentinelAlert]] = defaultdict(list)
    for alert in alerts:
        if alert.risk_tier.at_least(RiskTier.WARNING):
            alerts_by_commune[alert.commune_id].append(alert)
    reports_by_commune: dict[str, list[FieldReport]] = defaultdict(list)
    for report in reports:
        if report.status is FieldReportStatus.WATER_REACHED:
            reports_by_commune[report.commune_code].append(report)

    calibrations: list[CommuneCalibration] = []
    for code, stats in summary.by_commune.items():
        tp = int(stats["true_positives"])
        fp = int(stats["false_positives"])
        fn = int(stats["false_negatives"])
        sample_size = tp + fp + fn
        if sample_size == 0:
            continue

        prev = existing_map.get(code)
        base_margin = prev.levee_margin_m if prev is not None else default_levee_margin_m
        base_mult = prev.lead_time_multiplier if prev is not None else 1.0

        # False negatives (missed floods) widen the safety margin; false alarms tighten it.
        margin = base_margin + (0.10 * fn) - (0.05 * fp)
        margin = round(max(MIN_LEVEE_MARGIN_M, min(MAX_LEVEE_MARGIN_M, margin)), 3)

        ratios: list[float] = []
        c_reports = sorted(reports_by_commune.get(code, []), key=lambda r: _utc(r.reported_at))
        for alert in alerts_by_commune.get(code, []):
            if not alert.lead_time_hours or alert.lead_time_hours <= 0:
                continue
            dispatched = _utc(alert.dispatched_at)
            matched = [
                r for r in c_reports if dispatched <= _utc(r.reported_at) <= dispatched + window
            ]
            if matched:
                actual_hours = (_utc(matched[0].reported_at) - dispatched).total_seconds() / 3600.0
                if actual_hours > 0:
                    ratios.append(actual_hours / float(alert.lead_time_hours))

        if ratios:
            avg_ratio = sum(ratios) / len(ratios)
            mult = 0.5 * base_mult + 0.5 * avg_ratio
            mult = round(max(MIN_LEAD_TIME_MULTIPLIER, min(MAX_LEAD_TIME_MULTIPLIER, mult)), 3)
        else:
            mult = round(base_mult, 3)

        calibrations.append(
            CommuneCalibration(
                commune_code=code,
                levee_margin_m=margin,
                lead_time_multiplier=mult,
                sample_size=sample_size,
                updated_at=now,
            )
        )
    return calibrations


class BigQueryExporter:
    """Best-effort streaming exporter to BigQuery; no-op when dataset is unset."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self._settings = settings
        self._dataset = getattr(settings, "bigquery_dataset", None)
        self._project = (
            getattr(settings, "bigquery_project", None)
            or settings.vertex_project
            or settings.firestore_project
        )
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self._dataset)

    def _get_client(self) -> Any | None:
        if not self._dataset:
            return None
        if self._client is None:
            try:
                from google.cloud import bigquery  # type: ignore[import-untyped]
            except ImportError:
                log_event(log, "BIGQUERY_UNAVAILABLE", detail="google-cloud-bigquery not installed")
                return None
            self._client = bigquery.Client(project=self._project) if self._project else bigquery.Client()
        return self._client

    def _table_id(self, table: str) -> str:
        if self._project:
            return f"{self._project}.{self._dataset}.{table}"
        return f"{self._dataset}.{table}"

    async def _insert(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows or not self._dataset:
            return 0
        client = self._get_client()
        if client is None:
            return 0
        table_id = self._table_id(table)
        try:
            errors = await asyncio.to_thread(client.insert_rows_json, table_id, rows)
        except Exception as exc:  # noqa: BLE001 - analytics export must never break core flows
            log_event(log, "BIGQUERY_EXPORT_FAILED", table=table_id, error=str(exc))
            return 0
        if errors:
            log_event(log, "BIGQUERY_EXPORT_ERRORS", table=table_id, count=len(errors))
            return max(0, len(rows) - len(errors))
        return len(rows)

    async def export_observations(self, snapshots: list[StationSnapshot]) -> int:
        rows = [
            {
                "station_id": s.station_id,
                "name": s.name,
                "river": s.river,
                "level_m": s.level_m,
                "alarm_stage_m": s.alarm_stage_m,
                "flood_stage_m": s.flood_stage_m,
                "rate_of_rise_m_per_hr": s.rate_of_rise_m_per_hr,
                "rain_mm": s.rain_mm,
                "source": s.source,
                "is_stale_fallback": s.is_stale_fallback,
                "recorded_at": _utc(s.recorded_at).isoformat(),
            }
            for s in snapshots
        ]
        return await self._insert("hydro_observations", rows)

    async def export_weather(self, snapshots: list[WeatherSnapshot]) -> int:
        rows = [
            {
                "province_code": w.province_code,
                "latitude": w.latitude,
                "longitude": w.longitude,
                "precipitation_48h_mm": w.precipitation_48h_mm,
                "precipitation_7d_mm": w.precipitation_7d_mm,
                "max_rain_24h_mm": w.max_rain_24h_mm,
                "soil_moisture_pct": w.soil_moisture_pct,
                "fetched_at": _utc(w.fetched_at).isoformat(),
            }
            for w in snapshots
        ]
        return await self._insert("weather_forecasts", rows)

    async def export_alerts(self, alerts: list[SentinelAlert]) -> int:
        rows = [
            {
                "alert_id": str(a.id) if a.id is not None else None,
                "patrol_run_id": str(a.patrol_run_id) if a.patrol_run_id is not None else None,
                "commune_id": a.commune_id,
                "station_id": a.station_id,
                "risk_tier": a.risk_tier.value,
                "lead_time_hours": a.lead_time_hours,
                "directive_title": a.directive_title,
                "recipients_count": a.recipients_count,
                "dispatched_at": _utc(a.dispatched_at).isoformat(),
            }
            for a in alerts
        ]
        return await self._insert("sentinel_alerts", rows)

    async def export_field_reports(self, reports: list[FieldReport]) -> int:
        rows = [
            {
                "report_id": r.id,
                "commune_code": r.commune_code,
                "status": r.status.value,
                "note": r.note,
                "reporter_label": r.reporter_label,
                "source": r.source,
                "reported_at": _utc(r.reported_at).isoformat(),
            }
            for r in reports
        ]
        return await self._insert("field_reports", rows)
