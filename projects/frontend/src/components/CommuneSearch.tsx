"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError, type SearchHit } from "@/lib/api";
import { MapPinIcon, SearchIcon } from "./icons";

export interface CommuneSearchProps {
  onPick: (communeCode: string) => void;
}

export function CommuneSearch({ onPick }: CommuneSearchProps) {
  const t = useTranslations("Search");
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
            `${t("errorLookup")}${err instanceof ApiError ? ` (${err.status})` : ""}`,
          );
        }
      } finally {
        if (requestId.current === id) setBusy(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

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
        setError(
          t("errorDenied"),
        );
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  return (
    <div className="card">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          {t("title")}
        </h2>
      </div>
      <form
        className="search-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (results.length > 0) onPick(results[0].commune_code);
        }}
      >
        <div className="search-field">
          <span className="search-icon" aria-hidden="true">
            <SearchIcon />
          </span>
          <input
            className="text-field"
            type="search"
            id="commune-search"
            name="q"
            value={query}
            placeholder={t("placeholder")}
            aria-label={t("inputAria")}
            aria-invalid={error != null}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </form>
      <div className="chip-row" style={{ marginTop: 10 }}>
        <button type="button" className="chip label-medium" onClick={sendGpsLocation} disabled={busy}>
          <MapPinIcon /> {t("gps")}
        </button>
      </div>
      {error && (
        <p className="body-small" style={{ color: "var(--error-ink)", marginTop: 10 }} role="alert">
          {error}
        </p>
      )}
      {busy && <div className="shimmer" style={{ marginTop: 12, height: 40 }} aria-busy="true" />}
      {!busy && results.length > 0 && (
        <ul className="search-results">
          {results.map((hit) => (
            <li key={hit.commune_code}>
              <button type="button" onClick={() => onPick(hit.commune_code)}>
                <span className="body-medium" lang="km">
                  {hit.name_kh}
                </span>{" "}
                <span className="body-medium">{hit.name_en}</span>
                <span className="body-small muted">
                  {" "}
                  · {hit.district_en ?? "—"} · {hit.province_en ?? "—"} ·{" "}
                  <span className="code">{hit.commune_code}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!busy && query.trim().length >= 2 && results.length === 0 && !error && (
        <p className="body-small muted" style={{ marginTop: 8 }} data-empty="true">
          {t("noMatch")}
        </p>
      )}
    </div>
  );
}
