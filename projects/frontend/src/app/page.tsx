"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AssessmentDialog } from "@/components/AssessmentDialog";
import { BasinMap } from "@/components/BasinMap";
import { CommuneSearch } from "@/components/CommuneSearch";
import { HydrographChart, type HydroObservation } from "@/components/HydrographChart";
import { AlertIcon, BrandMark, MapIcon, RefreshIcon, WaveIcon } from "@/components/icons";
import { RiskBadge } from "@/components/RiskBadge";
import { RiskList } from "@/components/RiskList";
import { StationMetricCard } from "@/components/StationMetricCard";
import { VoicePlayer } from "@/components/VoicePlayer";
import {
  api,
  ApiError,
  type Assessment,
  type CommuneRiskRow,
  type Health,
  type HydroPoint,
  type StationTelemetry,
} from "@/lib/api";
import { formatDateTime, TIER_META, TIER_ORDER, tierSeverity } from "@/lib/design";

const REFRESH_MS = 15 * 60 * 1000;

export default function DashboardPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stations, setStations] = useState<StationTelemetry[]>([]);
  const [riskRows, setRiskRows] = useState<CommuneRiskRow[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const [points, setPoints] = useState<HydroPoint[]>([]);
  const [selectedCommuneCode, setSelectedCommuneCode] = useState<string | null>(null);
  const [lastAssessment, setLastAssessment] = useState<Assessment | null>(null);
  const [booting, setBooting] = useState(true);
  const [pointsLoading, setPointsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextHealth, nextStations, nextRisks] = await Promise.all([
        api.health(),
        api.stations(),
        api.riskMap(),
      ]);
      setHealth(nextHealth);
      setStations(nextStations);
      setRiskRows(nextRisks);
      setError(null);
      setSelectedStationId((current) => current ?? nextStations[0]?.station_id ?? null);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status >= 500
          ? "Telemetry gateway: the upstream station feed is unavailable. Showing the last successful refresh."
          : "Telemetry gateway: connection failed. Check that the API is running, then refresh.",
      );
    } finally {
      setBooting(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!selectedStationId) return;
    let cancelled = false;
    setPointsLoading(true);
    api
      .hydrograph(selectedStationId, 168)
      .then((series) => {
        if (!cancelled) setPoints(series.points);
      })
      .catch(() => {
        if (!cancelled) setPoints([]);
      })
      .finally(() => {
        if (!cancelled) setPointsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedStationId]);

  const selectedStation = stations.find((station) => station.station_id === selectedStationId) ?? null;

  const observations: HydroObservation[] = useMemo(
    () =>
      points.map((point) => ({
        timestamp: point.t,
        waterLevelMeters: point.level_m,
        rainfallMm: point.rain_mm ?? undefined,
      })),
    [points],
  );

  const tierCounts = useMemo(() => {
    const counts: Record<string, number> = { NORMAL: 0, ADVISORY: 0, WARNING: 0, DANGER: 0 };
    riskRows.forEach((row) => {
      counts[row.tier] = (counts[row.tier] ?? 0) + 1;
    });
    return counts;
  }, [riskRows]);

  const lastSync = useMemo(() => {
    if (stations.length === 0) return null;
    return stations.reduce(
      (newest, station) =>
        new Date(station.recorded_at) > new Date(newest) ? station.recorded_at : newest,
      stations[0].recorded_at,
    );
  }, [stations]);

  /** Plain-language basin status for the hero band. */
  const headline = useMemo(() => {
    if (booting) return "Reading the rivers…";
    if (tierCounts.DANGER > 0) return `${tierCounts.DANGER} communes in flood danger`;
    if (tierCounts.WARNING > 0) return `${tierCounts.WARNING} communes under flood warning`;
    if (tierCounts.ADVISORY > 0) return `${tierCounts.ADVISORY} communes on advisory watch`;
    return "All monitored communes below alarm stage";
  }, [booting, tierCounts]);

  const headlineTier = useMemo(() => {
    if (tierCounts.DANGER > 0) return "DANGER";
    if (tierCounts.WARNING > 0) return "WARNING";
    if (tierCounts.ADVISORY > 0) return "ADVISORY";
    return "NORMAL";
  }, [tierCounts]);

  const headlineParts = useMemo(() => {
    const count = tierCounts[headlineTier] ?? 0;
    const phrase =
      headlineTier === "DANGER"
        ? "in flood danger"
        : headlineTier === "WARNING"
          ? "under flood warning"
          : headlineTier === "ADVISORY"
            ? "on advisory watch"
            : "";
    return { count, phrase };
  }, [headlineTier, tierCounts]);

  const topRisk = useMemo(
    () =>
      [...riskRows]
        .filter((row) => tierSeverity(row.tier) >= tierSeverity("ADVISORY"))
        .sort((a, b) => tierSeverity(b.tier) - tierSeverity(a.tier) || b.score - a.score)
        .slice(0, 5),
    [riskRows],
  );

  const handleAssessment = useCallback((assessment: Assessment) => {
    setLastAssessment(assessment);
  }, []);

  return (
    <div className="app">
      <header className="top-app-bar">
        <div className="brand">
          <BrandMark />
          <span className="brand-text">
            <span className="brand-name">MekongPulse</span>
            <span className="body-small subtitle">ទឹកទន្លេមេគង្គ · River telemetry</span>
          </span>
        </div>
        <div className="spacer" />
        {health && (
          <>
            <span
              className="connection-pill label-small"
              data-state={health.mrc_station_connection}
              aria-label={`MRC telemetry ${health.mrc_station_connection}`}
            >
              <span className="dot" aria-hidden="true" />
              <span className="connection-label">MRC {health.mrc_station_connection.toLowerCase()}</span>
            </span>
            <span className="meta-pill label-small" aria-label={`Environment ${health.environment}`}>
              {health.environment}
            </span>
          </>
        )}
        <button
          type="button"
          className="btn btn--filled btn--compact label-medium"
          onClick={() => void load()}
          aria-label="Refresh telemetry and risk data"
        >
          <RefreshIcon />
          <span>Refresh</span>
        </button>
      </header>

      <section className="hero-band" aria-label="Basin status">
        <div className="hero-inner">
          <div className="hero-copy">
            <p className="eyebrow">MekongPulse · River telemetry · Cambodia</p>
            <h1 className="hero-headline">
              {headlineParts.count > 0 && headlineParts.phrase ? (
                <>
                  <span className="tier-word">{headlineParts.count}</span>{" "}
                  {headlineParts.phrase}
                </>
              ) : (
                headline
              )}
            </h1>
            <p className="body-medium hero-sub">
              {`${riskRows.length.toLocaleString()} communes scored from ${stations.length} MRC stations`}
              {" · "}
              {lastSync ? `last reading ${formatDateTime(lastSync)}` : "awaiting first sync"}
              <br />
              ស្ថានភាពទឹកទន្លេឥឡូវនេះ · មេគង្គ · បាសាក់ · ទន្លេសាប
            </p>
            <nav className="hero-links" aria-label="Jump to section">
              <a className="hero-link label-medium" href="#stations">
                <WaveIcon /> River stations
              </a>
              <a className="hero-link label-medium" href="#map">
                <MapIcon /> Basin map
              </a>
              <a className="hero-link label-medium" href="#risk">
                <AlertIcon /> Risk register
              </a>
            </nav>
          </div>

          <div className="risk-panel" aria-label="Risk distribution across monitored communes">
            <div className="risk-panel-head">
              <span className="eyebrow">Basin risk / ហានិភ័យអាង</span>
              <span className="body-small muted">{riskRows.length.toLocaleString()} communes</span>
            </div>
            <div
              className="risk-bar"
              role="img"
              aria-label={TIER_ORDER.map((tier) => `${TIER_META[tier].labelEn} ${tierCounts[tier] ?? 0}`).join(", ")}
            >
              {TIER_ORDER.map((tier) => {
                const count = tierCounts[tier] ?? 0;
                if (count === 0) return null;
                return (
                  <span
                    key={tier}
                    className="seg"
                    style={{ flexGrow: count, background: TIER_META[tier].color }}
                  />
                );
              })}
            </div>
            <ul className="risk-legend">
              {TIER_ORDER.map((tier) => (
                <li className="item" key={tier}>
                  <span className="swatch" style={{ background: TIER_META[tier].color }} aria-hidden="true" />
                  <span className="body-small" lang="km">{TIER_META[tier].labelKh}</span>
                  <span className="body-small muted">{TIER_META[tier].labelEn}</span>
                  <span className="count mono body-medium">{(tierCounts[tier] ?? 0).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <main className="layout">
        <aside className="rail" aria-label="Commune lookup and highest risk">
          <CommuneSearch onPick={setSelectedCommuneCode} />

          <section className="card" aria-label="Highest risk communes">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                Highest risk / ហានិភ័យខ្ពស់
              </h2>
              <span className="body-small muted">
                {topRisk.length > 0 ? "tap for the full bulletin" : "all clear"}
              </span>
            </div>
            {topRisk.length === 0 ? (
              <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
                No elevated communes right now.
              </p>
            ) : (
              <ul className="top-risk-list">
                {topRisk.map((row) => (
                  <li key={row.commune_code}>
                    <button
                      type="button"
                      className="top-risk-item"
                      onClick={() => setSelectedCommuneCode(row.commune_code)}
                    >
                      <span className="top-risk-name">
                        <span className="title-small" lang="km">{row.commune_name_kh}</span>
                        <span className="body-small muted">
                          {row.commune_name_en} · {row.province ?? "—"}
                        </span>
                      </span>
                      <RiskBadge
                        tier={row.tier}
                        leadTimeHours={row.lead_time_hours ?? undefined}
                        size="small"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>

        <div className="main-column">
          {error && (
            <p className="error-banner body-medium" role="alert">
              {error}
            </p>
          )}

          <section className="card" id="stations" aria-label="River stations">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                River stations / ស្ថានីយទន្លេ
              </h2>
              <span className="body-small muted">select a station to plot its 7-day hydrograph</span>
            </div>
            {booting ? (
              <div className="chip-row">
                <div className="shimmer" style={{ width: 150, height: 40 }} />
                <div className="shimmer" style={{ width: 150, height: 40 }} />
                <div className="shimmer" style={{ width: 150, height: 40 }} />
              </div>
            ) : stations.length === 0 ? (
              <p className="empty-state body-medium" data-empty="true" style={{ margin: 0 }}>
                No telemetry yet. The scheduler syncs MRC stations every 15 minutes; run{" "}
                <span className="mono">POST /api/v1/telemetry/sync</span> to poll immediately.
              </p>
            ) : (
              <div className="chip-row" role="group" aria-label="Station selector">
                {stations.map((station) => (
                  <button
                    key={station.station_id}
                    type="button"
                    className="chip label-medium"
                    aria-pressed={station.station_id === selectedStationId}
                    onClick={() => setSelectedStationId(station.station_id)}
                    title={`${station.river} · alarm ${station.alarm_stage_m} m · flood ${station.flood_stage_m} m`}
                  >
                    {station.name}
                    <span className="chip-level">{station.level_m.toFixed(2)} m</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="card hero-card" aria-label="Hydrograph and voice bulletin">
            <div className="card-title-row" style={{ marginBottom: 0 }}>
              <div>
                <h2 className="headline-medium" style={{ margin: 0 }}>
                  {selectedStation ? selectedStation.name : "Station hydrograph"}
                </h2>
                <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                  {selectedStation
                    ? `${selectedStation.river} · ${selectedStation.station_id} · alarm ${selectedStation.alarm_stage_m.toFixed(2)} m · flood ${selectedStation.flood_stage_m.toFixed(2)} m · 7-day / កម្ពស់ទឹក ៧ថ្ងៃថយក្រោយ`
                    : "Select a station to plot its 7-day water level."}
                </p>
              </div>
              {selectedStation && (
                <span className="station-live">
                  <span className="value mono">{selectedStation.level_m.toFixed(2)}</span>
                  <span className="muted body-medium">m</span>
                  <span
                    className="rate body-medium"
                    data-direction={
                      selectedStation.rate_of_rise_m_per_hr > 0.005
                        ? "rising"
                        : selectedStation.rate_of_rise_m_per_hr < -0.005
                          ? "falling"
                          : "steady"
                    }
                  >
                    {selectedStation.rate_of_rise_m_per_hr > 0.005
                      ? "▲"
                      : selectedStation.rate_of_rise_m_per_hr < -0.005
                        ? "▼"
                        : "■"}{" "}
                    {selectedStation.rate_of_rise_m_per_hr.toFixed(3)} m/hr
                  </span>
                </span>
              )}
            </div>
            {pointsLoading ? (
              <div className="shimmer" style={{ height: 320 }} aria-busy="true" />
            ) : selectedStation ? (
              <HydrographChart
                stationId={selectedStation.station_id}
                stationName={selectedStation.name}
                alarmStageMeters={selectedStation.alarm_stage_m}
                floodStageMeters={selectedStation.flood_stage_m}
                observations={observations}
              />
            ) : (
              <p className="empty-state body-medium" data-empty="true" style={{ margin: 0 }}>
                Select a station to plot its 7-day hydrograph.
              </p>
            )}
          </section>

          <section className="card voice-card" aria-label="Khmer voice bulletin">
            <div className="card-title-row" style={{ marginBottom: 8 }}>
              <h2 className="title-medium" style={{ margin: 0 }}>
                សារសម្លេងខ្មែរ · Khmer voice bulletin
              </h2>
              <span className="body-small" style={{ color: "#a9bcd9" }}>
                {lastAssessment
                  ? `${lastAssessment.commune_name_en} (${lastAssessment.commune_code})`
                  : "select a commune to load its bulletin"}
              </span>
            </div>
            <VoicePlayer
              audioSrc={lastAssessment?.audio?.url}
              durationSeconds={lastAssessment?.audio?.duration_seconds ?? undefined}
              transcriptKhmer={
                lastAssessment?.khmer_bulletin ??
                "ជ្រើសរើសឃុំនៅលើផែនទី ឬស្វែងរកឃុំ ដើម្បីមើលសារជូនដំណឹង និងស្តាប់សារសម្លេងខ្មែរ។"
              }
              transcriptEnglish={
                lastAssessment?.english_bulletin ??
                "Select or search a commune to load its bilingual flood bulletin and spoken Khmer warning."
              }
            />
          </section>

          <section className="card" id="map" aria-label="Basin risk map">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                Basin risk map / ផែនទីហានិភ័យ
              </h2>
              <span className="body-small muted">
                {riskRows.length.toLocaleString()} communes · tap a dot for its bulletin
              </span>
            </div>
            <BasinMap
              communes={riskRows}
              stations={stations}
              selectedStationId={selectedStationId ?? undefined}
              onSelectCommune={setSelectedCommuneCode}
              onSelectStation={setSelectedStationId}
            />
          </section>

          <section aria-label="Station detail cards">
            <div className="section-label label-small">Station detail / ព័ត៌មានលម្អិត</div>
            {booting ? (
              <div className="station-grid">
                <div className="shimmer" style={{ height: 180 }} />
                <div className="shimmer" style={{ height: 180 }} />
                <div className="shimmer" style={{ height: 180 }} />
                <div className="shimmer" style={{ height: 180 }} />
              </div>
            ) : (
              <div className="station-grid">
                {stations.map((station) => (
                  <StationMetricCard
                    key={station.station_id}
                    stationId={station.station_id}
                    stationName={station.name}
                    riverName={station.river}
                    currentWaterLevelM={station.level_m}
                    rateOfRiseMPerHour={station.rate_of_rise_m_per_hr}
                    alarmStageM={station.alarm_stage_m}
                    floodStageM={station.flood_stage_m}
                    isStaleFallback={station.is_stale_fallback}
                    selected={station.station_id === selectedStationId}
                    onSelect={setSelectedStationId}
                  />
                ))}
              </div>
            )}
          </section>

          <RiskList rows={riskRows} onSelect={setSelectedCommuneCode} />

          <footer className="footer body-small">
            Data: MRC telemetry (api.mrcmekong.org) · Open-Meteo rainfall · MEF 2025 commune gazetteer.
            Risk tiers refresh every 15 minutes; alerts dispatch via the MekongPulse Telegram bot.
            Bilingual bulletins are synthesized with Gemini Khmer TTS and attached to Sentinel alerts.
          </footer>
        </div>
      </main>

      <nav className="bottom-nav" aria-label="Primary">
        <a href="#stations" aria-current="true">
          <span className="icon" aria-hidden="true">
            <WaveIcon />
          </span>
          <span className="label-small">River ទន្លេ</span>
        </a>
        <a href="#map">
          <span className="icon" aria-hidden="true">
            <MapIcon />
          </span>
          <span className="label-small">Map ផែនទី</span>
        </a>
        <a href="#risk">
          <span className="icon" aria-hidden="true">
            <AlertIcon />
          </span>
          <span className="label-small">Risk ហានិភ័យ</span>
        </a>
      </nav>

      <AssessmentDialog
        communeCode={selectedCommuneCode}
        onClose={() => setSelectedCommuneCode(null)}
        onAssessment={handleAssessment}
      />
    </div>
  );
}
