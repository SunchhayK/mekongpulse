"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api, ApiError, type FieldReport } from "@/lib/api";
import { formatDateTime } from "@/lib/design";

export interface FieldReportsListProps {
  communeCode: string;
  /** Render without the surrounding surface (used inside disclosures/dialog). */
  plain?: boolean;
}

const DEFAULT_LIMIT = 20;
const KNOWN_SOURCES = new Set(["web", "telegram"]);

function relativeParts(iso: string): { unit: "justNow" | "minutes" | "hours" | "days"; count: number } | null {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (minutes < 1) return { unit: "justNow", count: 0 };
  if (minutes < 60) return { unit: "minutes", count: minutes };
  const hours = Math.round(minutes / 60);
  if (hours < 24) return { unit: "hours", count: hours };
  return { unit: "days", count: Math.round(hours / 24) };
}

/** Ground-truth reports filed by local officials and residents. */
export function FieldReportsList({ communeCode, plain = false }: FieldReportsListProps) {
  const t = useTranslations("FieldReports");
  const locale = useLocale();
  const [reports, setReports] = useState<FieldReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function relativeLabel(iso: string): string {
    const parts = relativeParts(iso);
    if (!parts) return "—";
    if (parts.unit === "justNow") return t("relative.justNow");
    return t(`relative.${parts.unit}`, { count: parts.count });
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .reports(communeCode, DEFAULT_LIMIT)
      .then((payload) => {
        if (!cancelled) setReports(payload.reports);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is memoized per namespace
  }, [communeCode]);

  const body = (
    <>
      {loading ? (
        <div className="shimmer" style={{ height: 84 }} aria-busy="true" />
      ) : error ? (
        <p className="body-small muted" style={{ margin: 0 }}>
          {error}
        </p>
      ) : reports.length === 0 ? (
        <p className="empty-state body-small" data-empty="true" style={{ margin: 0 }}>
          {t("empty")}
        </p>
      ) : (
        <ul className="reports-list">
          {reports.map((report) => (
            <li key={report.id} className="report-item">
              <div className="report-line">
                <span className="report-status label-medium" data-status={report.status}>
                  {t(`statuses.${report.status}`)}
                </span>
                <span className="body-small muted">
                  {relativeLabel(report.reported_at)} ({formatDateTime(report.reported_at, locale)})
                </span>
              </div>
              {report.note && (
                <p className="body-small" style={{ margin: 0 }}>
                  {report.note}
                </p>
              )}
              <p className="body-small muted" style={{ margin: 0 }}>
                {report.reporter_label ? t("reportedBy", { name: report.reporter_label }) : t("anonymous")}
                {", "}
                {KNOWN_SOURCES.has(report.source) ? t(`sources.${report.source}`) : report.source}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  if (plain) return <div className="reports-plain">{body}</div>;

  return (
    <section className="surface surface--padded" aria-label={t("title")}>
      <div className="section-header">
        <h2 className="title-medium section-title">{t("title")}</h2>
      </div>
      {body}
    </section>
  );
}
