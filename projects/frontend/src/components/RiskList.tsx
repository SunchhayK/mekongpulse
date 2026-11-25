"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CommuneRiskRow, FloodRiskTier } from "@/lib/api";
import { downloadCsv, riskRegisterCsv } from "@/lib/csv";
import { formatNumber, tierSeverity } from "@/lib/design";
import { RiskBadge } from "./RiskBadge";

export interface RiskListProps {
  rows: CommuneRiskRow[];
  tierFilter?: FloodRiskTier | null;
  onClearTierFilter?: () => void;
  onSelect: (communeCode: string) => void;
}

const DEFAULT_VISIBLE = 8;
const MAX_ALL_ROWS = 100;

export function RiskList({
  rows,
  tierFilter = null,
  onClearTierFilter,
  onSelect,
}: RiskListProps) {
  const t = useTranslations("RiskList");
  const tierT = useTranslations("Tier");
  const locale = useLocale();
  const [province, setProvince] = useState("ALL");
  const [showAll, setShowAll] = useState(false);

  const provinces = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((row) => {
      if (row.province) set.add(row.province);
    });
    return [...set].sort();
  }, [rows]);

  const filtered = useMemo(() => {
    let subset = province === "ALL" ? rows : rows.filter((row) => row.province === province);
    if (tierFilter) {
      subset = subset.filter((row) => row.tier === tierFilter);
    } else if (!showAll) {
      const elevated = subset.filter((row) => tierSeverity(row.tier) >= tierSeverity("ADVISORY"));
      subset = elevated.length > 0 ? elevated : subset;
    }
    return [...subset].sort(
      (a, b) =>
        tierSeverity(b.tier) - tierSeverity(a.tier) ||
        b.score - a.score ||
        a.commune_name_en.localeCompare(b.commune_name_en),
    );
  }, [rows, province, tierFilter, showAll]);

  const visibleRows = filtered.slice(0, showAll || tierFilter ? MAX_ALL_ROWS : DEFAULT_VISIBLE);
  const canToggleAll = !tierFilter && rows.length > visibleRows.length;

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
    <section className="surface watch-panel" id="risk" aria-label={t("title")}>
      <div className="watch-panel-head">
        <div>
          <h2 className="title-medium" style={{ margin: 0 }}>
            {t("title")}
          </h2>
          {tierFilter && (
            <p className="body-small muted" style={{ margin: "2px 0 0" }}>
              {t("filteredBy", { tier: tierT(tierFilter) })}
            </p>
          )}
        </div>
        <div className="watch-panel-controls">
          {tierFilter && onClearTierFilter && (
            <button
              type="button"
              className="btn btn--outline btn--compact label-small"
              onClick={onClearTierFilter}
            >
              {t("clearFilter")}
            </button>
          )}
          <label>
            <span className="sr-only">{t("filterAria")}</span>
            <select
              className="province-select"
              id="province-filter"
              name="province"
              value={province}
              onChange={(event) => setProvince(event.target.value)}
            >
              <option value="ALL">
                {t("allProvinces", { count: formatNumber(rows.length, locale) })}
              </option>
              {provinces.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {visibleRows.length === 0 ? (
        <div style={{ padding: 18 }}>
          <p className="empty-state body-small" data-empty="true" style={{ margin: 0 }}>
            {tierFilter ? t("emptyTier", { tier: tierT(tierFilter) }) : t("empty")}
          </p>
        </div>
      ) : (
        <ul className="commune-list">
          {visibleRows.map((row) => (
            <li key={row.commune_code}>
              <button
                type="button"
                className="commune-row-btn"
                onClick={() => onSelect(row.commune_code)}
                aria-label={t("rowAria", { name: row.commune_name_en, tier: tierT(row.tier) })}
              >
                <span className="commune-row-main">
                  <span className="title-small" lang="km">
                    {row.commune_name_kh}
                  </span>
                  <span className="body-small commune-row-sub">
                    {row.commune_name_en}
                    {row.province ? `, ${row.province}` : ""}
                  </span>
                </span>
                <span className="commune-row-badges">
                  <RiskBadge
                    tier={row.tier}
                    leadTimeHours={row.lead_time_hours ?? undefined}
                    size="small"
                  />
                  {row.forecast_tier && (
                    <span className="forecast-badge label-small" data-tier={row.forecast_tier}>
                      {row.forecast_lead_days != null
                        ? tierT("forecastDays", {
                            days: row.forecast_lead_days,
                            tier: tierT(row.forecast_tier),
                          })
                        : tierT("forecast", { tier: tierT(row.forecast_tier) })}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="watch-panel-foot">
        {canToggleAll || showAll ? (
          <button
            type="button"
            className="btn btn--outline btn--compact label-small"
            onClick={() => setShowAll((prev) => !prev)}
          >
            {showAll
              ? t("showElevated")
              : t("showAll", { count: formatNumber(rows.length, locale) })}
          </button>
        ) : (
          <span className="body-small muted">
            {t("countSummary", { count: formatNumber(filtered.length, locale) })}
          </span>
        )}
        <button
          type="button"
          className="btn btn--outline btn--compact label-small no-print"
          onClick={exportCsv}
          disabled={rows.length === 0}
          aria-label={t("exportAria")}
        >
          {t("export")}
        </button>
      </div>
    </section>
  );
}
