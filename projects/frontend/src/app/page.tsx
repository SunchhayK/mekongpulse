"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AssessmentDialog } from "@/components/AssessmentDialog";
import { BasinMap } from "@/components/BasinMap";
import { CommuneSearch } from "@/components/CommuneSearch";
import { HydrographChart, type HydroObservation } from "@/components/HydrographChart";
import { RefreshIcon, WaveIcon } from "@/components/icons";
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
          ? "Telemetry Gateway: upstream station feed is unavailable. Showing the last successful refresh."
          : "Telemetry Gateway: connection failed. Check that the API is running and refresh.",
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
          <span className="wave" aria-hidden="true">
            <WaveIcon />
          </span>
          <span className="title-large">MekongPulse</span>
          <span className="body-small subtitle">
            ការត្រួតពិនិត្យទឹកទន្លេ · Mekong • Bassac • Tonle Sap
          </span>
        </div>
        <div className="spacer" />
        {health && (
          <>
            <span className="connection-pill label-small" data-state={health.mrc_station_connection}>
              <span className="dot" aria-hidden="true" />
              MRC Telemetry: {health.mrc_station_connection}
            </span>
            <span className="chip label-small" aria-label={`Environment ${health.environment}`}>
              {health.environment}
            </span>
          </>
        )}
        <button
          type="button"
          className="chip label-small"
          onClick={() => void load()}
          aria-label="Refresh telemetry and risk data"
        >
          <RefreshIcon />
          <span className="body-small">Refresh</span>
        </button>
      </header>

      <main className="layout">
        <aside className="rail" aria-label="Basin summary and commune lookup">
          <section className="card card--high" aria-label="Basin summary">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                Basin summary / សង្ខេបអាង
              </h2>
            </div>
            <p className="display-small mono" style={{ margin: 0 }}>
              {riskRows.length.toLocaleString()}
            </p>
            <p className="body-small muted" style={{ margin: "4px 0 12px" }}>
              monitored communes scored from {stations.length} river stations
              <br />
              ឃុំក្នុងការត្រួតពិនិត្យ
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {TIER_ORDER.map((tier) => (
                <div
                  key={tier}
                  style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}
                >
                  <span className="body-medium">
                    <span aria-hidden="true">{TIER_META[tier].emoji}</span>{" "}
                    <span lang="km">{TIER_META[tier].labelKh}</span>{" "}
                    <span className="muted">· {TIER_META[tier].labelEn}</span>
                  </span>
                  <span className="mono body-medium">{(tierCounts[tier] ?? 0).toLocaleString()}</span>
                </div>
              ))}
            </div>
            <p className="body-small muted" style={{ marginTop: 12 }}>
              Last station reading: {lastSync ? formatDateTime(lastSync) : "awaiting first sync"} ·{" "}
              synced every 15 min
            </p>
          </section>

          <CommuneSearch onPick={setSelectedCommuneCode} />

          <section className="card" aria-label="Highest risk communes">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                Highest risk / ហានិភ័យខ្ពស់
              </h2>
            </div>
            {topRisk.length === 0 ? (
              <p className="body-small muted" data-empty="true">
                No elevated communes right now.
              </p>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                {topRisk.map((row) => (
                  <li key={row.commune_code}>
                    <button
                      type="button"
                      className="chip"
                      style={{ width: "100%", justifyContent: "space-between" }}
                      onClick={() => setSelectedCommuneCode(row.commune_code)}
                    >
                      <span>
                        <span lang="km">{row.commune_name_kh}</span>
                        <br />
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
              <span className="body-small muted">tap a station to plot its hydrograph</span>
            </div>
            {booting ? (
              <div className="chip-row">
                <div className="shimmer" style={{ width: 160, height: 40 }} />
                <div className="shimmer" style={{ width: 160, height: 40 }} />
                <div className="shimmer" style={{ width: 160, height: 40 }} />
              </div>
            ) : stations.length === 0 ? (
              <p className="empty-state body-medium" data-empty="true">
                No telemetry yet. The scheduler syncs MRC stations every 15 minutes; run{" "}
                <span className="mono">POST /api/v1/telemetry/sync</span> to poll immediately.
              </p>
            ) : (
              <div className="chip-row" role="tablist" aria-label="Station selector">
                {stations.map((station) => (
                  <button
                    key={station.station_id}
                    type="button"
                    role="tab"
                    className="chip label-medium"
                    aria-selected={station.station_id === selectedStationId}
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

          <section className="hero" aria-label="Hydrograph and voice bulletin">
            <div className="card-title-row" style={{ marginBottom: 0 }}>
              <div>
                <h2 className="title-large" style={{ margin: 0 }}>
                  {selectedStation ? selectedStation.name : "Station hydrograph"}
                </h2>
                <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                  7-day water level · alarm {selectedStation?.alarm_stage_m.toFixed(2) ?? "—"} m · flood{" "}
                  {selectedStation?.flood_stage_m.toFixed(2) ?? "—"} m / កម្ពស់ទឹក ៧ថ្ងៃថយក្រោយ
                </p>
              </div>
              {selectedStation && (
                <span className="mono title-medium">
                  {selectedStation.level_m.toFixed(2)} m
                  <span className="muted body-small">
                    {" "}
                    {selectedStation.rate_of_rise_m_per_hr > 0 ? "▲" : selectedStation.rate_of_rise_m_per_hr < 0 ? "▼" : "■"}{" "}
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
              <p className="empty-state body-medium" data-empty="true">
                Select a station to plot its 7-day hydrograph.
              </p>
            )}

            <div className="body-small muted" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span>
                Khmer voice bulletin / សារសម្លេងខ្មែរ —{" "}
                {lastAssessment
                  ? `${lastAssessment.commune_name_kh} (${lastAssessment.commune_code})`
                  : "select a commune on the map"}
              </span>
              <VoicePlayer
                audioSrc={lastAssessment?.audio?.url}
                durationSeconds={lastAssessment?.audio?.duration_seconds ?? undefined}
                transcriptKhmer={
                  lastAssessment?.khmer_bulletin ??
                  "ជ្រើសរើសឃុំនៅលើផែនទី ឬស្វែងរកឃុំ ដើម្បីមើលសារជូនដំណឹង និងស្តាប់សារសម្លេងខ្មែរ។"
                }
                transcriptEnglish={
                  lastAssessment?.english_bulletin ??
                  "Select or search a commune to load its bilingual bulletin and spoken Khmer warning."
                }
              />
            </div>
          </section>

          <section className="card" id="map" aria-label="Basin risk map">
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                Basin risk map / ផែនទីហានិភ័យ
              </h2>
              <span className="body-small muted">
                {riskRows.length.toLocaleString()} communes · risk-coloured by tier
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

          <footer className="body-small muted" style={{ paddingBottom: 8 }}>
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
            ⌖
          </span>
          <span className="label-small">Map ផែនទី</span>
        </a>
        <a href="#risk">
          <span className="icon" aria-hidden="true">
            ⚠
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
