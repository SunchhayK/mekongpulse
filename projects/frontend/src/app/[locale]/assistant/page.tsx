"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { AssistantChat, type ChatMessage } from "@/components/AssistantChat";
import { CommuneSearch } from "@/components/CommuneSearch";
import { ArrowLeftIcon, CloseIcon, MapPinIcon } from "@/components/icons";
import { Link } from "@/i18n/navigation";
import {
  api,
  ApiError,
  type AdvisorAction,
  type AdvisorToolCall,
  type OfficerSession,
} from "@/lib/api";
import { intlLocale } from "@/lib/design";

const SESSION_KEY = "mekongpulse.officer_session";
/** Pre-sign-in builds kept the raw officer token here; the UI no longer uses it. */
const LEGACY_TOKEN_KEY = "mekongpulse.officer_token";
const CONVERSATION_KEY = "mekongpulse.assistant_conversation.v1";
const FOCUS_KEY = "mekongpulse.assistant_focus.v1";
const MAX_STORED_MESSAGES = 60;

/** Stored session, or null when absent, malformed, or already expired. */
function readStoredSession(): OfficerSession | null {
  try {
    window.localStorage.removeItem(LEGACY_TOKEN_KEY);
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<OfficerSession>;
    if (typeof parsed.session !== "string" || parsed.session.length === 0) return null;
    if (typeof parsed.expires_at !== "string" || Number.isNaN(Date.parse(parsed.expires_at))) return null;
    if (Date.parse(parsed.expires_at) <= Date.now()) {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return { session: parsed.session, expires_at: parsed.expires_at };
  } catch {
    return null;
  }
}

function writeStoredSession(value: OfficerSession | null) {
  try {
    if (value) {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } else {
      window.localStorage.removeItem(SESSION_KEY);
    }
  } catch {
    // storage unavailable (private mode) — the in-memory session still works
  }
}

/** Stored threads come from the network: accept only the shape we render. */
function readToolCall(value: unknown): AdvisorToolCall | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.name !== "string" || typeof raw.status !== "string" || typeof raw.summary !== "string") {
    return null;
  }
  return { name: raw.name, status: raw.status, summary: raw.summary };
}

function readAction(value: unknown): AdvisorAction | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.type !== "string" || typeof raw.status !== "string") return null;
  return { type: raw.type, status: raw.status, detail: typeof raw.detail === "string" ? raw.detail : null };
}

function readMessage(value: unknown): ChatMessage | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const role = raw.role;
  if ((role !== "user" && role !== "assistant") || typeof raw.content !== "string") return null;

  const message: ChatMessage = { role, content: raw.content };
  if (Array.isArray(raw.toolCalls)) {
    const toolCalls = raw.toolCalls.map(readToolCall).filter((call): call is AdvisorToolCall => call !== null);
    if (toolCalls.length > 0) message.toolCalls = toolCalls;
  }
  if (Array.isArray(raw.actions)) {
    const actions = raw.actions.map(readAction).filter((action): action is AdvisorAction => action !== null);
    if (actions.length > 0) message.actions = actions;
  }
  return message;
}

function readStoredConversation(): ChatMessage[] {
  try {
    const raw = window.localStorage.getItem(CONVERSATION_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(readMessage)
      .filter((message): message is ChatMessage => message !== null)
      .slice(-MAX_STORED_MESSAGES);
  } catch {
    return [];
  }
}

function writeStoredConversation(messages: ChatMessage[]) {
  try {
    if (messages.length === 0) {
      window.localStorage.removeItem(CONVERSATION_KEY);
    } else {
      window.localStorage.setItem(CONVERSATION_KEY, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)));
    }
  } catch {
    // storage unavailable (private mode) — the thread still works in memory
  }
}

function readStoredFocus(): string {
  try {
    return window.localStorage.getItem(FOCUS_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
}

function writeStoredFocus(code: string) {
  try {
    if (code) {
      window.localStorage.setItem(FOCUS_KEY, code);
    } else {
      window.localStorage.removeItem(FOCUS_KEY);
    }
  } catch {
    // storage unavailable (private mode)
  }
}

function formatExpiry(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(intlLocale(locale), {
    timeZone: "Asia/Phnom_Penh",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * Officer assistant page (static export): full-page chat with officer sign-in
 * and server-side Khmer voice input.
 *
 * Client-only concerns (stored session, recording, useSearchParams) sit inside
 * the Suspense boundary below.
 */
export default function AssistantPage() {
  return (
    <Suspense fallback={<AssistantSkeleton />}>
      <AssistantView />
    </Suspense>
  );
}

function AssistantSkeleton() {
  return (
    <div className="app assistant-app">
      <main className="assistant-main" aria-busy="true">
        <div className="shimmer" style={{ height: 220 }} />
      </main>
    </div>
  );
}

function AssistantView() {
  const t = useTranslations("Officer");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<OfficerSession | null>(null);
  const [passcode, setPasscode] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);
  const initialCode = searchParams.get("code")?.trim() ?? "";
  const [communeCode, setCommuneCode] = useState(initialCode);
  const [pickingCommune, setPickingCommune] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationReady, setConversationReady] = useState(false);
  const [focusReady, setFocusReady] = useState(false);

  useEffect(() => {
    setSession(readStoredSession());
  }, []);

  // Hydrate the thread after mount so the static export prerenders empty.
  useEffect(() => {
    setMessages(readStoredConversation());
    setConversationReady(true);
  }, []);

  useEffect(() => {
    if (conversationReady) writeStoredConversation(messages);
  }, [messages, conversationReady]);

  // ?code= wins on load; otherwise fall back to the last focused commune.
  useEffect(() => {
    if (!initialCode) {
      const stored = readStoredFocus();
      if (stored) setCommuneCode(stored);
    }
    setFocusReady(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (focusReady) writeStoredFocus(communeCode);
  }, [communeCode, focusReady]);

  // Expired sessions count as signed out; a 401 mid-conversation signs out too.
  const activeSession = useMemo(
    () => (session && Date.parse(session.expires_at) > Date.now() ? session : null),
    [session],
  );

  const clearSession = useCallback(() => {
    setSession(null);
    setSignInError(null);
    writeStoredSession(null);
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    writeStoredConversation([]);
  }, []);

  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    const code = passcode.trim();
    if (!code || signingIn) return;
    setSigningIn(true);
    setSignInError(null);
    try {
      const result = await api.officerLogin(code);
      setSession(result);
      setPasscode("");
      writeStoredSession(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setSignInError(
          err.status === 401
            ? t("signIn.errors.invalid")
            : err.status === 429
              ? t("signIn.errors.tooMany")
              : err.status === 503
                ? t("signIn.errors.unavailable")
                : `${t("errors.server")} (${err.status})`,
        );
      } else {
        setSignInError(t("errors.network"));
      }
    } finally {
      setSigningIn(false);
    }
  }

  return (
    <div className="app assistant-app">
      <header className="top-app-bar assistant-bar">
        <Link className="assistant-back label-medium" href="/">
          <ArrowLeftIcon />
          <span className="assistant-back-text">{t("back")}</span>
        </Link>
        <span className="assistant-head">
          <h1 className="title-medium assistant-title">{t("title")}</h1>
          <span className="body-small subtitle">
            {communeCode ? t("context", { code: communeCode }) : t("subtitle")}
          </span>
        </span>
        <div className="spacer" />
        <button
          type="button"
          className="btn assistant-signout assistant-clear label-small"
          aria-label={t("clearConversationAria")}
          title={t("clearConversationAria")}
          onClick={clearConversation}
        >
          {t("clearConversation")}
        </button>
        {activeSession && (
          <>
            <span className="session-chip label-small">
              {t("signedIn", { time: formatExpiry(activeSession.expires_at, locale) })}
            </span>
            <button type="button" className="btn assistant-signout label-small" onClick={clearSession}>
              {t("signOut")}
            </button>
          </>
        )}
        <AssistantLangSwitch />
      </header>

      <main className="assistant-main">
        {!activeSession && (
          <section className="card assistant-signin" aria-label={t("signIn.title")}>
            <h2 className="title-small" style={{ margin: 0 }}>
              {t("signIn.title")}
            </h2>
            <form className="assistant-signin-row" onSubmit={(event) => void signIn(event)}>
              <input
                className="text-field assistant-signin-input"
                type="password"
                id="officer-passcode"
                name="passcode"
                value={passcode}
                placeholder={t("signIn.placeholder")}
                aria-label={t("signIn.passcode")}
                aria-invalid={signInError != null}
                autoComplete="current-password"
                onChange={(event) => setPasscode(event.target.value)}
              />
              <button
                type="submit"
                className="btn btn--filled label-medium"
                disabled={signingIn || passcode.trim().length === 0}
              >
                {signingIn ? t("signIn.working") : t("signIn.submit")}
              </button>
            </form>
            {signInError ? (
              <p className="error-banner body-small" role="alert">
                {signInError}
              </p>
            ) : (
              <p className="body-small muted" style={{ margin: 0 }}>
                {t("draftOnly")}
              </p>
            )}
          </section>
        )}

        <div className="assistant-focus-row">
          {communeCode ? (
            <span className="assistant-focus-chip label-small">
              <MapPinIcon />
              <span>{t("context", { code: communeCode })}</span>
              <button
                type="button"
                className="assistant-focus-clear"
                aria-label={t("focusClear")}
                title={t("focusClear")}
                onClick={() => setCommuneCode("")}
              >
                <CloseIcon />
              </button>
            </span>
          ) : (
            !pickingCommune && (
              <button
                type="button"
                className="chip label-small"
                aria-expanded={pickingCommune}
                onClick={() => setPickingCommune(true)}
              >
                <MapPinIcon /> {t("focusAdd")}
              </button>
            )
          )}
        </div>

        {pickingCommune && !communeCode && (
          <section className="assistant-focus-search" aria-label={t("focusAdd")}>
            <CommuneSearch
              onPick={(code) => {
                setCommuneCode(code);
                setPickingCommune(false);
              }}
            />
            <button
              type="button"
              className="btn assistant-signout label-small"
              onClick={() => setPickingCommune(false)}
            >
              {t("focusCancel")}
            </button>
          </section>
        )}

        <AssistantChat
          communeCode={communeCode || null}
          session={activeSession?.session ?? null}
          onSessionInvalid={clearSession}
          messages={messages}
          setMessages={setMessages}
        />
      </main>
    </div>
  );
}

/**
 * Locale pill for this page: next-intl's LanguageSwitcher drops the ?code=
 * query, which would silently clear the focused commune on a locale switch.
 */
function AssistantLangSwitch() {
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
            href={{ pathname: "/assistant", query: code ? { code } : undefined }}
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
