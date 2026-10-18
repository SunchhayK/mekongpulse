"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FieldReportsList } from "@/components/FieldReportsList";
import { Link } from "@/i18n/navigation";
import { api, ApiError, type Assessment, type EvidencePayload } from "@/lib/api";
import { formatDateTime } from "@/lib/design";
import { CloseIcon } from "./icons";
import { RiskBadge } from "./RiskBadge";
import { VoicePlayer } from "./VoicePlayer";

export interface AssessmentDialogProps {
  /** Commune to assess; null closes the dialog */
  communeCode: string | null;
  onClose: () => void;
  /** Notifies the page when a fresh assessment arrives (for the hero player) */
  onAssessment?: (assessment: Assessment) => void;
}

export function AssessmentDialog({ communeCode, onClose, onAssessment }: AssessmentDialogProps) {
  const t = useTranslations("Dialog");
  const evidenceT = useTranslations("Evidence");
  const locale = useLocale();
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (!communeCode) {
      setAssessment(null);
      setError(null);
      return;
    }
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    api
      .assess(communeCode)
      .then((result) => {
        if (requestId.current !== id) return;
        setAssessment(result);
        onAssessment?.(result);
      })
      .catch((err) => {
        if (requestId.current !== id) return;
        setAssessment(null);
        setError(
          err instanceof ApiError && err.status === 409
            ? t("errorNoTelemetry", { code: communeCode })
            : err instanceof ApiError && err.status === 404
              ? t("errorNotFound", { code: communeCode })
              : `${t("errorUnavailable")}${err instanceof ApiError ? ` (${err.status})` : ""}`,
        );
      })
      .finally(() => {
        if (requestId.current === id) setLoading(false);
      });
  }, [communeCode, onAssessment]);

  // Provenance loads independently: the dialog stays usable while it arrives.
  useEffect(() => {
    if (!communeCode) {
      setEvidence(null);
      setEvidenceError(null);
      return;
    }
    let cancelled = false;
    setEvidenceLoading(true);
    setEvidenceError(null);
    api
      .evidence(communeCode)
      .then((payload) => {
        if (!cancelled) setEvidence(payload);
      })
      .catch(() => {
        if (!cancelled) setEvidenceError(t("evidenceFailed"));
      })
      .finally(() => {
        if (!cancelled) setEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is memoized per namespace
  }, [communeCode]);

  useEffect(() => {
    if (!communeCode) return;
    dialogRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [communeCode, onClose]);

  if (!communeCode) return null;

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("aria", { code: communeCode })}
        tabIndex={-1}
        ref={dialogRef}
      >
        <div className="dialog-head">
          <div>
            {assessment ? (
              <>
                <h2 className="title-large" style={{ margin: 0 }} lang="km">
                  {assessment.commune_name_kh}
                </h2>
                <p className="body-medium muted" style={{ margin: "4px 0 0" }}>
                  {t("updated", {
                    name: assessment.commune_name_en,
                    code: assessment.commune_code,
                    time: formatDateTime(assessment.generated_at, locale),
                  })}
                </p>
              </>
            ) : (
              <>
                <h2 className="title-large" style={{ margin: 0 }}>
                  {t("loadingTitle", { code: communeCode })}
                </h2>
                <p className="body-medium muted" style={{ margin: "4px 0 0" }}>
                  {t("loadingBody")}
                </p>
              </>
            )}
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label={t("closeAria")}>
            <CloseIcon />
          </button>
        </div>

        <p className="body-small muted" style={{ margin: 0 }}>
          {t("readOnly")}
        </p>

        {loading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }} aria-busy="true">
            <div className="shimmer" style={{ height: 48 }} />
            <div className="shimmer" style={{ height: 96 }} />
            <div className="shimmer" style={{ height: 80 }} />
          </div>
        )}

        {!loading && error && (
          <p className="error-banner body-medium" role="alert">
            {error}
          </p>
        )}

        {!loading && assessment && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <RiskBadge
                tier={assessment.risk_tier}
                leadTimeHours={assessment.lead_time_hours ?? undefined}
                size="large"
              />
              {assessment.estimated && (
                <span className="status-pill label-medium">
                  {t("estimated")}
                </span>
              )}
            </div>

            <ul className="directive-list">
              {assessment.directives.map((directive) => (
                <li key={directive.action_code}>
                  <span className="urgency label-small">
                    {directive.family} · {"★".repeat(Math.max(1, 4 - Math.min(3, directive.priority)))}
                  </span>
                  <div className="title-small" lang="km">
                    {directive.title_kh}
                  </div>
                  <div className="body-medium" lang="km">
                    {directive.instruction_kh}
                  </div>
                  <div className="body-small muted" lang="en" style={{ marginTop: 4 }}>
                    <strong>{directive.title_en}</strong> — {directive.instruction_en}
                  </div>
                </li>
              ))}
            </ul>

            <div className="voice-card voice-card--inset">
              <VoicePlayer
                audioSrc={assessment.audio?.url}
                durationSeconds={assessment.audio?.duration_seconds ?? undefined}
                transcriptKhmer={assessment.khmer_bulletin}
                transcriptEnglish={assessment.english_bulletin}
              />
            </div>
          </div>
        )}

        <section className="dialog-section" aria-label={evidenceT("title")}>
          <h3 className="title-medium" style={{ margin: "0 0 10px" }}>
            {evidenceT("title")}
          </h3>
          {evidenceLoading ? (
            <div className="shimmer" style={{ height: 140 }} aria-busy="true" />
          ) : evidence ? (
            <EvidencePanel evidence={evidence} />
          ) : evidenceError ? (
            <p className="body-small muted" style={{ margin: 0 }}>
              {evidenceError}
            </p>
          ) : null}
        </section>

        <section className="dialog-section">
          <FieldReportsList communeCode={communeCode} plain />
        </section>

        <p style={{ margin: "4px 0 0" }}>
          <Link
            className="btn btn--filled btn--compact label-medium"
            href={{ pathname: "/commune", query: { code: communeCode } }}
          >
            {t("openFullPage")}
          </Link>
        </p>
      </div>
    </div>
  );
}
