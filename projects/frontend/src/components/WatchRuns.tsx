"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  api,
  ApiError,
  type AgentRun,
  type AgentRunStatus,
  type OfficerSession,
} from "@/lib/api";
import { intlLocale } from "@/lib/design";

const POLL_MS = 30_000;

interface WatchRunsProps {
  session: OfficerSession | null;
  communeCode: string | null;
  onSessionInvalid: () => void;
  onPendingChange?: (count: number) => void;
}

const STATUS_CLASS: Record<AgentRunStatus, string> = {
  pending_approval: "watch-status--pending",
  published: "watch-status--published",
  rejected: "watch-status--rejected",
  failed: "watch-status--failed",
};

export function WatchRuns({
  session,
  communeCode,
  onSessionInvalid,
  onPendingChange,
}: WatchRunsProps) {
  const t = useTranslations("Watch");
  const locale = useLocale();
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; khmer: string; english: string } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const pendingCount = runs.filter((run) => run.status === "pending_approval").length;
  const orderedRuns = [...runs].sort(
    (a, b) =>
      Number(b.status === "pending_approval") - Number(a.status === "pending_approval"),
  );

  useEffect(() => {
    onPendingChange?.(pendingCount);
  }, [pendingCount, onPendingChange]);

  const formatTime = useCallback(
    (iso: string | null) => {
      if (!iso) return "—";
      const date = new Date(iso);
      if (Number.isNaN(date.getTime())) return "—";
      return new Intl.DateTimeFormat(intlLocale(locale), {
        timeZone: "Asia/Phnom_Penh",
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
    },
    [locale],
  );

  const fail = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) {
        onSessionInvalid();
        return;
      }
      const detail = err instanceof ApiError ? err.message : null;
      setError(detail ? `${t("actionFailed")} ${detail}` : t("actionFailed"));
    },
    [onSessionInvalid, t],
  );

  useEffect(() => {
    if (!session) {
      setRuns([]);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const payload = await api.watchRuns(session.session);
        if (!cancelled) setRuns(payload.runs);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          onSessionInvalid();
        } else {
          setError(t("loadFailed"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // `t` is stable for the locale; excluding it avoids re-creating the poller.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, onSessionInvalid]);

  async function runWatch() {
    if (!session || creating) return;
    setCreating(true);
    setError(null);
    try {
      const { run } = await api.watchRun(session.session, communeCode);
      setRuns((current) => [run, ...current].slice(0, 10));
    } catch (err) {
      fail(err);
    } finally {
      setCreating(false);
    }
  }

  async function approve(run: AgentRun) {
    if (!session || busy) return;
    const edits = editing?.id === run.id ? editing : null;
    setBusy(run.id);
    setError(null);
    try {
      const { run: updated } = await api.approveRun(
        session.session,
        run.id,
        edits?.khmer,
        edits?.english,
      );
      setRuns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditing(null);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  }

  async function reject(run: AgentRun) {
    if (!session || busy) return;
    setBusy(run.id);
    setError(null);
    try {
      const { run: updated } = await api.rejectRun(session.session, run.id);
      setRuns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (editing?.id === run.id) setEditing(null);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card watch-card" aria-label={t("title")}>
      <div className="watch-action">
        <div className="watch-action-copy">
          <p className="watch-action-label label-small">{t("startTitle")}</p>
          <h2 className="title-small" style={{ margin: "2px 0 4px" }}>
            {communeCode ? t("runOn", { code: communeCode }) : t("runHighest")}
          </h2>
          <p className="body-small muted" style={{ margin: 0 }}>
            {t("intro")}
          </p>
        </div>
        <button
          type="button"
          className="btn btn--filled label-medium watch-run-btn"
          onClick={() => void runWatch()}
          disabled={!session || creating}
        >
          {creating ? t("running") : t("runWatch")}
        </button>
      </div>

      {error && (
        <p className="error-banner body-small" role="alert">
          {error}
        </p>
      )}
      {!session && <p className="body-small muted">{t("signIn")}</p>}
      {session && orderedRuns.length === 0 && !loading && (
        <p className="body-small muted watch-empty">{t("empty")}</p>
      )}

      <div className="watch-inbox-head">
        <h3 className="title-small" style={{ margin: 0 }}>
          {t("recent")}
        </h3>
        {pendingCount > 0 && (
          <span className="watch-count label-small">
            {t("pendingCount", { count: pendingCount })}
          </span>
        )}
      </div>

      <div className="watch-list" aria-live="polite">
        {orderedRuns.map((run) => {
          const name =
            locale === "km"
              ? run.commune_name_kh || run.commune_name_en || run.commune_code
              : run.commune_name_en || run.commune_name_kh || run.commune_code;
          const isEditing = editing?.id === run.id;
          const pending = run.status === "pending_approval";
          return (
            <article key={run.id} className={`watch-run watch-run--${run.status}`}>
              <div className="watch-run-head">
                <div>
                  <span className="watch-run-title">{name}</span>{" "}
                  <span className="body-small muted">{run.commune_code}</span>
                </div>
                <span className={`status-pill watch-status ${STATUS_CLASS[run.status]}`}>
                  {t(run.status)}
                </span>
              </div>
              <p className="body-small muted watch-meta">
                {run.trigger === "transition" ? t("triggerTransition") : t("triggerManual")}
                {" · "}
                {t("created", { time: formatTime(run.created_at) })}
                {" · "}
                {t("tierChange", {
                  previous: run.previous_tier || t("noPrevious"),
                  current: run.current_tier,
                })}
              </p>

              {run.rationale && (
                <div className="watch-section">
                  <span className="label-small muted">{t("rationale")}</span>
                  <div className="watch-rationale assistant-md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {run.rationale}
                    </ReactMarkdown>
                  </div>
                </div>
              )}

              {run.tool_calls.length > 0 ? (
                <details className="watch-tools">
                  <summary className="body-small muted">
                    {t("tools", { count: run.tool_calls.length })}
                  </summary>
                  <ul className="body-small">
                    {run.tool_calls.map((call, index) => (
                      <li key={`${call.name}-${index}`}>
                        <strong>{call.name}</strong> — {call.summary || call.status}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : (
                <p className="body-small muted">{t("noTools")}</p>
              )}

              {run.error && (
                <p className="body-small watch-error">
                  {t("errorLabel")}: {run.error}
                </p>
              )}

              {isEditing ? (
                <div className="watch-edit">
                  <label className="label-small" htmlFor={`watch-kh-${run.id}`}>
                    {t("draftKhmer")}
                  </label>
                  <textarea
                    id={`watch-kh-${run.id}`}
                    className="text-field"
                    value={editing.khmer}
                    onChange={(event) =>
                      setEditing({ ...editing, khmer: event.target.value })
                    }
                    rows={5}
                    lang="km"
                  />
                  <label className="label-small" htmlFor={`watch-en-${run.id}`}>
                    {t("draftEnglish")}
                  </label>
                  <textarea
                    id={`watch-en-${run.id}`}
                    className="text-field"
                    value={editing.english}
                    onChange={(event) =>
                      setEditing({ ...editing, english: event.target.value })
                    }
                    rows={4}
                    lang="en"
                  />
                  <div className="watch-actions">
                    <button
                      type="button"
                      className="btn btn--filled label-small"
                      onClick={() => void approve(run)}
                      disabled={busy !== null}
                    >
                      {busy === run.id ? t("approving") : t("saveApprove")}
                    </button>
                    <button
                      type="button"
                      className="btn btn--outline label-small"
                      onClick={() => setEditing(null)}
                      disabled={busy !== null}
                    >
                      {t("cancel")}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <details
                    className="watch-draft"
                    open={run.status === "pending_approval"}
                  >
                    <summary className="body-small muted">{t("draft")}</summary>
                    <p className="body-small watch-draft-text" lang="km">
                      {run.draft_khmer}
                    </p>
                    {run.draft_english && (
                      <p className="body-small muted watch-draft-text" lang="en">
                        {run.draft_english}
                      </p>
                    )}
                  </details>

                  {pending ? (
                    <div className="watch-actions">
                      <button
                        type="button"
                        className="btn btn--filled label-small"
                        onClick={() => void approve(run)}
                        disabled={busy !== null}
                      >
                        {busy === run.id ? t("approving") : t("approve")}
                      </button>
                      <button
                        type="button"
                        className="btn btn--outline label-small"
                        onClick={() =>
                          setEditing({
                            id: run.id,
                            khmer: run.draft_khmer,
                            english: run.draft_english || "",
                          })
                        }
                        disabled={busy !== null}
                      >
                        {t("edit")}
                      </button>
                      <button
                        type="button"
                        className="btn btn--outline label-small"
                        onClick={() => void reject(run)}
                        disabled={busy !== null}
                      >
                        {busy === run.id ? t("rejecting") : t("reject")}
                      </button>
                    </div>
                  ) : (
                    <p className="body-small muted watch-meta">
                      {run.status === "published" && run.published_at
                        ? t("publishedAt", { time: formatTime(run.published_at) })
                        : null}
                      {run.status === "published" && run.published_message_id
                        ? ` · ${t("messageId", { id: run.published_message_id })}`
                        : null}
                      {run.status === "rejected" && run.rejected_at
                        ? t("rejectedAt", { time: formatTime(run.rejected_at) })
                        : null}
                    </p>
                  )}
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
