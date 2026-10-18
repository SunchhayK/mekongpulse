"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { PauseIcon, PlayIcon, VolumeIcon } from "./icons";

export interface VoicePlayerProps {
  /** Cloud Storage audio URL (MP3 format) */
  audioSrc?: string;
  /** Total audio length in seconds */
  durationSeconds?: number;
  /** Plain text transcript of the spoken Khmer message */
  transcriptKhmer: string;
  /** English summary translation */
  transcriptEnglish?: string;
  /** Automatically play when message arrives in Telegram */
  autoPlay?: boolean;
}

function formatClock(seconds: number): string {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const minutes = Math.floor(safe / 60);
  const rest = Math.floor(safe % 60);
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

export function VoicePlayer({
  audioSrc,
  durationSeconds,
  transcriptKhmer,
  transcriptEnglish,
  autoPlay = false,
}: VoicePlayerProps) {
  const t = useTranslations("Voice");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(durationSeconds ?? 0);
  const [showTranscript, setShowTranscript] = useState(!audioSrc);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !autoPlay || !audioSrc) return;
    audio.play().then(
      () => setPlaying(true),
      () => setPlaying(false),
    );
  }, [autoPlay, audioSrc]);

  function toggle() {
    const audio = audioRef.current;
    if (!audio || !audioSrc) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      audio.play().then(
        () => setPlaying(true),
        () => setPlaying(false),
      );
    }
  }

  return (
    <div className="voice-player">
      <audio
        ref={audioRef}
        src={audioSrc}
        preload="metadata"
        onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
        onLoadedMetadata={(event) =>
          setDuration(
            Number.isFinite(event.currentTarget.duration)
              ? event.currentTarget.duration
              : durationSeconds ?? 0,
          )
        }
        onEnded={() => {
          setPlaying(false);
          setCurrent(0);
        }}
      />
      <button
        type="button"
        className="play-btn"
        onClick={toggle}
        disabled={!audioSrc}
        aria-label={t("playAria")}
      >
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <div className="scrub">
        <input
          type="range"
          id="voice-scrub"
          name="voice-scrub"
          min={0}
          max={duration || 1}
          step={0.1}
          value={current}
          disabled={!audioSrc}
          aria-label={t("seekAria")}
          onChange={(event) => {
            const value = Number(event.target.value);
            setCurrent(value);
            if (audioRef.current) audioRef.current.currentTime = value;
          }}
        />
        <div className="label-small time">
          {formatClock(current)} / {formatClock(duration)} · <VolumeIcon />
        </div>
        {audioSrc ? (
          <button
            type="button"
            className="toggle-transcript label-small"
            aria-expanded={showTranscript}
            onClick={() => setShowTranscript((value) => !value)}
          >
            {showTranscript ? t("hideTranscript") : t("showTranscript")}
          </button>
        ) : (
          <p className="label-small voice-note" style={{ margin: 0 }}>
            {t("attachNote")}
          </p>
        )}
        {showTranscript && (
          <div lang="km">
            <p className="body-medium transcript transcript-km">{transcriptKhmer}</p>
            {transcriptEnglish && (
              <p className="body-small transcript transcript-en" lang="en">
                {transcriptEnglish}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
