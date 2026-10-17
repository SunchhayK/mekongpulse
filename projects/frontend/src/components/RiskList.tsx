"use client";

import { useMemo, useState } from "react";
import type { CommuneRiskRow } from "@/lib/api";
import { formatMeters, TIER_META, tierSeverity } from "@/lib/design";

export interface RiskListProps {
  rows: CommuneRiskRow[];
  onSelect: (communeCode: string) => void;
}

const MAX_ROWS = 100;

export function RiskList({ rows, onSelect }: RiskListProps) {
  const [province, setProvince] = useState("ALL");

  const provinces = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((row) => {
      if (row.province) set.add(row.province);
    });
    return [...set].sort();
  }, [rows]);

  const filtered = useMemo(() => {
    const subset = province === "ALL" ? rows : rows.filter((row) => row.province === province);
    return [...subset]
      .sort(
        (a, b) =>
          tierSeverity(b.tier) - tierSeverity(a.tier) ||
          b.score - a.score ||
          a.commune_name_en.localeCompare(b.commune_name_en),
      )
      .slice(0, MAX_ROWS);
  }, [rows, province]);

  const total = province === "ALL" ? rows.length : rows.filter((r) => r.province === province).length;

  return (
    <div className="card" id="risk">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          Risk register / តារាងហានិភ័យ
        </h2>
        <label className="body-small muted">
          <span className="sr-only">Filter by province</span>
          <select
            className="province-select label-medium"
            value={province}
            onChange={(event) => setProvince(event.target.value)}
          >
            <option value="ALL">All provinces · {rows.length.toLocaleString()}</option>
            {provinces.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {filtered.length === 0 ? (
        <p className="empty-state body-medium" data-empty="true">
          No scored communes yet. Telemetry sync runs every 15 minutes.
        </p>
      ) : (
        <>
          <div className="risk-table-wrap">
            <table className="risk-table body-small">
              <thead>
                <tr>
                  <th scope="col">Commune</th>
                  <th scope="col">Province</th>
                  <th scope="col">Tier</th>
                  <th scope="col">Lead</th>
                  <th scope="col">Level</th>
                  <th scope="col">Score</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr
                    key={row.commune_code}
                    tabIndex={0}
                    onClick={() => onSelect(row.commune_code)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") onSelect(row.commune_code);
                    }}
                    aria-label={`Assess ${row.commune_name_en}, ${TIER_META[row.tier].labelEn} tier`}
                  >
                    <td>
                      <span lang="km">{row.commune_name_kh}</span>
                      <br />
                      {row.commune_name_en}{" "}
                      <span className="muted">{row.estimated ? "· estimated" : ""}</span>
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
                    <td className="muted">{row.lead_time_hours != null ? `~${row.lead_time_hours}h` : "—"}</td>
                    <td className="muted">
                      {row.station_level_m != null ? `${formatMeters(row.station_level_m)} m` : "—"}
                    </td>
                    <td>{row.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {total > MAX_ROWS && (
            <p className="body-small muted" style={{ marginTop: 8 }}>
              Showing the {MAX_ROWS} highest-risk of {total.toLocaleString()} scored communes. Pick a
              province to narrow the register.
            </p>
          )}
        </>
      )}
    </div>
  );
}
