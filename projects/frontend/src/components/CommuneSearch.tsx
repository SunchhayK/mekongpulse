"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError, type SearchHit } from "@/lib/api";
import { MapPinIcon, SearchIcon } from "./icons";

export interface CommuneSearchProps {
  onPick: (communeCode: string) => void;
  /** Compact panel variant used inside Assistant focus picker. */
  compact?: boolean;
}

export function CommuneSearch({ onPick, compact = false }: CommuneSearchProps) {
  const t = useTranslations("Search");
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setError(null);
      return;
    }
    const id = ++requestId.current;
    const timer = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const hits = await api.search(trimmed);
        if (requestId.current === id) setResults(hits);
      } catch (err) {
        if (requestId.current === id) {
          setResults([]);
          setError(
            err instanceof ApiError && err.status >= 500
              ? t("errorLookup")
              : t("errorLookup"),
          );
        }
      } finally {
        if (requestId.current === id) setBusy(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, t]);

  function sendGpsLocation() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setError(t("errorNoGeolocation"));
      return;
    }
    setBusy(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const resolved = await api.resolve(position.coords.latitude, position.coords.longitude);
          onPick(resolved.commune_code);
        } catch (err) {
          setError(
            err instanceof ApiError && err.problemType?.endsWith("outside-basin")
              ? t("errorOutsideBasin")
              : t("errorResolve"),
          );
        } finally {
          setBusy(false);
        }
      },
      () => {
        setBusy(false);
        setError(t("errorDenied"));
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  function handlePick(code: string) {
    setQuery("");
    setResults([]);
    onPick(code);
  }

  return (
    <div className={compact ? "surface surface--padded" : "hero-search-wrap"}>
      <form
        className="hero-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (results.length > 0) handlePick(results[0].commune_code);
        }}
      >
        <div className="search-field">
          <label htmlFor={inputId} className="sr-only">
            {t("inputAria")}
          </label>
          <span className="search-icon" aria-hidden="true">
            <SearchIcon />
          </span>
          <input
            className="text-field"
            type="search"
            id={inputId}
            name="q"
            value={query}
            placeholder={t("placeholder")}
            aria-invalid={error != null}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <button
          type="button"
          className="btn btn--outline label-medium"
          onClick={sendGpsLocation}
          disabled={busy}
        >
          <MapPinIcon />
          <span>{t("gps")}</span>
        </button>
      </form>

      {error && (
        <p className="body-small" style={{ color: "var(--error-ink)", margin: "8px 0 0" }} role="alert">
          {error}
        </p>
      )}
      {busy && <div className="shimmer" style={{ marginTop: 10, height: 44 }} aria-busy="true" />}

      {!busy && results.length > 0 && (
        <div className="search-results-panel">
          <ul className="search-results">
            {results.map((hit) => {
              const locationParts = [hit.district_en, hit.province_en].filter(Boolean).join(", ");
              return (
                <li key={hit.commune_code}>
                  <button type="button" onClick={() => handlePick(hit.commune_code)}>
                    <span className="title-small" lang="km">
                      {hit.name_kh}
                    </span>
                    <span className="body-small search-result-meta">
                      {hit.name_en}
                      {locationParts ? `, ${locationParts}` : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {!busy && query.trim().length >= 2 && results.length === 0 && !error && (
        <p className="body-small muted" style={{ margin: "8px 0 0" }} data-empty="true">
          {t("noMatch")}
        </p>
      )}
    </div>
  );
}
