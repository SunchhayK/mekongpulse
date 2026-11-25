"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { AlertLog } from "@/components/AlertLog";
import { AssessmentDialog } from "@/components/AssessmentDialog";
import { BasinMap } from "@/components/BasinMap";
import { CommuneSearch } from "@/components/CommuneSearch";
import { HydrographChart, type HydroObservation } from "@/components/HydrographChart";
import {
  AssistantIcon,
  BrandMark,
  MapIcon,
  RefreshIcon,
  SearchIcon,
} from "@/components/icons";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { RiskList } from "@/components/RiskList";
import { stationTier } from "@/components/StationMetricCard";
import { StatusSummary } from "@/components/StatusSummary";
import { Link } from "@/i18n/navigation";
import {
  api,
  type CommuneRiskRow,
  type FloodRiskTier,
  type HydroPoint,
  type StationTelemetry,
} from "@/lib/api";
import {
  formatDateTime,
  formatNumber,
  TIER_META,
  TIER_ORDER,
} from "@/lib/design";

const REFRESH_MS = 15 * 60 * 1000;
const HERO_TIER_ORDER: FloodRiskTier[] = ["DANGER", "WARNING", "ADVISORY", "NORMAL"];

export default function DashboardPage() {
  const t = useTranslations();
  const locale = useLocale();
  const [stations, setStations] = useState<StationTelemetry[]>([]);
  const [riskRows, setRiskRows] = useState<CommuneRiskRow[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const [points, setPoints] = useState<HydroPoint[]>([]);
  const [selectedCommuneCode, setSelectedCommuneCode] = useState<string | null>(null);
  const [tierFilter, setTierFilter] = useState<FloodRiskTier | null>(null);
  const [booting, setBooting] = useState(true);
  const [pointsLoading, setPointsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextStations, nextRisks] = await Promise.all([
        api.stations(),
        api.riskMap(),
      ]);
      setStations(nextStations);
      setRiskRows(nextRisks);
      setError(null);
      setSelectedStationId((current) => current ?? nextStations[0]?.station_id ?? null);
    } catch {
      setError(t("TelemetryErrors.unavailable"));
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

  const selectedStation =
    stations.find((station) => station.station_id === selectedStationId) ?? null;

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
    const counts: Record<FloodRiskTier, number> = {
      NORMAL: 0,
      ADVISORY: 0,
      WARNING: 0,
      DANGER: 0,
    };
    riskRows.forEach((row) => {
      counts[row.tier] = (counts[row.tier] ?? 0) + 1;
    });
    return counts;
  }, [riskRows]);

  const highestTier: FloodRiskTier = useMemo(() => {
    if (tierCounts.DANGER > 0) return "DANGER";
    if (tierCounts.WARNING > 0) return "WARNING";
    if (tierCounts.ADVISORY > 0) return "ADVISORY";
    return "NORMAL";
  }, [tierCounts]);

  const lastSync = useMemo(() => {
    if (stations.length === 0) return null;
    return stations.reduce(
      (newest, station) =>
        new Date(station.recorded_at) > new Date(newest) ? station.recorded_at : newest,
      stations[0].recorded_at,
    );
  }, [stations]);

  const headline = useMemo(() => {
    if (booting) return t("Hero.reading");
    if (tierCounts.DANGER > 0) return t("Hero.danger", { count: tierCounts.DANGER });
    if (tierCounts.WARNING > 0) return t("Hero.warning", { count: tierCounts.WARNING });
    if (tierCounts.ADVISORY > 0) return t("Hero.advisory", { count: tierCounts.ADVISORY });
    return t("Hero.allClear");
  }, [booting, tierCounts, t]);

  const stationMarginNote = useMemo(() => {
    if (!selectedStation) return null;
    const diff = selectedStation.alarm_stage_m - selectedStation.level_m;
    if (diff < 0) {
      return t("Hydrograph.aboveAlarm", { meters: Math.abs(diff).toFixed(2) });
    }
    return t("Hydrograph.belowAlarm", { meters: diff.toFixed(2) });
  }, [selectedStation, t]);

  return (
    <div className="app">
      <header className="top-app-bar">
        <div className="top-app-bar-inner">
          <Link className="brand" href="/">
            <BrandMark />
            <span className="brand-name">MekongPulse</span>
          </Link>
          <div className="spacer" />
          <nav className="primary-nav" aria-label={t("Header.navAria")}>
            <Link className="nav-link label-medium" href="/" aria-current="page">
              {t("Header.floodMap")}
            </Link>
            <Link
              className="nav-link label-medium"
              href={{
                pathname: "/assistant",
                query: selectedCommuneCode ? { code: selectedCommuneCode } : undefined,
              }}
            >
              {t("Header.assistant")}
            </Link>
          </nav>
          <LanguageSwitcher />
        </div>
      </header>

      <section
        className="hero-band"
        id="check"
        data-tier={booting ? undefined : highestTier}
        aria-label={t("Hero.bandAria")}
      >
        <div className="hero-inner">
          <div className="hero-status-row">
            <div className="hero-heading-group">
              <span
                className="hero-status-dot"
                data-tier={booting ? undefined : highestTier}
                aria-hidden="true"
              />
              <h1 className="hero-headline">{headline}</h1>
            </div>
            <div className="hero-meta-row body-small">
              <p className="hero-meta-text">
                {lastSync
                  ? t("Hero.updatedFrom", {
                      time: formatDateTime(lastSync, locale),
                      stations: stations.length,
                    })
                  : t("Hero.awaitingSync")}
              </p>
              <button
                type="button"
                className="btn-link-quiet"
                onClick={() => void load()}
                aria-label={t("Header.refreshAria")}
              >
                <RefreshIcon />
                <span>{t("Header.refresh")}</span>
              </button>
            </div>
          </div>

          <CommuneSearch onPick={setSelectedCommuneCode} />

          <div
            className="tier-filter-strip"
            role="group"
            aria-label={t("Hero.riskPanelAria")}
          >
            {HERO_TIER_ORDER.map((tier) => {
              const active = tierFilter === tier;
              return (
                <button
                  key={tier}
                  type="button"
                  className="tier-pill label-medium"
                  aria-pressed={active}
                  onClick={() => setTierFilter((prev) => (prev === tier ? null : tier))}
                >
                  <span
                    className="swatch"
                    style={{ background: TIER_META[tier].color }}
                    aria-hidden="true"
                  />
                  <span>{t(`Tier.${tier}`)}</span>
                  <span className="count">{formatNumber(tierCounts[tier] ?? 0, locale)}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <main className="page-container">
        {error && (
          <div className="notice-banner body-small" role="status">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn--outline btn--compact label-small"
              onClick={() => void load()}
            >
              <RefreshIcon />
              <span>{t("Header.refresh")}</span>
            </button>
          </div>
        )}

        <section className="workspace-grid" id="map" aria-label={t("Map.sectionAria")}>
          <div className="surface map-panel">
            <div className="map-panel-head">
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
          </div>

          <RiskList
            rows={riskRows}
            tierFilter={tierFilter}
            onClearTierFilter={() => setTierFilter(null)}
            onSelect={setSelectedCommuneCode}
          />
        </section>

        <hr className="section-divider" />

        <section className="river-section" id="stations" aria-label={t("Stations.title")}>
          <div className="section-header" style={{ marginBottom: 0 }}>
            <h2 className="headline-medium section-title">{t("Stations.title")}</h2>
            <span className="body-small muted">{t("Stations.hint")}</span>
          </div>

          {booting ? (
            <div className="station-strip">
              <div className="shimmer" style={{ width: 140, height: 44 }} />
              <div className="shimmer" style={{ width: 140, height: 44 }} />
              <div className="shimmer" style={{ width: 140, height: 44 }} />
            </div>
          ) : stations.length === 0 ? (
            <p className="empty-state body-small" data-empty="true" style={{ margin: 0 }}>
              {t("Stations.empty")}
            </p>
          ) : (
            <>
              <div className="station-strip" role="group" aria-label={t("Stations.selectorAria")}>
                {stations.map((station) => {
                  const sTier = stationTier(station);
                  return (
                    <button
                      key={station.station_id}
                      type="button"
                      className="station-chip label-medium"
                      aria-pressed={station.station_id === selectedStationId}
                      onClick={() => setSelectedStationId(station.station_id)}
                    >
                      <span
                        className="station-chip-dot"
                        style={{ background: TIER_META[sTier].color }}
                        aria-hidden="true"
                      />
                      <span>{station.name}</span>
                      <span className="chip-level">{station.level_m.toFixed(2)} m</span>
                    </button>
                  );
                })}
              </div>

              <div className="surface surface--padded">
                <div className="hydrograph-header">
                  <div>
                    <h3 className="title-large" style={{ margin: 0 }}>
                      {selectedStation
                        ? `${selectedStation.name} (${selectedStation.river})`
                        : t("Hydrograph.titleFallback")}
                    </h3>
                    {selectedStation && (
                      <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                        {t("Hydrograph.subActive", {
                          alarm: selectedStation.alarm_stage_m.toFixed(2),
                          flood: selectedStation.flood_stage_m.toFixed(2),
                        })}
                        {stationMarginNote ? `, ${stationMarginNote}` : ""}
                      </p>
                    )}
                  </div>
                  {selectedStation && (
                    <span className="station-live">
                      <span className="value">{selectedStation.level_m.toFixed(2)}</span>
                      <span className="muted body-medium">m</span>
                      <span
                        className="rate body-small"
                        data-direction={
                          selectedStation.rate_of_rise_m_per_hr > 0.005
                            ? "rising"
                            : selectedStation.rate_of_rise_m_per_hr < -0.005
                              ? "falling"
                              : "steady"
                        }
                      >
                        {selectedStation.rate_of_rise_m_per_hr > 0.005
                          ? t("Hydrograph.trendRising")
                          : selectedStation.rate_of_rise_m_per_hr < -0.005
                            ? t("Hydrograph.trendFalling")
                            : t("Hydrograph.trendSteady")}{" "}
                        ({selectedStation.rate_of_rise_m_per_hr > 0 ? "+" : ""}
                        {selectedStation.rate_of_rise_m_per_hr.toFixed(3)} m/hr)
                      </span>
                    </span>
                  )}
                </div>

                {pointsLoading ? (
                  <div className="shimmer" style={{ height: 300 }} aria-busy="true" />
                ) : selectedStation ? (
                  <HydrographChart
                    stationId={selectedStation.station_id}
                    stationName={selectedStation.name}
                    alarmStageMeters={selectedStation.alarm_stage_m}
                    floodStageMeters={selectedStation.flood_stage_m}
                    observations={observations}
                  />
                ) : (
                  <p className="empty-state body-small" data-empty="true" style={{ margin: 0 }}>
                    {t("Hydrograph.subEmpty")}
                  </p>
                )}
              </div>
            </>
          )}
        </section>

        <hr className="section-divider" />

        <section aria-label={t("Officials.sectionAria")}>
          <div className="section-header">
            <h2 className="headline-medium section-title">{t("Officials.title")}</h2>
          </div>
          <div className="disclosures-stack">
            <AlertLog />
            <StatusSummary riskRows={riskRows} stations={stations} lastSync={lastSync} />
          </div>
        </section>

        <footer className="site-footer body-small">
          <span>{t("Footer.data")}</span>
          <Link href="/assistant" className="label-small">
            {t("Header.assistant")}
          </Link>
        </footer>
      </main>

      <nav className="bottom-nav" aria-label={t("BottomNav.aria")}>
        <a href="#check" aria-current="page">
          <SearchIcon />
          <span className="label-small">{t("BottomNav.check")}</span>
        </a>
        <a href="#map">
          <MapIcon />
          <span className="label-small">{t("BottomNav.map")}</span>
        </a>
        <Link
          href={{
            pathname: "/assistant",
            query: selectedCommuneCode ? { code: selectedCommuneCode } : undefined,
          }}
        >
          <AssistantIcon />
          <span className="label-small">{t("BottomNav.assistant")}</span>
        </Link>
      </nav>

      <AssessmentDialog
        communeCode={selectedCommuneCode}
        onClose={() => setSelectedCommuneCode(null)}
      />
    </div>
  );
}
