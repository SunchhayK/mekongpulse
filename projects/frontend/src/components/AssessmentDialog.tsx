"use client";

import { useEffect, useId, useRef, useState } from "react";
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
  /** Notifies the page when a fresh assessment arrives */
  onAssessment?: (assessment: Assessment) => void;
}

export function AssessmentDialog({ communeCode, onClose, onAssessment }: AssessmentDialogProps) {
  const t = useTranslations("Dialog");
  const evidenceT = useTranslations("Evidence");
  const reportsT = useTranslations("FieldReports");
  const communeT = useTranslations("Commune");
  const locale = useLocale();
  const titleId = useId();
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const requestId = useRef(0);

  // Open/close native <dialog> via showModal() so it lives in the browser top layer
  // above Leaflet panes without manual z-index hacks, focus traps, or Esc handlers.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (communeCode) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [communeCode]);

  // Light-dismiss fallback for browsers without <dialog closedby="any"> (e.g., Safari).
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || typeof HTMLDialogElement === "undefined") return;
    if ("closedBy" in HTMLDialogElement.prototype) return;

    const isOutside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let pressedOutside = false;
    const onPointerDown = (e: PointerEvent) => {
      pressedOutside = isOutside(e);
    };
    const onPointerUp = (e: PointerEvent) => {
      if (pressedOutside && isOutside(e)) dialog.close();
    };
    dialog.addEventListener("pointerdown", onPointerDown);
    dialog.addEventListener("pointerup", onPointerUp);
    return () => {
      dialog.removeEventListener("pointerdown", onPointerDown);
      dialog.removeEventListener("pointerup", onPointerUp);
    };
  }, []);

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
              : t("errorUnavailable"),
        );
      })
      .finally(() => {
        if (requestId.current === id) setLoading(false);
      });
  }, [communeCode, onAssessment, t]);

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

  const closedByProps = { closedby: "any" } as Record<string, string>;

  return (
    <dialog
      ref={dialogRef}
      className="assessment-dialog"
      aria-labelledby={titleId}
      onClose={() => {
        if (dialogRef.current) dialogRef.current.returnValue = "";
        onClose();
      }}
      {...closedByProps}
    >
      {communeCode && (
        <div className="dialog-inner">
          <div className="dialog-head">
            <div>
              {assessment ? (
                <>
                  <h1 id={titleId} className="dialog-title" lang="km">
                    {assessment.commune_name_kh}
                  </h1>
                  <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                    {t("updated", {
                      name: assessment.commune_name_en,
                      time: formatDateTime(assessment.generated_at, locale),
                    })}
                  </p>
                </>
              ) : loading ? (
                <>
                  <h1 id={titleId} className="dialog-title">
                    {t("loadingTitle", { code: communeCode })}
                  </h1>
                  <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                    {t("loadingBody")}
                  </p>
                </>
              ) : (
                <>
                  <h1 id={titleId} className="dialog-title" lang={evidence?.commune_name_kh ? "km" : undefined}>
                    {evidence?.commune_name_kh || t("fallbackTitle", { code: communeCode })}
                  </h1>
                  {evidence?.commune_name_en && (
                    <p className="body-small muted" style={{ margin: "4px 0 0" }}>
                      {evidence.commune_name_en}
                    </p>
                  )}
                </>
              )}
            </div>
            <button
              type="button"
              className="close-btn"
              onClick={() => dialogRef.current?.close()}
              aria-label={t("closeAria")}
              autoFocus
            >
              <CloseIcon />
            </button>
          </div>

          {loading && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }} aria-busy="true">
              <div className="shimmer" style={{ height: 44 }} />
              <div className="shimmer" style={{ height: 96 }} />
              <div className="shimmer" style={{ height: 80 }} />
            </div>
          )}

          {!loading && error && (
            <p className="error-banner body-small" role="alert">
              {error}
            </p>
          )}

          {!loading && assessment && (
            <>
              <div className="commune-facts">
                <RiskBadge
                  tier={assessment.risk_tier}
                  leadTimeHours={assessment.lead_time_hours ?? undefined}
                  size="large"
                />
                {assessment.estimated && (
                  <span className="status-pill label-small">{t("estimated")}</span>
                )}
              </div>

              <div className="voice-card">
                <VoicePlayer
                  audioSrc={assessment.audio?.url}
                  durationSeconds={assessment.audio?.duration_seconds ?? undefined}
                  transcriptKhmer={assessment.khmer_bulletin}
                  transcriptEnglish={assessment.english_bulletin}
                />
              </div>

              {assessment.directives.length > 0 && (
                <div>
                  <h2 className="title-small" style={{ margin: "0 0 10px" }}>
                    {communeT("directivesTitle")}
                  </h2>
                  <ol className="directive-list">
                    {assessment.directives.map((directive) => (
                      <li key={directive.action_code}>
                        <div className="directive-content">
                          <div className="title-small" lang="km">
                            {directive.title_kh}
                          </div>
                          <div className="body-small" lang="km">
                            {directive.instruction_kh}
                          </div>
                          <div className="body-small muted" lang="en">
                            {directive.title_en}: {directive.instruction_en}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </>
          )}

          <div className="disclosures-stack">
            <details className="disclosure">
              <summary className="label-medium">
                <span>{evidenceT("title")}</span>
                {evidence && (
                  <span className="disclosure-summary-meta label-small">
                    {evidenceT(`confidence.levels.${evidence.confidence}`)}
                  </span>
                )}
              </summary>
              <div className="disclosure-body">
                {evidenceLoading ? (
                  <div className="shimmer" style={{ height: 120 }} aria-busy="true" />
                ) : evidence ? (
                  <EvidencePanel evidence={evidence} />
                ) : evidenceError ? (
                  <p className="body-small muted" style={{ margin: 0 }}>
                    {evidenceError}
                  </p>
                ) : null}
              </div>
            </details>

            <details className="disclosure">
              <summary className="label-medium">
                <span>{reportsT("title")}</span>
              </summary>
              <div className="disclosure-body">
                <FieldReportsList communeCode={communeCode} plain />
              </div>
            </details>
          </div>

          <div className="dialog-actions">
            <Link
              className="btn btn--filled label-medium"
              href={{ pathname: "/commune", query: { code: communeCode } }}
              onClick={() => dialogRef.current?.close()}
            >
              {t("openFullPage")}
            </Link>
            <button
              type="button"
              className="btn btn--outline label-medium"
              onClick={() => dialogRef.current?.close()}
            >
              {t("close")}
            </button>
          </div>
        </div>
      )}
    </dialog>
  );
}
