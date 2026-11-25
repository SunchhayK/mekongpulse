"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { EvidencePanel } from "@/components/EvidencePanel";
import { FieldReportsList } from "@/components/FieldReportsList";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { RiskBadge } from "@/components/RiskBadge";
import { VoicePlayer } from "@/components/VoicePlayer";
import { ArrowLeftIcon, BrandMark, ShareIcon, VolumeIcon } from "@/components/icons";
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
const OFFICER_SESSION_KEY = "mekongpulse.officer_session";

function readOfficerToken(): string | null {
  try {
    const raw = window.localStorage.getItem(OFFICER_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { session?: unknown; expires_at?: unknown };
    if (typeof parsed.session !== "string" || typeof parsed.expires_at !== "string") return null;
    if (Number.isNaN(Date.parse(parsed.expires_at))) return null;
    if (Date.parse(parsed.expires_at) <= Date.now()) return null;
    return parsed.session;
  } catch {
    return null;
  }
}

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
}

export default function CommunePage() {
  return (
    <Suspense fallback={<CommuneSkeleton />}>
      <CommuneView />
    </Suspense>
  );
}

function CommuneSkeleton() {
  return (
    <div className="app">
      <div className="commune-main" aria-busy="true">
        <div className="shimmer" style={{ height: 240 }} />
        <div className="shimmer" style={{ height: 160 }} />
      </div>
    </div>
  );
}

function CommuneView() {
  const t = useTranslations("Commune");
  const headerT = useTranslations("Header");
  const evidenceT = useTranslations("Evidence");
  const tierT = useTranslations("Tier");
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
  const [officerToken, setOfficerToken] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
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
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [code, initialStage]);

  useEffect(() => {
    setOfficerToken(readOfficerToken());
    const onStorage = (event: StorageEvent) => {
      if (event.key === OFFICER_SESSION_KEY) setOfficerToken(readOfficerToken());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const requestAssessment = useCallback(
    async (nextStage: CropStage | null, force = false) => {
      if (!code) return;
      const id = ++requestId.current;
      setAssessing(true);
      if (force) setRegenerating(true);
      setAssessError(null);
      try {
        const result = await api.assess(code, nextStage ?? undefined, {
          force,
          session: force ? officerToken ?? undefined : undefined,
        });
        if (requestId.current !== id) return;
        setAssessment(result);
        setStage(nextStage);
        setStageInUrl(nextStage);
      } catch (err) {
        if (requestId.current !== id) return;
        if (force && err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          try {
            window.localStorage.removeItem(OFFICER_SESSION_KEY);
          } catch {
            // ignore storage errors
          }
          setOfficerToken(null);
          setAssessError(t("regenerateAuth"));
        } else {
          setAssessError(
            err instanceof ApiError && err.status === 409 ? t("errorNoTelemetry", { code }) : t("assessFailed"),
          );
        }
      } finally {
        if (requestId.current === id) {
          setAssessing(false);
          setRegenerating(false);
        }
      }
    },
    [code, t, officerToken],
  );

  const nameKh = assessment?.commune_name_kh ?? evidence?.commune_name_kh ?? "";
  const nameEn = assessment?.commune_name_en ?? evidence?.commune_name_en ?? code;
  const tier = assessment?.risk_tier ?? evidence?.risk_tier ?? null;
  const forecastTier = assessment?.forecast_tier ?? evidence?.forecast_tier ?? null;
  const forecastLeadDays = assessment?.forecast_lead_days ?? evidence?.forecast_lead_days ?? null;

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
      if (err instanceof DOMException && err.name === "AbortError") return;
      setShareState("failed");
      window.setTimeout(() => setShareState("idle"), 3200);
    }
  }

  return (
    <div className="app">
      <header className="top-app-bar">
        <div className="top-app-bar-inner">
          <Link className="brand" href="/">
            <BrandMark />
            <span className="brand-name">MekongPulse</span>
          </Link>
          <div className="spacer" />
          <nav className="primary-nav" aria-label={headerT("navAria")}>
            <Link className="nav-link label-medium" href="/">
              {headerT("floodMap")}
            </Link>
            <Link
              className="nav-link label-medium"
              href={{ pathname: "/assistant", query: code ? { code } : undefined }}
            >
              {headerT("assistant")}
            </Link>
          </nav>
          <LanguageSwitcher />
        </div>
      </header>

      <main className="commune-main">
        <Link className="back-link label-medium" href="/">
          <ArrowLeftIcon />
          <span>{t("backToDashboard")}</span>
        </Link>

        {!code ? (
          <section className="empty-state" aria-label={t("missingCodeTitle")}>
            <h1 className="title-large" style={{ marginTop: 0 }}>
              {t("missingCodeTitle")}
            </h1>
            <p className="body-medium muted">{t("missingCodeBody")}</p>
            <Link className="btn btn--filled label-medium" href="/">
              <ArrowLeftIcon />
              <span>{t("backToDashboard")}</span>
            </Link>
          </section>
        ) : loading ? (
          <div aria-busy="true" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="shimmer" style={{ height: 240 }} />
            <div className="shimmer" style={{ height: 160 }} />
          </div>
        ) : loadError ? (
          <section aria-label={t("errorAria")}>
            <p className="error-banner body-medium" role="alert">
              {t(
                loadError.kind === "notFound"
                  ? "errorNotFound"
                  : loadError.kind === "noTelemetry"
                    ? "errorNoTelemetry"
                    : "errorUnavailable",
                { code },
              )}
            </p>
          </section>
        ) : (
          <>
            <section className="surface surface--padded commune-hero" aria-label={t("heroAria", { name: nameKh || nameEn })}>
              <div className="commune-facts">
                {tier && (
                  <RiskBadge
                    tier={tier}
                    leadTimeHours={assessment?.lead_time_hours ?? undefined}
                    size="large"
                  />
                )}
                {forecastTier && (
                  <span className="forecast-badge label-small" data-tier={forecastTier}>
                    {forecastLeadDays != null
                      ? tierT("forecastDays", { days: forecastLeadDays, tier: tierT(forecastTier) })
                      : tierT("forecast", { tier: tierT(forecastTier) })}
                  </span>
                )}
                {assessment?.estimated && <span className="status-pill label-small">{t("estimated")}</span>}
              </div>

              <div>
                <h1 className="commune-name" lang="km">
                  {nameKh}
                </h1>
                <p className="body-medium muted" style={{ margin: "4px 0 0" }}>
                  {nameEn}
                  {assessment
                    ? `, ${t("updated", { time: formatDateTime(assessment.generated_at, locale) })}`
                    : ""}
                </p>
              </div>

              {tier && (
                <p className="body-medium" style={{ margin: 0, maxWidth: "60ch" }}>
                  {t(`statusSummary.${tier}`)}
                </p>
              )}

              <div className="commune-actions">
                <button
                  type="button"
                  className="btn btn--filled label-large commune-listen"
                  onClick={() => void requestAssessment(stage)}
                  disabled={assessing}
                >
                  <VolumeIcon />
                  <span>{assessing ? t("listenLoading") : t("listen")}</span>
                </button>
                <button type="button" className="btn btn--outline label-medium" onClick={() => void share()}>
                  <ShareIcon />
                  <span>{t("share")}</span>
                </button>
              </div>

              {shareState !== "idle" && (
                <p className="body-small muted" role="status" style={{ margin: 0 }}>
                  {shareState === "copied" ? t("shareCopied") : t("shareFailed")}
                </p>
              )}

              {assessError && (
                <p className="error-banner body-small" role="alert">
                  {assessError}
                </p>
              )}

              {assessment &&
                (assessment.audio ? (
                  <div className="voice-card">
                    <VoicePlayer
                      audioSrc={assessment.audio.url}
                      durationSeconds={assessment.audio.duration_seconds ?? undefined}
                      transcriptKhmer={assessment.khmer_bulletin}
                      transcriptEnglish={assessment.english_bulletin}
                    />
                  </div>
                ) : (
                  <div className="commune-bulletin">
                    <p className="body-medium transcript" lang="km">
                      {assessment.khmer_bulletin}
                    </p>
                    {assessment.english_bulletin && (
                      <p className="body-small muted" lang="en">
                        {assessment.english_bulletin}
                      </p>
                    )}
                    <p className="body-small muted" role="note">
                      {t("voiceUnavailable")}
                    </p>
                  </div>
                ))}

              {assessment && officerToken && (
                <div className="commune-regenerate">
                  <button
                    type="button"
                    className="btn btn--outline btn--compact label-small"
                    onClick={() => void requestAssessment(stage, true)}
                    disabled={assessing}
                  >
                    {regenerating ? t("regenerating") : t("regenerate")}
                  </button>
                  <span className="body-small muted">{t("regenerateHint")}</span>
                </div>
              )}

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
              <section className="surface surface--padded" aria-label={t("directivesAria")}>
                <div className="section-header">
                  <h2 className="title-large section-title">{t("directivesTitle")}</h2>
                  <span className="body-small muted">
                    {t("stageSelected", {
                      stage: stage ? t(`stage.${stage}`) : t("stageDefault"),
                    })}
                  </span>
                </div>
                <ol className="directive-list">
                  {assessment.directives.map((directive) => (
                    <li key={directive.action_code}>
                      <div className="directive-content">
                        <div className="title-small" lang="km">
                          {directive.title_kh}
                        </div>
                        <div className="body-medium" lang="km">
                          {directive.instruction_kh}
                        </div>
                        <div className="body-small muted" lang="en">
                          {directive.title_en}: {directive.instruction_en}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <FieldReportsList communeCode={code} />

            {evidence && (
              <details className="disclosure">
                <summary className="label-large">
                  <span>{evidenceT("title")}</span>
                  <span className="disclosure-summary-meta label-small">
                    {evidenceT(`confidence.levels.${evidence.confidence}`)}
                  </span>
                </summary>
                <div className="disclosure-body">
                  <EvidencePanel evidence={evidence} />
                </div>
              </details>
            )}
          </>
        )}
      </main>
    </div>
  );
}
