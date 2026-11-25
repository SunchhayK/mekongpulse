"""Ingestion + assessment pipeline (FR-01, FR-02, FR-03, FR-05, INV-02, IMP-01..08).

`sync()` polls all configured stations (with pre-classification QC, adjacent-
station failover, and cached readings as last resort), refreshes province rain
forecasts and optional Google Flood Hub multi-day forecasts, applies per-commune
calibrated thresholds, classifies every commune, and persists the result,
returning tier transitions for the sentinel. `assess_commune()` is the on-demand
path shared by the API, the bot, and the advisor tools.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agronomy import AgriDecisionEngine, primary_directive
from .bulletin import BulletinBuilder, GeminiTextClient
from .cache import StateStore, create_state_store
from .config import Settings
from .flood_hub import FloodHubClient
from .logging_utils import log_event
from .models import (
    AssessmentResult,
    Commune,
    CommuneRisk,
    CropStage,
    CropType,
    Directive,
    FloodForecast,
    RiskTier,
    StationSnapshot,
    TelemetryWarning,
    WeatherSnapshot,
)
from .mrc import (
    MRCTelemetryClient,
    MRCTelemetryError,
    MRCValidationError,
    compute_hydraulic_offset,
)
from .repository import AudioStoreProtocol, Repository
from .risk import SpatialRiskClassifier
from .spatial import Gazetteer, load_gazetteer
from .stations import StationConfig, load_stations
from .telemetry import (
    emit_gauge_failover,
    emit_mrc_station_timeout,
    emit_telemetry_warning,
    emit_tts_unavailable,
    traced_span,
)
from .tts import AudioEncodeError, GeminiTTS, TTSUnavailable
from .verification import BigQueryExporter
from .weather import OpenMeteoClient, WeatherError

log = logging.getLogger("mekongpulse.pipeline")

# Bump when the TTS voice/model or signature semantics change.
AUDIO_CACHE_VERSION = "v3"


def _risk_changed(prev: CommuneRisk | None, current: CommuneRisk) -> bool:
    """True when a persisted risk row would actually change (timestamps excluded)."""
    if prev is None:
        return True
    return (
        prev.tier != current.tier
        or prev.score != current.score
        or prev.reason != current.reason
        or prev.lead_time_hours != current.lead_time_hours
        or prev.drivers != current.drivers
        or prev.station_id != current.station_id
        or prev.estimated != current.estimated
        or prev.forecast_tier != current.forecast_tier
        or prev.forecast_lead_days != current.forecast_lead_days
    )


def audio_cache_signature(
    commune_code: str,
    crop_stage: CropStage,
    risk: CommuneRisk,
    station: StationSnapshot | None,
    weather: WeatherSnapshot | None,
    directives: list[Directive],
) -> str:
    """Digest of the inputs the spoken bulletin is derived from."""
    parts = [
        commune_code,
        crop_stage.value,
        risk.tier.value,
        risk.reason.value,
        str(risk.lead_time_hours or 0),
    ]
    if station is not None:
        rate = station.rate_of_rise_m_per_hr
        rate_bucket = "fast" if rate >= 0.08 else "slow" if rate > 0.01 else "stable"
        parts += [
            station.station_id,
            f"{round(station.level_m, 1):.1f}",
            rate_bucket,
            f"{station.alarm_stage_m:.2f}",
            f"{station.flood_stage_m:.2f}",
        ]
    if weather is not None:
        rain_bucket = int(round(weather.precipitation_48h_mm / 5.0) * 5)
        parts.append(str(rain_bucket))
    parts += [f"{d.action_code}:{d.urgency.value}" for d in directives]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


class CommuneNotFound(Exception):
    pass


class AssessmentUnavailable(Exception):
    """Commune cannot be scored (no station assignment or no telemetry yet)."""


@dataclass
class SyncSummary:
    stations_polled: int
    stations_failed: list[str]
    warnings: list[TelemetryWarning]
    communes_evaluated: int
    communes_skipped: int
    risk_counts: dict[str, int]
    worst_tier: RiskTier | None
    duration_ms: int


@dataclass
class RiskTransition:
    commune: Commune
    previous: RiskTier | None
    current: CommuneRisk


@dataclass
class Pipeline:
    settings: Settings
    repo: Repository
    mrc: MRCTelemetryClient | None = None
    weather: OpenMeteoClient | None = None
    _gazetteer: Gazetteer | None = None
    classifier: SpatialRiskClassifier = field(default_factory=SpatialRiskClassifier)
    agri: AgriDecisionEngine = field(default_factory=AgriDecisionEngine)
    bulletin: BulletinBuilder | None = None
    tts: GeminiTTS | None = None
    audio_store: AudioStoreProtocol | None = None
    state_store: StateStore | None = None
    flood_hub: FloodHubClient | None = None
    bq_exporter: BigQueryExporter | None = None
    _weather_cache: tuple[float, dict[str, WeatherSnapshot]] | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.state_store is None:
            self.state_store = create_state_store(self.settings)
        if self.mrc is None:
            self.mrc = MRCTelemetryClient(
                self.settings.mrc_base_url, timeout=self.settings.http_timeout_seconds
            )
        if self.weather is None:
            self.weather = OpenMeteoClient(
                self.settings.open_meteo_base_url, timeout=self.settings.http_timeout_seconds
            )
        if self.bulletin is None:
            text_client = (
                GeminiTextClient(self.settings, state_store=self.state_store)
                if self.settings.has_gemini
                else None
            )
            self.bulletin = BulletinBuilder(text_client, state_store=self.state_store)
        if self.tts is None:
            self.tts = GeminiTTS(self.settings, state_store=self.state_store)
        if self.flood_hub is None:
            self.flood_hub = FloodHubClient(
                api_key=self.settings.flood_hub_api_key,
                base_url=self.settings.flood_hub_base_url,
                state_store=self.state_store,
                timeout=self.settings.http_timeout_seconds,
            )
        if self.bq_exporter is None:
            self.bq_exporter = BigQueryExporter(self.settings)

    @property
    def gazetteer(self) -> Gazetteer:
        if self._gazetteer is None:
            self._gazetteer = load_gazetteer(str(self.settings.data_dir))
        return self._gazetteer

    async def ensure_seeded(self) -> None:
        stations = load_stations(str(self.settings.data_dir))
        await self.repo.seed_stations(list(stations.values()))
        if await self.repo.commune_count() == 0:
            await self.repo.seed_communes(self.gazetteer.all_communes())

    # ---- sync -----------------------------------------------------------------
    async def sync(self, *, force_fallback: bool = False) -> tuple[SyncSummary, list[RiskTransition]]:
        with traced_span("pipeline.sync", {"force_fallback": force_fallback}):
            started = time.monotonic()
            warnings: list[TelemetryWarning] = []
            stations = load_stations(str(self.settings.data_dir))

            previous_by_code = {r.commune_code: r for r in await self.repo.risk_map()}
            previous = {code: r.tier for code, r in previous_by_code.items()}

            snapshots: dict[str, StationSnapshot] = {}
            failed: list[str] = []
            for cfg in stations.values():
                snapshot, station_warnings = await self.poll_station(
                    cfg, stations, force_fallback=force_fallback
                )
                warnings.extend(station_warnings)
                if snapshot is None:
                    failed.append(cfg.id)
                    continue
                snapshots[cfg.id] = snapshot
                await self.repo.save_observation(snapshot)

            await self._refresh_offsets(stations, snapshots, warnings)

            weather_by_province = await self._refresh_weather()
            flood_forecasts: dict[str, FloodForecast] = {}
            if self.flood_hub is not None and self.flood_hub.enabled:
                flood_forecasts = await self.flood_hub.fetch_forecasts_for_stations(stations)

            calibrations = await self.repo.list_commune_calibrations()

            risks: list[CommuneRisk] = []
            skipped = 0
            for commune in self.gazetteer.all_communes():
                station = snapshots.get(commune.nearest_station_id or "")
                if station is None:
                    skipped += 1
                    continue
                cal = calibrations.get(commune.code)
                risks.append(
                    self.classifier.classify(
                        commune,
                        station,
                        weather_by_province.get(commune.province_code or ""),
                        levee_margin_m=cal.levee_margin_m if cal is not None else None,
                        lead_time_multiplier=cal.lead_time_multiplier if cal is not None else 1.0,
                        flood_forecast=flood_forecasts.get(station.station_id),
                    )
                )
            if risks:
                changed = [
                    r for r in risks if _risk_changed(previous_by_code.get(r.commune_code), r)
                ]
                if changed:
                    await self.repo.save_commune_risks(changed)
                log_event(
                    log,
                    "RISK_WRITES",
                    communes_evaluated=len(risks),
                    written=len(changed),
                    unchanged=len(risks) - len(changed),
                )

            if self.bq_exporter is not None and self.bq_exporter.enabled and snapshots:
                await self.bq_exporter.export_observations(list(snapshots.values()))

            transitions: list[RiskTransition] = []
            for r in risks:
                prev = previous.get(r.commune_code)
                if prev == r.tier:
                    continue
                commune = self.gazetteer.get(r.commune_code)
                if commune is None:  # pragma: no cover - defensive
                    continue
                transitions.append(RiskTransition(commune=commune, previous=prev, current=r))

            counts: dict[str, int] = {}
            for r in risks:
                counts[r.tier.value] = counts.get(r.tier.value, 0) + 1
            worst = max((r.tier for r in risks), key=lambda t: t.severity, default=None)
            duration_ms = int((time.monotonic() - started) * 1000)
            summary = SyncSummary(
                stations_polled=len(snapshots),
                stations_failed=failed,
                warnings=warnings,
                communes_evaluated=len(risks),
                communes_skipped=skipped,
                risk_counts=counts,
                worst_tier=worst,
                duration_ms=duration_ms,
            )
            log_event(
                log,
                "TELEMETRY_SYNC",
                stations_polled=len(snapshots),
                stations_failed=failed,
                communes_evaluated=len(risks),
                communes_skipped=skipped,
                warnings=len(warnings),
                worst_tier=worst.value if worst else None,
                duration_ms=duration_ms,
            )
            return summary, transitions

    async def poll_station(
        self,
        cfg: StationConfig,
        stations: dict[str, StationConfig],
        *,
        force_fallback: bool = False,
    ) -> tuple[StationSnapshot | None, list[TelemetryWarning]]:
        """Live (with range/spike QC) -> adjacent-station fallback -> cached reading.

        Every outcome is persisted as a telemetry warning (INV-02 / AC-06).
        """
        snapshot, warnings = await self._poll_station_inner(
            cfg, stations, force_fallback=force_fallback
        )
        for warning in warnings:
            await self.repo.save_telemetry_warning(warning)
        return snapshot, warnings

    async def _poll_station_inner(
        self,
        cfg: StationConfig,
        stations: dict[str, StationConfig],
        *,
        force_fallback: bool = False,
    ) -> tuple[StationSnapshot | None, list[TelemetryWarning]]:
        warnings: list[TelemetryWarning] = []
        now = datetime.now(timezone.utc)

        if not force_fallback:
            try:
                return await self.mrc.fetch_station(cfg.id), warnings  # type: ignore[union-attr]
            except MRCValidationError as exc:
                warnings.append(
                    TelemetryWarning(
                        station_id=cfg.id, kind=exc.kind, detail=str(exc), created_at=now
                    )
                )
                emit_telemetry_warning(cfg.id, exc.kind, str(exc))
            except MRCTelemetryError as exc:
                warnings.append(
                    TelemetryWarning(
                        station_id=cfg.id, kind="STATION_UNAVAILABLE", detail=str(exc), created_at=now
                    )
                )
                emit_mrc_station_timeout(cfg.id, str(exc))

        fallback_id = cfg.fallback_id
        if fallback_id and fallback_id in stations and fallback_id != cfg.id:
            try:
                fallback_snapshot = await self.mrc.fetch_station(fallback_id)  # type: ignore[union-attr]
                offset = await self._effective_offset(cfg.id, fallback_id)
                if offset is not None:
                    derived = fallback_snapshot.model_copy(
                        update={
                            "station_id": cfg.id,
                            "name": cfg.name_en,
                            "river": cfg.river,
                            "level_m": round(fallback_snapshot.level_m + offset, 3),
                            "alarm_stage_m": cfg.alarm_stage_m,
                            "flood_stage_m": cfg.flood_stage_m,
                            "is_stale_fallback": True,
                            "source": "fallback",
                            "fallback_offset_m": offset,
                        }
                    )
                    warnings.append(
                        TelemetryWarning(
                            station_id=cfg.id,
                            kind="FALLBACK_USED",
                            detail=f"fell back to {fallback_id} with offset {offset:+.3f}m",
                            created_at=now,
                        )
                    )
                    emit_gauge_failover(cfg.id, "fallback", fallback_id)
                    return derived, warnings
            except MRCTelemetryError as exc:
                warnings.append(
                    TelemetryWarning(
                        station_id=cfg.id,
                        kind="FALLBACK_FAILED",
                        detail=f"fallback {fallback_id} failed: {exc}",
                        created_at=now,
                    )
                )

        cached = await self.repo.latest_observation(cfg.id)
        if cached is not None:
            cached = cached.model_copy(
                update={
                    "is_stale_fallback": True,
                    "source": "cache",
                    "staleness_minutes": cached.staleness_minutes or 0,
                }
            )
            warnings.append(
                TelemetryWarning(
                    station_id=cfg.id,
                    kind="CACHE_USED",
                    detail=f"live and fallback unavailable; cached reading from {cached.recorded_at.isoformat()}",
                    created_at=now,
                )
            )
            emit_gauge_failover(cfg.id, "cache")
            return cached, warnings

        warnings.append(
            TelemetryWarning(
                station_id=cfg.id,
                kind="STATION_DROPPED",
                detail="live, fallback, and cache all unavailable; station skipped",
                created_at=now,
            )
        )
        return None, warnings

    async def _effective_offset(self, station_id: str, fallback_id: str) -> float | None:
        """Stored offset, else empirical median over stored overlapping series."""
        stored = await self.repo.get_failover_offset(station_id)
        if stored is not None:
            return stored
        hours = 24 * 30
        try:
            primary_series = await self.repo.telemetry_series(station_id, hours)
            fallback_series = await self.repo.telemetry_series(fallback_id, hours)
        except Exception:  # noqa: BLE001 - offsets are best-effort
            return None
        from .mrc import Measurement

        primary = [Measurement(at=at, level_m=w) for at, w, _ in primary_series]
        fallback = [Measurement(at=at, level_m=w) for at, w, _ in fallback_series]
        offset = compute_hydraulic_offset(primary, fallback)
        if offset is not None:
            await self.repo.save_failover_offset(station_id, fallback_id, offset)
            log_event(
                log,
                "FAILOVER_OFFSET_COMPUTED",
                station_id=station_id,
                fallback_id=fallback_id,
                offset_m=offset,
            )
        return offset

    async def _refresh_offsets(
        self,
        stations: dict[str, StationConfig],
        snapshots: dict[str, StationSnapshot],
        warnings: list[TelemetryWarning],
    ) -> None:
        """Compute any missing failover offsets while stations are healthy."""
        for cfg in stations.values():
            if not cfg.fallback_id or cfg.fallback_id not in stations:
                continue
            if await self.repo.get_failover_offset(cfg.id) is not None:
                continue
            if cfg.id not in snapshots or cfg.fallback_id not in snapshots:
                continue
            try:
                primary_series = await self.mrc.fetch_series(cfg.id)  # type: ignore[union-attr]
                fallback_series = await self.mrc.fetch_series(cfg.fallback_id)  # type: ignore[union-attr]
            except MRCTelemetryError:
                continue
            offset = compute_hydraulic_offset(primary_series, fallback_series)
            if offset is not None:
                await self.repo.save_failover_offset(cfg.id, cfg.fallback_id, offset)

    async def _refresh_weather(self) -> dict[str, WeatherSnapshot]:
        now = time.monotonic()
        if self._weather_cache is not None:
            cached_at, cached = self._weather_cache
            if now - cached_at < self.settings.weather_refresh_minutes * 60:
                return cached

        if self.state_store is not None:
            stored = await self.state_store.get_json("weather:all_provinces")
            if isinstance(stored, dict) and stored:
                try:
                    restored = {k: WeatherSnapshot.model_validate(v) for k, v in stored.items()}
                    self._weather_cache = (now, restored)
                    return restored
                except Exception:  # noqa: BLE001
                    pass

        province_points = self.gazetteer.province_points()
        fetched: dict[str, WeatherSnapshot] = {}
        semaphore = asyncio.Semaphore(5)

        async def fetch(code: str, lat: float, lng: float) -> None:
            async with semaphore:
                try:
                    snapshot = await self.weather.fetch_forecast(code, lat, lng)  # type: ignore[union-attr]
                except WeatherError as exc:
                    log_event(log, "WEATHER_FETCH_FAILED", province=code, error=str(exc))
                    return
                fetched[code] = snapshot
                await self.repo.save_weather(snapshot)

        await asyncio.gather(
            *(fetch(code, lat, lng) for code, (lat, lng) in province_points.items())
        )
        merged = await self.repo.latest_weather_by_province()
        merged.update(fetched)
        # Only cache a complete pass; a failed province retries on the next sync.
        if len(fetched) == len(province_points):
            self._weather_cache = (now, merged)
            if self.state_store is not None:
                await self.state_store.set_json(
                    "weather:all_provinces",
                    {k: v.model_dump(mode="json") for k, v in merged.items()},
                    ttl_seconds=self.settings.weather_refresh_minutes * 60,
                )
        return merged

    # ---- on-demand assessment ---------------------------------------------------
    async def assess_commune(
        self,
        commune_code: str,
        crop_stage: CropStage,
        *,
        with_audio: bool = False,
        force_audio: bool = False,
        crop_type: CropType = CropType.RICE,
    ) -> AssessmentResult:
        with traced_span(
            "pipeline.assess_commune",
            {"commune_code": commune_code, "crop_stage": crop_stage.value},
        ):
            commune = self.gazetteer.get(commune_code) or await self.repo.get_commune(commune_code)
            if commune is None:
                raise CommuneNotFound(commune_code)
            if not commune.nearest_station_id:
                raise AssessmentUnavailable(f"commune {commune_code} has no station assignment")

            station = await self.repo.latest_observation(commune.nearest_station_id)
            stations = load_stations(str(self.settings.data_dir))
            if station is None:
                cfg = stations.get(commune.nearest_station_id)
                if cfg is None:
                    raise AssessmentUnavailable(f"station {commune.nearest_station_id} not configured")
                live = await self.mrc.fetch_station(cfg.id)  # type: ignore[union-attr]
                await self.repo.save_observation(live)
                station = live

            weather_by_province = await self.repo.latest_weather_by_province()
            weather = weather_by_province.get(commune.province_code or "")

            calibrations = await self.repo.list_commune_calibrations()
            cal = calibrations.get(commune.code)

            flood_forecast: FloodForecast | None = None
            if self.flood_hub is not None and self.flood_hub.enabled:
                cfg = stations.get(station.station_id)
                if cfg is not None:
                    flood_forecast = await self.flood_hub.fetch_station_forecast(
                        cfg.id, cfg.lat, cfg.lng
                    )

            risk = self.classifier.classify(
                commune,
                station,
                weather,
                levee_margin_m=cal.levee_margin_m if cal is not None else None,
                lead_time_multiplier=cal.lead_time_multiplier if cal is not None else 1.0,
                flood_forecast=flood_forecast,
            )
            directives = self.agri.evaluate(
                risk.tier,
                crop_stage,
                rain_48h_mm=weather.precipitation_48h_mm if weather else 0.0,
                soil_moisture_pct=weather.soil_moisture_pct if weather else None,
                lead_time_hours=risk.lead_time_hours,
                crop_type=crop_type,
            )
            kh, en = await self.bulletin.build(  # type: ignore[union-attr]
                commune, risk, directives, station, weather, force_polish=force_audio
            )

            audio = None
            if with_audio:
                audio = await self._synthesize_audio(
                    commune_code,
                    risk,
                    kh,
                    audio_cache_signature(
                        commune_code, crop_stage, risk, station, weather, directives
                    ),
                    force=force_audio,
                )

            return AssessmentResult(
                commune_code=commune.code,
                commune_name_kh=commune.name_kh,
                commune_name_en=commune.name_en,
                risk_tier=risk.tier,
                score=risk.score,
                lead_time_hours=risk.lead_time_hours,
                directive=primary_directive(directives).action_code,
                directives=directives,
                khmer_bulletin=kh,
                english_bulletin=en,
                audio=audio,
                estimated=risk.estimated,
                generated_at=datetime.now(timezone.utc),
            )

    async def _synthesize_audio(
        self,
        commune_code: str,
        risk: CommuneRisk,
        bulletin_kh: str,
        cache_signature: str,
        *,
        force: bool = False,
    ):
        if self.audio_store is None:
            return None
        key = f"{commune_code}/{AUDIO_CACHE_VERSION}-{cache_signature}.mp3"
        if not force:
            try:
                cached = await self.audio_store.head(key)
            except Exception as exc:  # noqa: BLE001 - a cache probe must never break assessment
                log_event(log, "TTS_CACHE_ERROR", commune=commune_code, error=str(exc))
                cached = None
            if cached is not None:
                log_event(log, "TTS_CACHE_HIT", commune=commune_code, tier=risk.tier.value)
                return cached
        try:
            artifact = await self.tts.synthesize(bulletin_kh)  # type: ignore[union-attr]
        except (TTSUnavailable, AudioEncodeError) as exc:
            emit_tts_unavailable(commune_code, str(exc))
            return None
        ref = await self.audio_store.put(key, artifact.data, artifact.mime_type)
        log_event(
            log,
            "TTS_SYNTHESIZED",
            commune=commune_code,
            tier=risk.tier.value,
            forced=force,
        )
        return ref.model_copy(update={"duration_seconds": artifact.duration_seconds})
