"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { api, ApiError, type AdvisorAction, type AdvisorToolCall } from "@/lib/api";
import { SendIcon } from "./icons";

export interface OfficerAssistantProps {
  /** Commune currently selected in the console; grounds the advisor's answers. */
  communeCode?: string | null;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: AdvisorToolCall[];
  actions?: AdvisorAction[];
}

const TOKEN_KEY = "mekongpulse.officer_token";
const HISTORY_TURNS = 6;

const TOOL_NAME_KEYS = new Set([
  "get_station_telemetry",
  "resolve_commune_by_location",
  "search_commune",
  "evaluate_crop_directive",
  "synthesize_voice_bulletin",
  "get_commune_evidence",
  "draft_status_update",
  "publish_to_channel",
]);

const ACTION_STATUS_KEYS = new Set(["posted", "denied", "unavailable", "error"]);

/** Officer assistant panel: agentic advisor turns with tool-call tracing. */
export function OfficerAssistant({ communeCode }: OfficerAssistantProps) {
  const t = useTranslations("Officer");
  const locale = useLocale() === "en" ? "en" : "km";
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [open, setOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      setToken(window.localStorage.getItem(TOKEN_KEY) ?? "");
    } catch {
      // storage unavailable (private mode) — assistant stays draft-only
    }
    if (window.matchMedia("(min-width: 1040px)").matches) setOpen(true);
  }, []);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [messages, busy]);

  function updateToken(value: string) {
    setToken(value);
    try {
      if (value) {
        window.localStorage.setItem(TOKEN_KEY, value);
      } else {
        window.localStorage.removeItem(TOKEN_KEY);
      }
    } catch {
      // keep the in-memory token; persistence is best-effort
    }
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    const history = messages.slice(-HISTORY_TURNS).map(({ role, content }) => ({ role, content }));
    setMessages((current) => [...current, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const reply = await api.advisor(
        {
          message,
          history,
          locale,
          ...(communeCode ? { commune_code: communeCode } : {}),
        },
        token || undefined,
      );
      setMessages((current) => [
        ...current,
        { role: "assistant", content: reply.reply, toolCalls: reply.tool_calls, actions: reply.actions },
      ]);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 503
            ? t("errors.unavailable")
            : `${t("errors.server")} (${err.status})`
          : t("errors.network"),
      );
    } finally {
      setBusy(false);
    }
  }

  function toolLabel(name: string): string {
    return TOOL_NAME_KEYS.has(name) ? t(`tools.${name}`) : name;
  }

  function actionLabel(action: AdvisorAction): string {
    if (action.type === "telegram_post" && ACTION_STATUS_KEYS.has(action.status)) {
      return t(`actions.telegram_post.${action.status}`);
    }
    return t("actions.unknown", { status: action.status });
  }

  return (
    <section className="card officer-card" aria-label={t("title")}>
      <div className="card-title-row" style={{ marginBottom: open ? 12 : 0 }}>
        <div style={{ minWidth: 0 }}>
          <h2 className="title-medium" style={{ margin: 0 }}>
            {t("title")}
          </h2>
          <p className="body-small muted" style={{ margin: "2px 0 0" }}>
            {communeCode ? t("context", { code: communeCode }) : t("subtitle")}
          </p>
        </div>
        <button
          type="button"
          className="btn btn--compact label-medium officer-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? t("close") : t("open")}
        </button>
      </div>

      {open && (
        <div className="officer-body">
          <div className="officer-thread" ref={threadRef}>
            {messages.length === 0 && (
              <p className="body-small muted" data-empty="true">
                {t("empty")}
              </p>
            )}
            {messages.map((message, index) => (
              <div key={index} className="officer-turn" data-role={message.role}>
                <span className="officer-role label-small">
                  {message.role === "user" ? t("you") : t("assistant")}
                </span>
                <div className="officer-bubble body-small" data-role={message.role}>
                  {message.content}
                </div>
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <details className="officer-tools">
                    <summary className="label-small">
                      {t("toolsUsed", { count: message.toolCalls.length })}
                    </summary>
                    <ul>
                      {message.toolCalls.map((call, callIndex) => (
                        <li key={callIndex}>
                          <span className="tool-name label-small">{toolLabel(call.name)}</span>
                          <span className="tool-status label-small" data-status={call.status}>
                            {call.status === "error" ? t("toolStatuses.error") : t("toolStatuses.ok")}
                          </span>
                          {call.summary && <p className="body-small muted">{call.summary}</p>}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {message.actions?.map((action, actionIndex) => (
                  <p key={actionIndex} className="officer-action label-small" data-status={action.status}>
                    {actionLabel(action)}
                    {action.detail ? ` — ${action.detail}` : ""}
                  </p>
                ))}
              </div>
            ))}
            {busy && (
              <p className="body-small muted" aria-live="polite">
                {t("thinking")}
              </p>
            )}
          </div>

          {!token && (
            <p className="officer-hint label-small" role="note">
              {t("draftOnly")}
            </p>
          )}

          {error && (
            <p className="error-banner body-small" role="alert">
              {error}
            </p>
          )}

          <form
            className="officer-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send(input);
            }}
          >
            <input
              className="text-field officer-input"
              type="text"
              id="officer-message"
              name="message"
              value={input}
              placeholder={t("inputPlaceholder")}
              aria-label={t("inputAria")}
              maxLength={2000}
              onChange={(event) => setInput(event.target.value)}
            />
            <button
              type="submit"
              className="btn btn--filled officer-send"
              disabled={busy || input.trim().length === 0}
              aria-label={t("sendAria")}
            >
              <SendIcon />
            </button>
          </form>

          <div className="chip-row officer-quick">
            {(["summary", "draft", "post"] as const).map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="chip label-small"
                disabled={busy}
                onClick={() => void send(t(`quickPrompts.${prompt}`))}
              >
                {t(`quickPrompts.${prompt}`)}
              </button>
            ))}
          </div>

          <details className="officer-token">
            <summary className="label-small">
              {t("tokenLabel")} · {token ? t("tokenSet") : t("tokenUnset")}
            </summary>
            <div className="officer-token-row">
              <input
                className="text-field officer-token-input"
                type="password"
                id="officer-token"
                name="officer-token"
                value={token}
                placeholder={t("tokenPlaceholder")}
                aria-label={t("tokenLabel")}
                autoComplete="off"
                onChange={(event) => updateToken(event.target.value)}
              />
              {token && (
                <button
                  type="button"
                  className="btn btn--compact label-small officer-token-clear"
                  onClick={() => updateToken("")}
                >
                  {t("tokenClear")}
                </button>
              )}
            </div>
            <p className="body-small muted" style={{ margin: "6px 0 0" }}>
              {t("tokenHint")}
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
