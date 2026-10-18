"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FieldReportsList } from "@/components/FieldReportsList";
import { RiskBadge } from "@/components/RiskBadge";
import { VoicePlayer } from "@/components/VoicePlayer";
import { ArrowLeftIcon, BrandMark, ShareIcon, VolumeIcon, WaveIcon } from "@/components/icons";
import { Link } from "@/i18n/navigation";
import {
  api,
  ApiError,
  type Assessment,
  type CropStage,
  type EvidencePayload,
} from "@/lib/api";
import { formatDateTime } from "@/lib/design";

const CROP_STAGES: CropStage[] = ["TILLERING", "VEGETATIVE", "FLOWERING", "RIPENING"];

/** Keep the selected stage in the URL so shared links reuse the same briefing/audio. */
function setStageInUrl(next: CropStage | null) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  if (next) params.set("stage", next);
  else params.delete("stage");
  const query = params.toString();
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${query ? `?${query}` : ""}`,
  );
}

type LoadError = "notFound" | "noTelemetry" | "unavailable";

interface ErrorState {
  kind: LoadError;
  detail: string | null;
}

/**
 * Public commune bulletin page (static export): voice-first, built for relay
 * people — commune chiefs and extension workers — who receive a link like
 * /{locale}/commune/?code=080404 and forward it to farmers.
 *
 * Client-only data (evidence, assessment + TTS, field reports, share):
 * useSearchParams therefore sits inside the Suspense boundary below.
 */
export default function CommunePage() {
  return (
    <Suspense fallback={<CommuneSkeleton />}>
      <CommuneView />
    </Suspense>
  );
}

function CommuneSkeleton() {
  return (
    <div className="app commune-app">
      <div className="commune-main" aria-busy="true">
        <div className="shimmer" style={{ height: 240 }} />
        <div className="shimmer" style={{ height: 180 }} />
      </div>
    </div>
  );
}

function CommuneView() {
  const t = useTranslations("Commune");
  const evidenceT = useTranslations("Evidence");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const code = searchParams.get("code")?.trim() ?? "";
  const stageParam = searchParams.get("stage");
  const initialStage = CROP_STAGES.includes(stageParam as CropStage)
    ? (stageParam as CropStage)
    : null;

  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<ErrorState | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [assessing, setAssessing] = useState(false);
  const [assessError, setAssessError] = useState<string | null>(null);
  const [stage, setStage] = useState<CropStage | null>(initialStage);
  const [shareState, setShareState] = useState<"idle" | "copied" | "failed">("idle");
  const requestId = useRef(0);

  useEffect(() => {
    if (!code) return;
    let cancelled = false;
    requestId.current += 1;
    setLoading(true);
    setLoadError(null);
    setEvidence(null);
    setAssessment(null);
    setAssessError(null);
    setStage(initialStage);
    setShareState("idle");
    api
      .evidence(code)
      .then((payload) => {
        if (!cancelled) setEvidence(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError({
          kind:
            err instanceof ApiError && err.status === 404
              ? "notFound"
              : err instanceof ApiError && err.status === 409
                ? "noTelemetry"
                : "unavailable",
          detail: err instanceof ApiError ? err.message : null,
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [code, initialStage]);

  /** Fetch the bulletin (with Khmer TTS) for the chosen rice stage. */
  const requestAssessment = useCallback(
    async (nextStage: CropStage | null) => {
      if (!code) return;
      const id = ++requestId.current;
      setAssessing(true);
      setAssessError(null);
      try {
        const result = await api.assess(code, nextStage ?? undefined);
        if (requestId.current !== id) return;
        setAssessment(result);
        setStage(nextStage);
        setStageInUrl(nextStage);
      } catch (err) {
        if (requestId.current !== id) return;
        setAssessError(
          err instanceof ApiError && err.status === 409 ? t("errorNoTelemetry") : t("assessFailed"),
        );
      } finally {
        if (requestId.current === id) setAssessing(false);
      }
    },
    [code, t],
  );

  const nameKh = assessment?.commune_name_kh ?? evidence?.commune_name_kh ?? "";
  const nameEn = assessment?.commune_name_en ?? evidence?.commune_name_en ?? code;
  const tier = assessment?.risk_tier ?? evidence?.risk_tier ?? null;

  async function share() {
    const url = window.location.href;
    const shareText = t("shareText", { name: nameKh || nameEn, url });
    try {
      if (typeof navigator.share === "function") {
        await navigator.share({ title: t("shareTitle", { name: nameKh || nameEn }), text: shareText, url });
        return;
      }
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(url);
      setShareState("copied");
      window.setTimeout(() => setShareState("idle"), 3200);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return; // user dismissed the sheet
      setShareState("failed");
      window.setTimeout(() => setShareState("idle"), 3200);
    }
  }

  return (
    <div className="app commune-app">
      <header className="top-app-bar">
        <Link className="brand" href="/">
          <BrandMark />
          <span className="brand-text">
            <span className="brand-name">MekongPulse</span>
            <span className="body-small subtitle">{t("brandSubtitle")}</span>
          </span>
        </Link>
        <div className="spacer" />
        <CommuneLangSwitch />
      </header>

      <main className="commune-main">
        {!code ? (
          <section className="empty-state" aria-label={t("missingCodeTitle")}>
            <h1 className="title-large" style={{ marginTop: 0 }}>
              {t("missingCodeTitle")}
            </h1>
            <p className="body-medium muted">{t("missingCodeBody")}</p>
            <Link className="btn btn--filled label-medium" href="/">
              <ArrowLeftIcon /> {t("backToDashboard")}
            </Link>
          </section>
        ) : loading ? (
          <div aria-busy="true" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="shimmer" style={{ height: 240 }} />
            <div className="shimmer" style={{ height: 180 }} />
          </div>
        ) : loadError ? (
          <section aria-label={t("errorAria")}>
            <p className="error-banner body-medium" role="alert">
              <span>
                <strong>
                  {t(
                    loadError.kind === "notFound"
                      ? "errorNotFound"
                      : loadError.kind === "noTelemetry"
                        ? "errorNoTelemetry"
                        : "errorUnavailable",
                    { code },
                  )}
                </strong>
                {loadError.detail && (
                  <>
                    <br />
                    <span className="body-small">{loadError.detail}</span>
                  </>
                )}
              </span>
            </p>
            <p style={{ marginTop: 16 }}>
              <Link className="hero-link label-medium" href="/">
                <ArrowLeftIcon /> {t("backToDashboard")}
              </Link>
            </p>
          </section>
        ) : (
          <>
            <section className="card commune-hero" aria-label={t("heroAria", { name: nameKh })}>
              <p className="eyebrow">{t("eyebrow")}</p>
              <h1 className="commune-name" lang="km">
                {nameKh}
              </h1>
              <p className="body-medium muted" style={{ margin: 0 }}>
                {nameEn} · <span className="mono">{code}</span>
                {assessment && (
                  <>
                    {" · "}
                    {t("updated", { time: formatDateTime(assessment.generated_at, locale) })}
                  </>
                )}
              </p>

              <div className="commune-facts">
                {tier && <RiskBadge tier={tier} leadTimeHours={assessment?.lead_time_hours ?? undefined} size="large" />}
                {assessment?.estimated && <span className="status-pill label-medium">{t("estimated")}</span>}
              </div>

              <div className="commune-actions">
                <button
                  type="button"
                  className="btn btn--filled label-large commune-listen"
                  onClick={() => void requestAssessment(stage)}
                  disabled={assessing}
                >
                  <VolumeIcon /> {assessing ? t("listenLoading") : t("listen")}
                </button>
                <button type="button" className="btn btn--outline label-medium" onClick={() => void share()}>
                  <ShareIcon /> {t("share")}
                </button>
              </div>
              {shareState !== "idle" && (
                <p className="body-small muted" role="status" style={{ margin: 0 }}>
                  {shareState === "copied" ? t("shareCopied") : t("shareFailed")}
                </p>
              )}

              {assessError && (
                <p className="error-banner body-medium" role="alert">
                  {assessError}
                </p>
              )}

              {assessment &&
                (assessment.audio ? (
                  <div className="voice-card voice-card--inset">
                    <VoicePlayer
                      audioSrc={assessment.audio.url}
                      durationSeconds={assessment.audio.duration_seconds ?? undefined}
                      transcriptKhmer={assessment.khmer_bulletin}
                      transcriptEnglish={assessment.english_bulletin}
                    />
                  </div>
                ) : (
                  <div className="commune-bulletin">
                    <p className="body-medium transcript" lang="km" style={{ margin: 0 }}>
                      {assessment.khmer_bulletin}
                    </p>
                    {assessment.english_bulletin && (
                      <p className="body-small muted" lang="en">
                        {assessment.english_bulletin}
                      </p>
                    )}
                    <p className="body-small commune-voice-note" role="note">
                      {t("voiceUnavailable")}
                    </p>
                  </div>
                ))}

              <div className="commune-stage" role="group" aria-label={t("stageAria")}>
                <span className="label-small muted">{t("stageLabel")}</span>
                <div className="chip-row">
                  {CROP_STAGES.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className="chip label-medium"
                      aria-pressed={stage === option}
                      disabled={assessing}
                      onClick={() => void requestAssessment(option)}
                    >
                      {t(`stage.${option}`)}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {assessment && assessment.directives.length > 0 && (
              <section className="card" aria-label={t("directivesAria")}>
                <div className="card-title-row">
                  <h2 className="title-medium" style={{ margin: 0 }}>
                    {t("directivesTitle")}
                  </h2>
                  <span className="body-small muted">
                    {t("stageSelected", {
                      stage: stage ? t(`stage.${stage}`) : t("stageDefault"),
                    })}
                  </span>
                </div>
                <ul className="directive-list" style={{ marginTop: 0 }}>
                  {assessment.directives.map((directive) => (
                    <li key={directive.action_code}>
                      <span className="urgency label-small">{directive.family}</span>
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
              </section>
            )}

            {evidence && (
              <section className="card" aria-label={evidenceT("title")}>
                <div className="card-title-row">
                  <h2 className="title-medium" style={{ margin: 0 }}>
                    {evidenceT("title")}
                  </h2>
                  <span className="body-small muted">{t("evidenceHint")}</span>
                </div>
                <EvidencePanel evidence={evidence} />
              </section>
            )}

            <FieldReportsList communeCode={code} />

            <p style={{ margin: 0 }}>
              <Link className="hero-link label-medium" href="/">
                <WaveIcon /> {t("backToDashboard")}
              </Link>
            </p>
          </>
        )}
      </main>
    </div>
  );
}

/**
 * Locale pill for this page: next-intl's LanguageSwitcher (untouched) drops
 * the ?code= query, which would strand relay links on the "missing code"
 * screen, so the commune page keeps the query while switching locales.
 */
function CommuneLangSwitch() {
  const locale = useLocale();
  const t = useTranslations("LanguageSwitcher");
  const searchParams = useSearchParams();
  const code = searchParams.get("code") ?? undefined;

  return (
    <span className="lang-switch label-small" role="group" aria-label={t("aria")}>
      {(["km", "en"] as const).map((option, index) => (
        <span key={option} className="lang-switch-option">
          {index > 0 && (
            <span className="lang-sep" aria-hidden="true">
              |
            </span>
          )}
          <Link
            href={{ pathname: "/commune", query: code ? { code } : undefined }}
            locale={option}
            aria-current={option === locale ? "true" : undefined}
            lang={option}
          >
            {option === "km" ? t("km") : t("en")}
          </Link>
        </span>
      ))}
    </span>
  );
}
