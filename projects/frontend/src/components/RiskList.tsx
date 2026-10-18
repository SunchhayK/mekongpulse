"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CommuneRiskRow } from "@/lib/api";
import { downloadCsv, riskRegisterCsv } from "@/lib/csv";
import { formatMeters, formatNumber, TIER_META, tierSeverity } from "@/lib/design";

export interface RiskListProps {
  rows: CommuneRiskRow[];
  onSelect: (communeCode: string) => void;
}

const MAX_ROWS = 100;

export function RiskList({ rows, onSelect }: RiskListProps) {
  const t = useTranslations("RiskList");
  const tableT = useTranslations("RiskTable");
  const tierT = useTranslations("Tier");
  const locale = useLocale();
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

  function exportCsv() {
    const now = new Date();
    const stamp = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-");
    downloadCsv(`mekongpulse-risk-register-${stamp}.csv`, riskRegisterCsv(rows));
  }

  return (
    <div className="card" id="risk">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          {t("title")}
        </h2>
        <span className="card-actions">
          <label className="body-small muted">
            <span className="sr-only">{t("filterAria")}</span>
            <select
              className="province-select label-medium"
              id="province-filter"
              name="province"
              value={province}
              onChange={(event) => setProvince(event.target.value)}
            >
              <option value="ALL">{t("allProvinces", { count: formatNumber(rows.length, locale) })}</option>
              {provinces.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--filled btn--compact label-medium no-print"
            onClick={exportCsv}
            disabled={rows.length === 0}
            aria-label={t("exportAria")}
          >
            {t("export")}
          </button>
        </span>
      </div>
      {filtered.length === 0 ? (
        <p className="empty-state body-medium" data-empty="true">
          {t("empty")}
        </p>
      ) : (
        <>
          <div className="risk-table-wrap">
            <table className="risk-table body-small">
              <thead>
                <tr>
                  <th scope="col">{tableT("commune")}</th>
                  <th scope="col">{tableT("province")}</th>
                  <th scope="col">{tableT("tier")}</th>
                  <th scope="col">{tableT("lead")}</th>
                  <th scope="col">{tableT("level")}</th>
                  <th scope="col">{tableT("score")}</th>
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
                    aria-label={t("rowAria", { name: row.commune_name_en, tier: tierT(row.tier) })}
                  >
                    <td>
                      <span lang="km">{row.commune_name_kh}</span>
                      <br />
                      {row.commune_name_en}{" "}
                      <span className="muted">{row.estimated ? t("estimated") : ""}</span>
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
                    <td className="muted">
                      {row.lead_time_hours != null ? tierT("lead", { hours: row.lead_time_hours }) : "—"}
                    </td>
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
              {t("footer", { max: MAX_ROWS, total })}
            </p>
          )}
        </>
      )}
    </div>
  );
}
