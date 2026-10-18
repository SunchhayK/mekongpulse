"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api, ApiError, type AlertLogEntry } from "@/lib/api";
import { formatDateTime, formatNumber, TIER_META } from "@/lib/design";

const LOG_LIMIT = 50;

/** Alert dispatch log for the officials' console (FR-10). */
export function AlertLog() {
  const t = useTranslations("AlertLog");
  const tierT = useTranslations("Tier");
  const locale = useLocale();
  const [entries, setEntries] = useState<AlertLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .alertLog(LOG_LIMIT)
      .then((next) => {
        if (!cancelled) setEntries(next);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status >= 500
            ? t("unavailable", { status: err.status })
            : t("failed"),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="card" id="alerts" aria-label={t("aria")}>
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          {t("title")}
        </h2>
        <span className="body-small muted">{t("hint", { limit: LOG_LIMIT })}</span>
      </div>

      {loading ? (
        <div className="shimmer" style={{ height: 140 }} aria-busy="true" />
      ) : error ? (
        <p className="error-banner body-medium" role="alert">
          {error}
        </p>
      ) : entries.length === 0 ? (
        <p className="empty-state body-medium" data-empty="true">
          {t("empty")}
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small" aria-label={t("tableAria")}>
            <thead>
              <tr>
                <th scope="col">{t("colDispatched")}</th>
                <th scope="col">{t("colCommune")}</th>
                <th scope="col">{t("colProvince")}</th>
                <th scope="col">{t("colTier")}</th>
                <th scope="col">{t("colDirective")}</th>
                <th scope="col">{t("colRecipients")}</th>
                <th scope="col">{t("colVoice")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id ?? `${entry.commune_code}-${entry.dispatched_at}`}>
                  <td className="muted">{formatDateTime(entry.dispatched_at, locale)}</td>
                  <td>
                    <span lang="km">{entry.commune_name_kh || entry.commune_code}</span>
                    <br />
                    {entry.commune_name_en || entry.commune_code}
                  </td>
                  <td className="muted">{entry.province ?? "—"}</td>
                  <td>
                    <span className="tier-cell">
                      <span
                        className="tier-dot"
                        style={{ background: TIER_META[entry.risk_tier].color }}
                        aria-hidden="true"
                      />
                      {tierT(entry.risk_tier)}
                    </span>
                  </td>
                  <td>
                    {entry.directive_title || "—"}
                    {entry.bulletin_text ? (
                      <details className="body-small" style={{ marginTop: 4 }}>
                        <summary className="muted">{t("bulletin")}</summary>
                        <p lang="km" className="muted" style={{ margin: "6px 0 0" }}>
                          {entry.bulletin_text}
                        </p>
                      </details>
                    ) : null}
                  </td>
                  <td className="mono">{formatNumber(entry.recipients_count, locale)}</td>
                  <td>
                    {entry.audio_url ? (
                      <a
                        href={entry.audio_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={t("listenAria", { name: entry.commune_name_en || entry.commune_code })}
                      >
                        {t("listen")}
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
