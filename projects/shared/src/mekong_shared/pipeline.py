"""Ingestion + assessment pipeline (FR-01, FR-02, FR-03, FR-05, INV-02).

`sync()` polls all four stations (with adjacent-station failover and cached
readings as last resort), refreshes the province rain forecasts, classifies
every commune, and persists the result, returning the tier transitions for the
sentinel. `assess_commune()` is the on-demand path shared by the API, the bot,
and the advisor tools.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agronomy import AgriDecisionEngine, primary_directive
from .bulletin import BulletinBuilder, GeminiTextClient
from .config import Settings
from .logging_utils import log_event
from .models import (
    AssessmentResult,
    Commune,
    CommuneRisk,
    CropStage,
    Directive,
    RiskTier,
    StationSnapshot,
    TelemetryWarning,
    WeatherSnapshot,
)
from .mrc import MRCTelemetryClient, MRCTelemetryError, compute_hydraulic_offset
from .repository import AudioStoreProtocol, Repository
from .risk import SpatialRiskClassifier
from .spatial import Gazetteer, load_gazetteer
from .stations import StationConfig, load_stations
from .tts import AudioEncodeError, GeminiTTS, TTSUnavailable
from .weather import OpenMeteoClient, WeatherError

import logging

log = logging.getLogger("mekongpulse.pipeline")

# Bump when the TTS voice/model changes so cached bulletins are not reused.
AUDIO_CACHE_VERSION = "v1"


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
    )


def audio_cache_signature(
    commune_code: str,
    crop_stage: CropStage,
    risk: CommuneRisk,
    station: StationSnapshot | None,
    weather: WeatherSnapshot | None,
    directives: list[Directive],
) -> str:
    """Digest of the inputs the spoken bulletin is derived from.

    The Khmer text may be LLM-polished, so its wording is not stable across
    requests; hashing the final text would miss the cache every time. The
    deterministic inputs are, so identical situations reuse one MP3.
    """
    parts = [
        commune_code,
        crop_stage.value,
        risk.tier.value,
        f"{risk.score:.1f}",
        risk.reason.value,
        str(risk.lead_time_hours or 0),
    ]
    if station is not None:
        parts += [
            station.station_id,
            f"{station.level_m:.2f}",
            f"{station.rate_of_rise_m_per_hr:.2f}",
            f"{station.alarm_stage_m:.2f}",
            f"{station.flood_stage_m:.2f}",
        ]
    if weather is not None:
        parts.append(f"{weather.precipitation_48h_mm:.0f}")
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
    _weather_cache: tuple[float, dict[str, WeatherSnapshot]] | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
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
                GeminiTextClient(self.settings) if self.settings.has_gemini else None
            )
            self.bulletin = BulletinBuilder(text_client)
        if self.tts is None:
            self.tts = GeminiTTS(self.settings)

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

        risks: list[CommuneRisk] = []
        skipped = 0
        for commune in self.gazetteer.all_communes():
            station = snapshots.get(commune.nearest_station_id or "")
            if station is None:
                skipped += 1
                continue
            risks.append(
                self.classifier.classify(
                    commune, station, weather_by_province.get(commune.province_code or "")
                )
            )
        if risks:
            changed = [r for r in risks if _risk_changed(previous_by_code.get(r.commune_code), r)]
            if changed:
                await self.repo.save_commune_risks(changed)
            log_event(
                log,
                "RISK_WRITES",
                communes_evaluated=len(risks),
                written=len(changed),
                unchanged=len(risks) - len(changed),
            )

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
        """Live -> adjacent-station fallback (empirical offset) -> cached reading.

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
            except MRCTelemetryError as exc:
                warnings.append(
                    TelemetryWarning(
                        station_id=cfg.id, kind="STATION_UNAVAILABLE", detail=str(exc), created_at=now
                    )
                )
                log_event(log, "MRC_STATION_TIMEOUT", station_id=cfg.id, error=str(exc))

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
                    return derived, warnings
            except MRCTelemetryError as exc:
                warnings.append(
                    TelemetryWarning(
                        station_id=cfg.id, kind="FALLBACK_FAILED",
                        detail=f"fallback {fallback_id} failed: {exc}", created_at=now,
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
            return cached, warnings

        warnings.append(
            TelemetryWarning(
                station_id=cfg.id, kind="STATION_DROPPED",
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
                log, "FAILOVER_OFFSET_COMPUTED",
                station_id=station_id, fallback_id=fallback_id, offset_m=offset,
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
        return merged

    # ---- on-demand assessment ---------------------------------------------------
    async def assess_commune(
        self,
        commune_code: str,
        crop_stage: CropStage,
        *,
        with_audio: bool = False,
    ) -> AssessmentResult:
        commune = self.gazetteer.get(commune_code) or await self.repo.get_commune(commune_code)
        if commune is None:
            raise CommuneNotFound(commune_code)
        if not commune.nearest_station_id:
            raise AssessmentUnavailable(f"commune {commune_code} has no station assignment")

        station = await self.repo.latest_observation(commune.nearest_station_id)
        if station is None:
            stations = load_stations(str(self.settings.data_dir))
            cfg = stations.get(commune.nearest_station_id)
            if cfg is None:
                raise AssessmentUnavailable(f"station {commune.nearest_station_id} not configured")
            live = await self.mrc.fetch_station(cfg.id)  # type: ignore[union-attr]
            await self.repo.save_observation(live)
            station = live

        weather_by_province = await self.repo.latest_weather_by_province()
        weather = weather_by_province.get(commune.province_code or "")

        risk = self.classifier.classify(commune, station, weather)
        directives = self.agri.evaluate(
            risk.tier,
            crop_stage,
            rain_48h_mm=weather.precipitation_48h_mm if weather else 0.0,
            soil_moisture_pct=weather.soil_moisture_pct if weather else None,
            lead_time_hours=risk.lead_time_hours,
        )
        kh, en = await self.bulletin.build(commune, risk, directives, station, weather)  # type: ignore[union-attr]

        audio = None
        if with_audio:
            audio = await self._synthesize_audio(
                commune_code,
                risk,
                kh,
                audio_cache_signature(
                    commune_code, crop_stage, risk, station, weather, directives
                ),
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
    ):
        if self.audio_store is None:
            return None
        key = f"{commune_code}/{AUDIO_CACHE_VERSION}-{cache_signature}.mp3"
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
            log_event(log, "TTS_UNAVAILABLE", commune=commune_code, error=str(exc))
            return None
        ref = await self.audio_store.put(key, artifact.data, artifact.mime_type)
        log_event(log, "TTS_SYNTHESIZED", commune=commune_code, tier=risk.tier.value)
        return ref.model_copy(update={"duration_seconds": artifact.duration_seconds})
