"use client";

import { useLocale, useTranslations } from "next-intl";
import type { CommuneRiskRow, StationTelemetry } from "@/lib/api";
import { formatDateTime, formatMeters, formatNumber, TIER_META, TIER_ORDER, tierSeverity } from "@/lib/design";

export interface StatusSummaryProps {
  riskRows: CommuneRiskRow[];
  stations: StationTelemetry[];
  lastSync: string | null;
}

const TOP_RISK_LIMIT = 10;

function stationStatusKey(station: StationTelemetry): "aboveFlood" | "aboveAlarm" | "belowAlarm" {
  if (station.level_m >= station.flood_stage_m) return "aboveFlood";
  if (station.level_m >= station.alarm_stage_m) return "aboveAlarm";
  return "belowAlarm";
}

/** Printable basin status report for shift handover (FR-10). */
export function StatusSummary({ riskRows, stations, lastSync }: StatusSummaryProps) {
  const t = useTranslations("Summary");
  const tableT = useTranslations("RiskTable");
  const tierT = useTranslations("Tier");
  const locale = useLocale();
  const tierCounts: Record<string, number> = { NORMAL: 0, ADVISORY: 0, WARNING: 0, DANGER: 0 };
  riskRows.forEach((row) => {
    tierCounts[row.tier] = (tierCounts[row.tier] ?? 0) + 1;
  });

  const topRisk = [...riskRows]
    .filter((row) => tierSeverity(row.tier) >= tierSeverity("ADVISORY"))
    .sort((a, b) => tierSeverity(b.tier) - tierSeverity(a.tier) || b.score - a.score)
    .slice(0, TOP_RISK_LIMIT);

  return (
    <div className="card" id="summary" aria-label={t("aria")}>
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          {t("title")}
        </h2>
        <button
          type="button"
          className="btn btn--filled btn--compact label-medium no-print"
          onClick={() => window.print()}
          aria-label={t("printAria")}
        >
          {t("print")}
        </button>
      </div>

      <ul className="risk-legend">
        {TIER_ORDER.map((tier) => (
          <li className="item" key={tier}>
            <span className="swatch" style={{ background: TIER_META[tier].color }} aria-hidden="true" />
            <span className="body-small">{tierT(tier)}</span>
            <span className="count mono body-medium">{formatNumber(tierCounts[tier] ?? 0, locale)}</span>
          </li>
        ))}
      </ul>
      <p className="body-medium" style={{ margin: "12px 0 0" }}>
        {t("scored", {
          count: riskRows.length,
          time: lastSync ? formatDateTime(lastSync, locale) : t("awaitingSync"),
        })}
      </p>

      <h3 className="section-label label-small" style={{ margin: "16px 0 8px" }}>
        {t("stationSection")}
      </h3>
      {stations.length === 0 ? (
        <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
          {t("stationEmpty")}
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small">
            <thead>
              <tr>
                <th scope="col">{t("stStation")}</th>
                <th scope="col">{t("stRiver")}</th>
                <th scope="col">{t("stLevel")}</th>
                <th scope="col">{t("stAlarm")}</th>
                <th scope="col">{t("stFlood")}</th>
                <th scope="col">{t("stStatus")}</th>
                <th scope="col">{t("stRecorded")}</th>
              </tr>
            </thead>
            <tbody>
              {stations.map((station) => (
                <tr key={station.station_id}>
                  <td>{station.name}</td>
                  <td className="muted">{station.river}</td>
                  <td className="mono">{formatMeters(station.level_m)}</td>
                  <td className="mono muted">{formatMeters(station.alarm_stage_m)}</td>
                  <td className="mono muted">{formatMeters(station.flood_stage_m)}</td>
                  <td className="mono">{t(stationStatusKey(station))}</td>
                  <td className="muted">{formatDateTime(station.recorded_at, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-label label-small" style={{ margin: "16px 0 8px" }}>
        {t("topTitle", { limit: TOP_RISK_LIMIT })}
      </h3>
      {topRisk.length === 0 ? (
        <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
          {t("empty")}
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small">
            <thead>
              <tr>
                <th scope="col">{tableT("commune")}</th>
                <th scope="col">{tableT("province")}</th>
                <th scope="col">{tableT("tier")}</th>
                <th scope="col">{tableT("score")}</th>
                <th scope="col">{tableT("lead")}</th>
              </tr>
            </thead>
            <tbody>
              {topRisk.map((row) => (
                <tr key={row.commune_code}>
                  <td>
                    <span lang="km">{row.commune_name_kh}</span>
                    <br />
                    {row.commune_name_en}
                  </td>
                  <td className="muted">{row.province ?? "—"}</td>
                  <td>
                    <span className="tier-cell">
                      <span
                        className="tier-dot"
                        style={{ background: TIER_META[row.tier].color }}
                        aria-hidden="true"
                      />
                      {tierT(row.tier)}
                    </span>
                  </td>
                  <td>{row.score}</td>
                  <td className="muted">
                    {row.lead_time_hours != null ? tierT("lead", { hours: row.lead_time_hours }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="body-small muted" style={{ margin: "14px 0 0" }} suppressHydrationWarning>
        {t("generated", { time: formatDateTime(new Date().toISOString(), locale) })}
      </p>
    </div>
  );
}
