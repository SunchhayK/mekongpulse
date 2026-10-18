"use client";

import type { CommuneRiskRow, StationTelemetry } from "@/lib/api";
import { formatDateTime, formatMeters, TIER_META, TIER_ORDER, tierSeverity } from "@/lib/design";

export interface StatusSummaryProps {
  riskRows: CommuneRiskRow[];
  stations: StationTelemetry[];
  lastSync: string | null;
}

const TOP_RISK_LIMIT = 10;

function stationStatus(station: StationTelemetry): string {
  if (station.level_m >= station.flood_stage_m) return "ABOVE FLOOD";
  if (station.level_m >= station.alarm_stage_m) return "ABOVE ALARM";
  return "BELOW ALARM";
}

/** Printable basin status report for shift handover (FR-10). */
export function StatusSummary({ riskRows, stations, lastSync }: StatusSummaryProps) {
  const tierCounts: Record<string, number> = { NORMAL: 0, ADVISORY: 0, WARNING: 0, DANGER: 0 };
  riskRows.forEach((row) => {
    tierCounts[row.tier] = (tierCounts[row.tier] ?? 0) + 1;
  });

  const topRisk = [...riskRows]
    .filter((row) => tierSeverity(row.tier) >= tierSeverity("ADVISORY"))
    .sort((a, b) => tierSeverity(b.tier) - tierSeverity(a.tier) || b.score - a.score)
    .slice(0, TOP_RISK_LIMIT);

  return (
    <div className="card" id="summary" aria-label="Basin status summary">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          Basin status summary / សេចក្តីសង្ខេបស្ថានភាពអាង
        </h2>
        <button
          type="button"
          className="btn btn--filled btn--compact label-medium no-print"
          onClick={() => window.print()}
          aria-label="Print or save this basin status summary as a PDF"
        >
          Print / PDF
        </button>
      </div>

      <ul className="risk-legend">
        {TIER_ORDER.map((tier) => (
          <li className="item" key={tier}>
            <span className="swatch" style={{ background: TIER_META[tier].color }} aria-hidden="true" />
            <span className="body-small" lang="km">
              {TIER_META[tier].labelKh}
            </span>
            <span className="body-small muted">{TIER_META[tier].labelEn}</span>
            <span className="count mono body-medium">{(tierCounts[tier] ?? 0).toLocaleString()}</span>
          </li>
        ))}
      </ul>
      <p className="body-medium" style={{ margin: "12px 0 0" }}>
        {riskRows.length.toLocaleString()} communes scored · last telemetry sync{" "}
        {lastSync ? formatDateTime(lastSync) : "awaiting first sync"}
      </p>

      <h3 className="section-label label-small" style={{ margin: "16px 0 8px" }}>
        Station status / ស្ថានភាពស្ថានីយ
      </h3>
      {stations.length === 0 ? (
        <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
          No telemetry yet. Last sync runs every 15 minutes.
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small">
            <thead>
              <tr>
                <th scope="col">Station</th>
                <th scope="col">River</th>
                <th scope="col">Level (m)</th>
                <th scope="col">Alarm (m)</th>
                <th scope="col">Flood (m)</th>
                <th scope="col">Status</th>
                <th scope="col">Recorded</th>
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
                  <td className="mono">{stationStatus(station)}</td>
                  <td className="muted">{formatDateTime(station.recorded_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-label label-small" style={{ margin: "16px 0 8px" }}>
        Highest risk / ហានិភ័យខ្ពស់ (top {TOP_RISK_LIMIT})
      </h3>
      {topRisk.length === 0 ? (
        <p className="body-small muted" data-empty="true" style={{ margin: 0 }}>
          No elevated communes right now.
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small">
            <thead>
              <tr>
                <th scope="col">Commune</th>
                <th scope="col">Province</th>
                <th scope="col">Tier</th>
                <th scope="col">Score</th>
                <th scope="col">Lead</th>
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
                      {TIER_META[row.tier].labelEn}
                    </span>
                  </td>
                  <td>{row.score}</td>
                  <td className="muted">
                    {row.lead_time_hours != null ? `~${row.lead_time_hours}h` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="body-small muted" style={{ margin: "14px 0 0" }} suppressHydrationWarning>
        Generated at {formatDateTime(new Date().toISOString())}
      </p>
    </div>
  );
}
