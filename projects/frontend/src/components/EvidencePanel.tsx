"use client";

import { useLocale, useTranslations } from "next-intl";
import type { EvidencePayload } from "@/lib/api";
import { formatDateTime, formatNumber, formatRate } from "@/lib/design";

export interface EvidencePanelProps {
  /** Deterministic provenance payload from GET /api/v1/communes/{code}/evidence */
  evidence: EvidencePayload;
}

const KNOWN_SOURCES = new Set(["live", "fallback", "cache"]);

/**
 * Compact trust panel: why this risk tier is credible (confidence, QC,
 * cross-checks, the evidence chain) and what it cannot claim (limitations).
 * Payload detail strings are already localized server-side (detail_kh /
 * text_kh); the panel picks the one matching the UI locale instead of
 * re-translating them.
 */
export function EvidencePanel({ evidence }: EvidencePanelProps) {
  const t = useTranslations("Evidence");
  const locale = useLocale();
  const payloadText = (en: string, kh: string) => (locale === "km" ? kh : en);
  const { station } = evidence;
  const sourceLabel = KNOWN_SOURCES.has(station.source)
    ? t(`station.sources.${station.source}`)
    : station.source;

  return (
    <div className="evidence-panel">
      <div className="evidence-head">
        <span className="confidence-chip label-medium" data-confidence={evidence.confidence}>
          <span className="dot" aria-hidden="true" />
          {t("confidenceLabel")} · {t(`confidence.levels.${evidence.confidence}`)}
        </span>
        <span className="body-small muted">
          {t("score", { score: formatNumber(evidence.score, locale) })} ·{" "}
          {t("generatedAt", { time: formatDateTime(evidence.generated_at, locale) })}
        </span>
      </div>

      {evidence.confidence_reasons.length > 0 && (
        <ul className="evidence-reasons" aria-label={t("reasonsAria")}>
          {evidence.confidence_reasons.map((id) => (
            <li key={id} className="evidence-reason label-small">
              {t(`confidence.reasons.${id}`)}
            </li>
          ))}
        </ul>
      )}

      <div className="evidence-block">
        <h3 className="evidence-block-title">{t("station.title")}</h3>
        <p className="body-medium" style={{ margin: "0 0 6px" }}>
          {station.name} <span className="mono body-small muted">{station.station_id}</span>
        </p>
        <dl className="evidence-facts">
          <div className="evidence-fact">
            <dt className="label-small">{t("station.source")}</dt>
            <dd className="body-small">{sourceLabel}</dd>
          </div>
          <div className="evidence-fact">
            <dt className="label-small">{t("station.recordedAt")}</dt>
            <dd className="body-small mono">{formatDateTime(station.recorded_at, locale)}</dd>
          </div>
          <div className="evidence-fact">
            <dt className="label-small">{t("station.freshness")}</dt>
            <dd className="body-small">
              {t(`station.freshnessLevels.${station.freshness}`)} ·{" "}
              {t("station.ageMinutes", { count: station.age_minutes })}
            </dd>
          </div>
          <div className="evidence-fact">
            <dt className="label-small">{t("station.distance")}</dt>
            <dd className="body-small">
              {station.distance_km == null
                ? t("station.distanceUnknown")
                : t("station.distanceKm", { km: station.distance_km.toFixed(1) })}
            </dd>
          </div>
          <div className="evidence-fact">
            <dt className="label-small">{t("station.level")}</dt>
            <dd className="body-small mono">
              {station.level_m.toFixed(2)} m · {formatRate(station.rate_of_rise_m_per_hr)}
            </dd>
          </div>
          <div className="evidence-fact">
            <dt className="label-small">{t("station.stages")}</dt>
            <dd className="body-small mono">
              {station.alarm_stage_m.toFixed(2)} m / {station.flood_stage_m.toFixed(2)} m
            </dd>
          </div>
        </dl>
      </div>

      <div className="evidence-block">
        <div className="evidence-block-head">
          <h3 className="evidence-block-title">{t("qc.title")}</h3>
          <span className="evidence-verdict label-small" data-status={evidence.qc.status}>
            {t(`qc.statuses.${evidence.qc.status}`)}
          </span>
        </div>
        <ul className="evidence-checks">
          {evidence.qc.checks.map((check) => (
            <li key={check.id} data-status={check.status}>
              <span className="status-dot" aria-hidden="true" />
              <span className="check-name label-medium">{t(`qc.checks.${check.id}`)}</span>
              <span className="evidence-verdict label-small" data-status={check.status}>
                {t(`qc.statuses.${check.status}`)}
              </span>
              <p className="body-small muted check-detail">
                {payloadText(check.detail, check.detail_kh)}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <div className="evidence-block">
        <h3 className="evidence-block-title">{t("crossChecks.title")}</h3>
        <ul className="evidence-checks">
          {evidence.cross_checks.map((check) => (
            <li key={check.id} data-status={check.status}>
              <span className="status-dot" aria-hidden="true" />
              <span className="check-name label-medium">{t(`crossChecks.${check.id}`)}</span>
              <span className="evidence-verdict label-small" data-status={check.status}>
                {t(`crossChecks.statuses.${check.status}`)}
              </span>
              <p className="body-small muted check-detail">
                {payloadText(check.detail, check.detail_kh)}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <div className="evidence-block">
        <h3 className="evidence-block-title">{t("chain.title")}</h3>
        <ol className="evidence-chain">
          {evidence.evidence_chain.map((step) => (
            <li key={step.id} className="body-small">
              {payloadText(step.text_en, step.text_kh)}
            </li>
          ))}
        </ol>
      </div>

      <p className="evidence-limitations body-small" role="note">
        <strong>{t("limitations.title")}</strong>{" "}
        {payloadText(evidence.limitations.text_en, evidence.limitations.text_kh)}
      </p>
    </div>
  );
}
