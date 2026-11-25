"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api, type AlertLogEntry } from "@/lib/api";
import { formatDateTime, formatNumber, TIER_META } from "@/lib/design";

const LOG_LIMIT = 50;

/** Recent alerts sent — tucked inside a native <details> disclosure on the dashboard. */
export function AlertLog() {
  const t = useTranslations("AlertLog");
  const tierT = useTranslations("Tier");
  const locale = useLocale();
  const [entries, setEntries] = useState<AlertLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .alertLog(LOG_LIMIT)
      .then((next) => {
        if (!cancelled) {
          setEntries(next);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <details className="disclosure alerts-disclosure" id="alerts">
      <summary className="label-large">
        <span>{t("title")}</span>
        <span className="disclosure-summary-meta label-small">
          {loading
            ? t("loading")
            : failed
              ? t("unavailableShort")
              : t("count", { count: entries.length })}
        </span>
      </summary>
      <div className="disclosure-body">
        {loading ? (
          <div className="shimmer" style={{ height: 120 }} aria-busy="true" />
        ) : failed ? (
          <p className="body-small muted" style={{ margin: 0 }}>
            {t("failed")}
          </p>
        ) : entries.length === 0 ? (
          <p className="empty-state body-small" data-empty="true" style={{ margin: 0 }}>
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
                          aria-label={t("listenAria", {
                            name: entry.commune_name_en || entry.commune_code,
                          })}
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
    </details>
  );
}
