"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { AssistantChat, type ChatMessage } from "@/components/AssistantChat";
import { CommuneSearch } from "@/components/CommuneSearch";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { WatchRuns } from "@/components/WatchRuns";
import { BrandMark, CloseIcon, MapPinIcon, ShieldIcon } from "@/components/icons";
import { Link } from "@/i18n/navigation";
import {
  api,
  ApiError,
  isFirebaseAuthConfigured,
  type AdvisorAction,
  type AdvisorToolCall,
  type OfficerSession,
} from "@/lib/api";
import { intlLocale } from "@/lib/design";

const SESSION_KEY = "mekongpulse.officer_session";
const LEGACY_TOKEN_KEY = "mekongpulse.officer_token";
const CONVERSATION_KEY = "mekongpulse.assistant_conversation.v1";
const FOCUS_KEY = "mekongpulse.assistant_focus.v1";
const MAX_STORED_MESSAGES = 60;

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
    return {
      session: parsed.session,
      expires_at: parsed.expires_at,
      email: typeof parsed.email === "string" ? parsed.email : null,
      auth_mode: parsed.auth_mode === "firebase" ? "firebase" : "passcode",
    };
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
    // ignore storage errors
  }
}

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
    // ignore storage errors
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
    // ignore storage errors
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
  const headerT = useTranslations("Header");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<OfficerSession | null>(null);
  const firebaseEnabled = isFirebaseAuthConfigured();
  const [showSignIn, setShowSignIn] = useState(false);
  const [authTab, setAuthTab] = useState<"passcode" | "firebase">("passcode");
  const [passcode, setPasscode] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);
  const initialCode = searchParams.get("code")?.trim() ?? "";
  const [communeCode, setCommuneCode] = useState(initialCode);
  const [pickingCommune, setPickingCommune] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationReady, setConversationReady] = useState(false);
  const [focusReady, setFocusReady] = useState(false);
  const [view, setView] = useState<"chat" | "watch">("chat");
  const [pendingRuns, setPendingRuns] = useState(0);

  useEffect(() => {
    setSession(readStoredSession());
  }, []);

  useEffect(() => {
    setMessages(readStoredConversation());
    setConversationReady(true);
  }, []);

  useEffect(() => {
    if (conversationReady) writeStoredConversation(messages);
  }, [messages, conversationReady]);

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
    if (signingIn) return;
    if (authTab === "firebase" && firebaseEnabled) {
      const trimmedEmail = email.trim();
      if (!trimmedEmail || !password) return;
      setSigningIn(true);
      setSignInError(null);
      try {
        const result = await api.firebaseOfficerLogin(trimmedEmail, password);
        setSession(result);
        setPassword("");
        setShowSignIn(false);
        writeStoredSession(result);
      } catch (err) {
        if (err instanceof ApiError) {
          setSignInError(
            err.status === 401
              ? t("signIn.errors.invalidCredentials")
              : t("errors.server"),
          );
        } else {
          setSignInError(t("errors.network"));
        }
      } finally {
        setSigningIn(false);
      }
      return;
    }

    const code = passcode.trim();
    if (!code) return;
    setSigningIn(true);
    setSignInError(null);
    try {
      const result = await api.officerLogin(code);
      setSession(result);
      setPasscode("");
      setShowSignIn(false);
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
                : t("errors.server"),
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
            <Link className="nav-link label-medium" href="/assistant" aria-current="page">
              {headerT("assistant")}
            </Link>
          </nav>
          <LanguageSwitcher />
        </div>
      </header>

      <main className="assistant-main">
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
                <MapPinIcon />
                <span>{t("focusAdd")}</span>
              </button>
            )
          )}

          {messages.length > 0 && (!activeSession || view === "chat") && (
            <button
              type="button"
              className="btn btn--outline btn--compact label-small"
              onClick={clearConversation}
            >
              {t("clearConversation")}
            </button>
          )}

          {activeSession ? (
            <button
              type="button"
              className="btn btn--outline btn--compact label-small"
              onClick={clearSession}
              title={
                activeSession.email
                  ? t("signedInAs", {
                      officer: activeSession.email,
                      time: formatExpiry(activeSession.expires_at, locale),
                    })
                  : t("signedIn", { time: formatExpiry(activeSession.expires_at, locale) })
              }
            >
              {t("signOut")}
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--outline btn--compact label-small"
              aria-expanded={showSignIn}
              onClick={() => setShowSignIn((prev) => !prev)}
            >
              <ShieldIcon />
              <span>{t("signIn.title")}</span>
            </button>
          )}
        </div>

        {!activeSession && showSignIn && (
          <section className="surface assistant-signin-panel" aria-label={t("signIn.title")}>
            <div className="assistant-signin-head">
              <h2 className="title-small" style={{ margin: 0 }}>
                {t("signIn.title")}
              </h2>
              {firebaseEnabled && (
                <div className="assistant-signin-tabs" role="tablist" aria-label={t("signIn.methodAria")}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={authTab === "passcode"}
                    className="chip label-small"
                    onClick={() => {
                      setAuthTab("passcode");
                      setSignInError(null);
                    }}
                  >
                    {t("signIn.methodPasscode")}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={authTab === "firebase"}
                    className="chip label-small"
                    onClick={() => {
                      setAuthTab("firebase");
                      setSignInError(null);
                    }}
                  >
                    {t("signIn.methodAccount")}
                  </button>
                </div>
              )}
            </div>
            <form className="assistant-signin-row" onSubmit={(event) => void signIn(event)}>
              {authTab === "firebase" && firebaseEnabled ? (
                <>
                  <input
                    className="text-field assistant-signin-input"
                    type="email"
                    id="officer-email"
                    name="email"
                    value={email}
                    placeholder={t("signIn.emailPlaceholder")}
                    aria-label={t("signIn.email")}
                    aria-invalid={signInError != null}
                    autoComplete="username"
                    onChange={(event) => setEmail(event.target.value)}
                  />
                  <input
                    className="text-field assistant-signin-input"
                    type="password"
                    id="officer-password"
                    name="password"
                    value={password}
                    placeholder={t("signIn.passwordPlaceholder")}
                    aria-label={t("signIn.password")}
                    aria-invalid={signInError != null}
                    autoComplete="current-password"
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    type="submit"
                    className="btn btn--filled label-medium"
                    disabled={signingIn || email.trim().length === 0 || password.length === 0}
                  >
                    {signingIn ? t("signIn.working") : t("signIn.submit")}
                  </button>
                </>
              ) : (
                <>
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
                </>
              )}
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

        {pickingCommune && !communeCode && (
          <section aria-label={t("focusAdd")}>
            <CommuneSearch
              compact
              onPick={(code) => {
                setCommuneCode(code);
                setPickingCommune(false);
              }}
            />
            <div style={{ marginTop: 8, textAlign: "end" }}>
              <button
                type="button"
                className="btn btn--outline btn--compact label-small"
                onClick={() => setPickingCommune(false)}
              >
                {t("focusCancel")}
              </button>
            </div>
          </section>
        )}

        {activeSession && (
          <div className="assistant-tabs" role="tablist" aria-label={t("tabs.aria")}>
            <button
              type="button"
              role="tab"
              id="assistant-chat-tab"
              aria-controls="assistant-chat-panel"
              aria-selected={view === "chat"}
              className="assistant-tab label-medium"
              onClick={() => setView("chat")}
            >
              {t("tabs.chat")}
            </button>
            <button
              type="button"
              role="tab"
              id="assistant-watch-tab"
              aria-controls="assistant-watch-panel"
              aria-selected={view === "watch"}
              className="assistant-tab label-medium"
              onClick={() => setView("watch")}
            >
              {t("tabs.watch")}
              {pendingRuns > 0 && (
                <span
                  className="assistant-tab-badge"
                  aria-label={t("tabs.pending", { count: pendingRuns })}
                >
                  {pendingRuns}
                </span>
              )}
            </button>
          </div>
        )}

        <div
          id="assistant-chat-panel"
          className="assistant-panel"
          role={activeSession ? "tabpanel" : undefined}
          aria-labelledby={activeSession ? "assistant-chat-tab" : undefined}
          hidden={Boolean(activeSession) && view !== "chat"}
        >
          <AssistantChat
            communeCode={communeCode || null}
            session={activeSession?.session ?? null}
            onSessionInvalid={clearSession}
            messages={messages}
            setMessages={setMessages}
          />
        </div>

        {activeSession && (
          <div
            id="assistant-watch-panel"
            className="assistant-panel"
            role="tabpanel"
            aria-labelledby="assistant-watch-tab"
            hidden={view !== "watch"}
          >
            <WatchRuns
              session={activeSession}
              communeCode={communeCode || null}
              onSessionInvalid={clearSession}
              onPendingChange={setPendingRuns}
            />
          </div>
        )}
      </main>
    </div>
  );
}
