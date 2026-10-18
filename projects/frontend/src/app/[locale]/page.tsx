"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { AlertLog } from "@/components/AlertLog";
import { AssessmentDialog } from "@/components/AssessmentDialog";
import { BasinMap } from "@/components/BasinMap";
import { CommuneSearch } from "@/components/CommuneSearch";
import { HydrographChart, type HydroObservation } from "@/components/HydrographChart";
import { AlertIcon, AssistantIcon, BrandMark, InfoIcon, MapIcon, RefreshIcon, WaveIcon } from "@/components/icons";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { RiskBadge } from "@/components/RiskBadge";
import { RiskList } from "@/components/RiskList";
import { StationMetricCard } from "@/components/StationMetricCard";
import { StatusSummary } from "@/components/StatusSummary";
import { VoicePlayer } from "@/components/VoicePlayer";
import { Link } from "@/i18n/navigation";
import {
  api,
  ApiError,
  type Assessment,
  type CommuneRiskRow,
  type Health,
  type HydroPoint,
  type StationTelemetry,
} from "@/lib/api";
import {
  formatDateTime,
  formatNumber,
  TIER_META,
  TIER_ORDER,
  tierSeverity,
} from "@/lib/design";

const REFRESH_MS = 15 * 60 * 1000;

export default function DashboardPage() {
  const t = useTranslations();
  const locale = useLocale();
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
          ? t("TelemetryErrors.gatewayUnavailable")
          : t("TelemetryErrors.gatewayFailed"),
      );
    } finally {
      setBooting(false);
    }
  }, [t]);

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
    const tierWord = (chunks: React.ReactNode) => <span className="tier-word">{chunks}</span>;
    if (booting) return t("Hero.reading");
    if (tierCounts.DANGER > 0)
      return t.rich("Hero.danger", { count: tierCounts.DANGER, tier: tierWord });
    if (tierCounts.WARNING > 0)
      return t.rich("Hero.warning", { count: tierCounts.WARNING, tier: tierWord });
    if (tierCounts.ADVISORY > 0)
      return t.rich("Hero.advisory", { count: tierCounts.ADVISORY, tier: tierWord });
    return t("Hero.allClear");
  }, [booting, tierCounts, t]);

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
            <span className="body-small subtitle">{t("Brand.subtitle")}</span>
          </span>
        </div>
        <div className="spacer" />
        {health && (
          <>
            <span
              className="connection-pill label-small"
              data-state={health.mrc_station_connection}
              aria-label={t("Header.mrcAria", {
                state: t(`Header.mrcStates.${health.mrc_station_connection}`),
              })}
            >
              <span className="dot" aria-hidden="true" />
              <span className="connection-label">
                {t("Header.mrcLabel", {
                  state: t(`Header.mrcStates.${health.mrc_station_connection}`),
                })}
              </span>
            </span>
            <span
              className="meta-pill label-small"
              aria-label={t("Header.environmentAria", { environment: health.environment })}
            >
              {health.environment}
            </span>
          </>
        )}
        <LanguageSwitcher />
        <nav className="header-nav" aria-label={t("Header.assistantNavAria")}>
          <Link
            className="header-nav-link label-medium"
            href={{
              pathname: "/assistant",
              query: selectedCommuneCode ? { code: selectedCommuneCode } : undefined,
            }}
            aria-label={t("Header.assistant")}
          >
            <AssistantIcon />
            <span className="header-nav-label">{t("Header.assistant")}</span>
          </Link>
        </nav>
        <button
          type="button"
          className="btn btn--filled btn--compact label-medium"
          onClick={() => void load()}
          aria-label={t("Header.refreshAria")}
        >
          <RefreshIcon />
          <span>{t("Header.refresh")}</span>
        </button>
      </header>

      <section className="hero-band" aria-label={t("Hero.bandAria")}>
        <div className="hero-inner">
          <div className="hero-copy">
            <p className="eyebrow">{t("Hero.eyebrow")}</p>
            <h1 className="hero-headline">{headline}</h1>
            <p className="body-medium hero-sub">
              {t("Hero.scored", { communes: riskRows.length, stations: stations.length })}
              {" · "}
              {lastSync
                ? t("Hero.lastReading", { time: formatDateTime(lastSync, locale) })
                : t("Hero.awaitingSync")}
              <br />
              {t("Hero.riverConditions")}
            </p>
            <nav className="hero-links" aria-label={t("Hero.jumpAria")}>
              <a className="hero-link label-medium" href="#summary">
                <InfoIcon /> {t("Hero.linkSummary")}
              </a>
              <a className="hero-link label-medium" href="#alerts">
                <AlertIcon /> {t("Hero.linkAlerts")}
              </a>
              <a className="hero-link label-medium" href="#stations">
                <WaveIcon /> {t("Hero.linkStations")}
              </a>
              <a className="hero-link label-medium" href="#map">
                <MapIcon /> {t("Hero.linkMap")}
              </a>
              <a className="hero-link label-medium" href="#risk">
                <AlertIcon /> {t("Hero.linkRisk")}
              </a>
            </nav>
          </div>

          <div className="risk-panel" aria-label={t("Hero.riskPanelAria")}>
            <div className="risk-panel-head">
              <span className="eyebrow">{t("Hero.riskPanelTitle")}</span>
              <span className="body-small muted">
                {t("Hero.communes", { count: riskRows.length })}
              </span>
            </div>
            <div
              className="risk-bar"
              role="img"
              aria-label={TIER_ORDER.map(
                (tier) => `${t(`Tier.${tier}`)} ${formatNumber(tierCounts[tier] ?? 0, locale)}`,
              ).join(", ")}
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
                  <span className="body-small">{t(`Tier.${tier}`)}</span>
                  <span className="count mono body-medium">
                    {formatNumber(tierCounts[tier] ?? 0, locale)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <main className="layout">
        <aside className="rail" aria-label={t("Aria.rail")}>
          <section className="card officer-cta" aria-label={t("Officer.title")}>
            <span className="officer-cta-icon" aria-hidden="true">
              <AssistantIcon />
            </span>
            <h2 className="title-medium" style={{ margin: 0 }}>
              {t("Officer.title")}
            </h2>
            <p className="body-small muted" style={{ margin: 0 }}>
              {t("Officer.subtitle")}
            </p>
            <Link
              className="btn btn--filled label-medium officer-cta-btn"
              href={{
                pathname: "/assistant",
                query: selectedCommuneCode ? { code: selectedCommuneCode } : undefined,
              }}
            >
              <AssistantIcon /> {t("Officer.ctaAction")}
            </Link>
          </section>

          <CommuneSearch onPick={setSelectedCommuneCode} />

          <section className="card" aria-label={t("Aria.highestRiskSection")}>
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                {t("HighestRisk.title")}
              </h2>
              <span className="body-small muted">
                {topRisk.length > 0 ? t("HighestRisk.tap") : t("HighestRisk.allClear")}
              </span>
            </div>
            {topRisk.length === 0 ? (
              <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
                {t("HighestRisk.empty")}
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

          <StatusSummary riskRows={riskRows} stations={stations} lastSync={lastSync} />

          <AlertLog />

          <section className="card" id="stations" aria-label={t("Stations.title")}>
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                {t("Stations.title")}
              </h2>
              <span className="body-small muted">{t("Stations.hint")}</span>
            </div>
            {booting ? (
              <div className="chip-row">
                <div className="shimmer" style={{ width: 150, height: 40 }} />
                <div className="shimmer" style={{ width: 150, height: 40 }} />
                <div className="shimmer" style={{ width: 150, height: 40 }} />
              </div>
            ) : stations.length === 0 ? (
              <p className="empty-state body-medium" data-empty="true" style={{ margin: 0 }}>
                {t.rich("Stations.empty", {
                  mono: (chunks) => <span className="mono">{chunks}</span>,
                })}
              </p>
            ) : (
              <div className="chip-row" role="group" aria-label={t("Stations.selectorAria")}>
                {stations.map((station) => (
                  <button
                    key={station.station_id}
                    type="button"
                    className="chip label-medium"
                    aria-pressed={station.station_id === selectedStationId}
                    onClick={() => setSelectedStationId(station.station_id)}
                    title={t("Stations.chipTitle", {
                      river: station.river,
                      alarm: station.alarm_stage_m,
                      flood: station.flood_stage_m,
                    })}
                  >
                    {station.name}
                    <span className="chip-level">{station.level_m.toFixed(2)} m</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="card hero-card" aria-label={t("Hydrograph.cardAria")}>
            <div className="card-title-row" style={{ marginBottom: 0 }}>
              <div>
                <h2 className="headline-medium" style={{ margin: 0 }}>
                  {selectedStation ? selectedStation.name : t("Hydrograph.titleFallback")}
                </h2>
                <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                  {selectedStation
                    ? t("Hydrograph.subActive", {
                        river: selectedStation.river,
                        id: selectedStation.station_id,
                        alarm: selectedStation.alarm_stage_m.toFixed(2),
                        flood: selectedStation.flood_stage_m.toFixed(2),
                      })
                    : t("Hydrograph.subEmpty")}
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
                {t("Hydrograph.subEmpty")}
              </p>
            )}
          </section>

          <section className="card voice-card" aria-label={t("Voice.cardAria")}>
            <div className="card-title-row" style={{ marginBottom: 8 }}>
              <h2 className="title-medium" style={{ margin: 0 }}>
                {t("Voice.title")}
              </h2>
              <span className="body-small" style={{ color: "#a9bcd9" }}>
                {lastAssessment
                  ? t("Voice.selected", {
                      name: lastAssessment.commune_name_en,
                      code: lastAssessment.commune_code,
                    })
                  : t("Voice.empty")}
              </span>
            </div>
            <VoicePlayer
              audioSrc={lastAssessment?.audio?.url}
              durationSeconds={lastAssessment?.audio?.duration_seconds ?? undefined}
              transcriptKhmer={lastAssessment?.khmer_bulletin ?? t("Voice.fallbackKhmer")}
              transcriptEnglish={lastAssessment?.english_bulletin ?? t("Voice.fallbackEnglish")}
            />
          </section>

          <section className="card" id="map" aria-label={t("Map.sectionAria")}>
            <div className="card-title-row">
              <h2 className="title-medium" style={{ margin: 0 }}>
                {t("Map.title")}
              </h2>
              <span className="body-small muted">
                {t("Map.hint", { count: riskRows.length })}
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

          <section id="station-detail" aria-label={t("Aria.stationDetailSection")}>
            <div className="section-label label-small">{t("StationDetail.label")}</div>
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

          <footer className="footer body-small">{t("Footer.data")}</footer>
        </div>
      </main>

      <nav className="bottom-nav" aria-label={t("BottomNav.aria")}>
        <a href="#stations" aria-current="true">
          <span className="icon" aria-hidden="true">
            <WaveIcon />
          </span>
          <span className="label-small">{t("BottomNav.river")}</span>
        </a>
        <a href="#map">
          <span className="icon" aria-hidden="true">
            <MapIcon />
          </span>
          <span className="label-small">{t("BottomNav.map")}</span>
        </a>
        <a href="#risk">
          <span className="icon" aria-hidden="true">
            <AlertIcon />
          </span>
          <span className="label-small">{t("BottomNav.risk")}</span>
        </a>
        <Link href={{ pathname: "/assistant", query: selectedCommuneCode ? { code: selectedCommuneCode } : undefined }}>
          <span className="icon" aria-hidden="true">
            <AssistantIcon />
          </span>
          <span className="label-small">{t("BottomNav.assistant")}</span>
        </Link>
      </nav>

      <AssessmentDialog
        communeCode={selectedCommuneCode}
        onClose={() => setSelectedCommuneCode(null)}
        onAssessment={handleAssessment}
      />
    </div>
  );
}
