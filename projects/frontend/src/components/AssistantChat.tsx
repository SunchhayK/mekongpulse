"use client";

import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useLocale, useTranslations } from "next-intl";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, ApiError, type AdvisorAction, type AdvisorToolCall } from "@/lib/api";
import { MicIcon, SendIcon, StopIcon } from "./icons";

export interface AssistantChatProps {
  /** Commune the conversation is grounded in; sent as commune_code. */
  communeCode?: string | null;
  /** Raw officer session token; absent means draft-only (read queries still work). */
  session?: string | null;
  /** Called when /advisor rejects the session (401) so the page can sign out. */
  onSessionInvalid?: () => void;
  /** Thread state is owned by the page so its header can clear it. */
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: AdvisorToolCall[];
  actions?: AdvisorAction[];
}

/** Markdown replies never load raw HTML; links leave the app safely. */
const MARKDOWN_COMPONENTS: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  table: ({ node: _node, ...props }) => (
    <div className="assistant-md-table">
      <table {...props} />
    </div>
  ),
};

const HISTORY_TURNS = 6;
/** Hard cap: the transcribe endpoint rejects long uploads. */
const MAX_RECORDING_SECONDS = 60;
const PREFERRED_MIME = "audio/webm;codecs=opus";

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

function readAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * Officer assistant conversation: agentic advisor turns with tool-call tracing,
 * a pinned composer row, and Khmer voice input transcribed by the server
 * (browser speech APIs do not cover Khmer).
 */
export function AssistantChat({
  communeCode,
  session,
  onSessionInvalid,
  messages,
  setMessages,
}: AssistantChatProps) {
  const t = useTranslations("Officer");
  const locale = useLocale() === "en" ? "en" : "km";
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Voice input. Supported browsers only: never render the mic when the
  // recorder APIs are missing (checked after mount so the export prerenders).
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const threadRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const discardRef = useRef(false);
  const startedAtRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setVoiceSupported(
      typeof MediaRecorder !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function",
    );
  }, []);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    // Unmount: drop the recording and release the microphone.
    return () => {
      discardRef.current = true;
      stopTimer();
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      recorderRef.current = null;
      releaseStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function stopTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function releaseStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopTimer();
    setRecording(false);
  }

  function cancelRecording() {
    discardRef.current = true;
    stopRecording();
  }

  async function startRecording() {
    if (recording || transcribing) return;
    setVoiceError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setVoiceError(t("voice.errors.denied"));
      return;
    }
    streamRef.current = stream;

    let recorder: MediaRecorder;
    try {
      recorder =
        typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(PREFERRED_MIME)
          ? new MediaRecorder(stream, { mimeType: PREFERRED_MIME })
          : new MediaRecorder(stream);
    } catch {
      releaseStream();
      setVoiceError(t("voice.errors.unsupported"));
      return;
    }

    chunksRef.current = [];
    discardRef.current = false;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      void transcribeRecording(recorder);
    };
    recorder.onerror = () => {
      discardRef.current = true;
      setVoiceError(t("voice.errors.failed"));
    };
    recorderRef.current = recorder;
    recorder.start();
    startedAtRef.current = Date.now();
    setElapsed(0);
    setRecording(true);
    timerRef.current = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsed(Math.min(seconds, MAX_RECORDING_SECONDS));
      if (seconds >= MAX_RECORDING_SECONDS) stopRecording();
    }, 500);
  }

  async function transcribeRecording(recorder: MediaRecorder) {
    const mimeType = recorder.mimeType || "audio/webm";
    recorderRef.current = null;
    releaseStream();
    const chunks = chunksRef.current;
    chunksRef.current = [];
    if (discardRef.current || chunks.length === 0) return;

    setTranscribing(true);
    try {
      const dataUrl = await readAsDataUrl(new Blob(chunks, { type: mimeType }));
      const { text } = await api.transcribe({
        audio_base64: dataUrl.slice(dataUrl.indexOf(",") + 1),
        mime_type: mimeType,
        locale_hint: locale,
      });
      const transcript = text.trim();
      if (transcript) {
        // Append and focus; the officer reviews before sending.
        setInput((current) => (current ? `${current} ${transcript}` : transcript));
        window.requestAnimationFrame(() => inputRef.current?.focus());
      }
    } catch (err) {
      setVoiceError(
        err instanceof ApiError
          ? err.status === 413
            ? t("voice.errors.tooLarge")
            : err.status === 503
              ? t("voice.errors.unavailable")
              : t("voice.errors.failed")
          : t("voice.errors.network"),
      );
    } finally {
      setTranscribing(false);
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
        session ?? undefined,
      );
      setMessages((current) => [
        ...current,
        { role: "assistant", content: reply.reply, toolCalls: reply.tool_calls, actions: reply.actions },
      ]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Keep the conversation; drop the dead session and go draft-only.
        onSessionInvalid?.();
        setError(t("errors.sessionExpired"));
      } else {
        setError(
          err instanceof ApiError
            ? err.status === 503
              ? t("errors.unavailable")
              : `${t("errors.server")} (${err.status})`
            : t("errors.network"),
        );
      }
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

  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <div className="assistant-chat">
      <div className="assistant-thread" ref={threadRef} aria-label={t("conversationAria")}>
        {messages.length === 0 && (
          <p className="body-medium muted" data-empty="true">
            {t("empty")}
          </p>
        )}
        {messages.map((message, index) => (
          <div key={index} className="officer-turn" data-role={message.role}>
            <span className="officer-role label-small">
              {message.role === "user" ? t("you") : t("assistant")}
            </span>
            <div className="officer-bubble body-medium" data-role={message.role}>
              {message.role === "assistant" ? (
                <div className="assistant-md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              ) : (
                message.content
              )}
            </div>
            {message.toolCalls && message.toolCalls.length > 0 && (
              <details className={`officer-tools assistant-tools--${message.role}`}>
                <summary className="label-small">{t("toolsUsed", { count: message.toolCalls.length })}</summary>
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
          <p className="body-medium muted" aria-live="polite">
            {t("thinking")}
          </p>
        )}
      </div>

      <div className="assistant-compose">
        <div className="chip-row officer-quick">
          {(["summary", "draft", "post"] as const).map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="chip label-small"
              disabled={busy || recording}
              onClick={() => void send(t(`quickPrompts.${prompt}`))}
            >
              {t(`quickPrompts.${prompt}`)}
            </button>
          ))}
        </div>

        {recording && (
          <div className="voice-strip" role="status">
            <span className="voice-dot" aria-hidden="true" />
            <span className="label-medium">{t("voice.recording")}</span>
            <span className="voice-time body-medium">{clock}</span>
            <span className="body-small muted">{t("voice.limit")}</span>
            <span className="spacer" />
            <button
              type="button"
              className="btn btn--filled label-small voice-stop"
              onClick={stopRecording}
            >
              <StopIcon /> {t("voice.stop")}
            </button>
            <button type="button" className="btn voice-cancel label-small" onClick={cancelRecording}>
              {t("voice.cancel")}
            </button>
          </div>
        )}

        {transcribing && (
          <p className="body-small muted" style={{ margin: 0 }} role="status">
            {t("voice.transcribing")}
          </p>
        )}

        <form
          className="officer-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          {voiceSupported && (
            <button
              type="button"
              className="btn mic-btn"
              data-recording={recording}
              disabled={busy || transcribing || recording}
              aria-label={t("voice.start")}
              title={t("voice.start")}
              onClick={() => void startRecording()}
            >
              <MicIcon />
            </button>
          )}
          <input
            ref={inputRef}
            className="text-field officer-input"
            type="text"
            id="assistant-message"
            name="message"
            value={input}
            placeholder={t("inputPlaceholder")}
            aria-label={t("inputAria")}
            maxLength={2000}
            disabled={recording}
            onChange={(event) => setInput(event.target.value)}
          />
          <button
            type="submit"
            className="btn btn--filled officer-send"
            disabled={busy || recording || input.trim().length === 0}
            aria-label={t("sendAria")}
          >
            <SendIcon />
          </button>
        </form>

        {voiceError && (
          <p className="error-banner body-small" role="alert">
            {voiceError}
          </p>
        )}
        {error && (
          <p className="error-banner body-small" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
