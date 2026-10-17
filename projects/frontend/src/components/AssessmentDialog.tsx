"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Assessment, type CropStage } from "@/lib/api";
import { CROP_STAGES, formatDateTime } from "@/lib/design";
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
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [cropStage, setCropStage] = useState<CropStage>("RIPENING");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      .assess(communeCode, cropStage)
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
            ? `Commune ${communeCode} has no station telemetry to score yet. Pick another commune or retry after the next sync.`
            : err instanceof ApiError && err.status === 404
              ? `Commune ${communeCode} was not found in the 2025 gazetteer.`
              : `Assessment unavailable right now${err instanceof ApiError ? ` (${err.status})` : ""}. Retry in a few minutes.`,
        );
      })
      .finally(() => {
        if (requestId.current === id) setLoading(false);
      });
  }, [communeCode, cropStage, onAssessment]);

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
        aria-label={`Flood assessment for commune ${communeCode}`}
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
                  {assessment.commune_name_en} · {assessment.commune_code} · updated{" "}
                  {formatDateTime(assessment.generated_at)}
                </p>
              </>
            ) : (
              <>
                <h2 className="title-large" style={{ margin: 0 }}>
                  Commune {communeCode}
                </h2>
                <p className="body-medium muted" style={{ margin: "4px 0 0" }}>
                  Evaluating flood risk and recording the Khmer voice bulletin — up to a minute…
                </p>
              </>
            )}
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close assessment">
            <CloseIcon />
          </button>
        </div>

        <div className="crop-stage-row" role="group" aria-label="Rice growth stage">
          {CROP_STAGES.map((stage) => (
            <button
              key={stage.value}
              type="button"
              className="chip label-medium"
              aria-pressed={cropStage === stage.value}
              onClick={() => setCropStage(stage.value)}
            >
              {stage.labelKh} · {stage.labelEn}
            </button>
          ))}
        </div>

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
                  ⚠︎ ទិន្នន័យប៉ាន់ស្មាន / estimated telemetry — escalated conservatively
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

            <VoicePlayer
              audioSrc={assessment.audio?.url}
              durationSeconds={assessment.audio?.duration_seconds ?? undefined}
              transcriptKhmer={assessment.khmer_bulletin}
              transcriptEnglish={assessment.english_bulletin}
            />
          </div>
        )}
      </div>
    </div>
  );
}
