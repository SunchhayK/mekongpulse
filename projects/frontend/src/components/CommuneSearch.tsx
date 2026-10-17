"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, type SearchHit } from "@/lib/api";
import { MapPinIcon, SearchIcon } from "./icons";

export interface CommuneSearchProps {
  onPick: (communeCode: string) => void;
}

export function CommuneSearch({ onPick }: CommuneSearchProps) {
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
            `Commune Search: lookup failed${err instanceof ApiError ? ` (${err.status})` : ""}. Retry or pick a commune from the map.`,
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
      setError("Location Resolver: this browser cannot share a GPS pin. Select your commune from the menu.");
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
              ? "Location Resolver: coordinates are outside the Mekong river basin. Select your target commune from the menu."
              : "Location Resolver: GPS pin could not be resolved. Select your commune from the menu.",
          );
        } finally {
          setBusy(false);
        }
      },
      () => {
        setBusy(false);
        setError(
          "Location Resolver: GPS permission was denied. Select your target commune from the menu.",
        );
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  return (
    <div className="card">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          Commune lookup / ស្វែងរកឃុំ
        </h2>
      </div>
      <form
        className="search-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (results.length > 0) onPick(results[0].commune_code);
        }}
      >
        <input
          className="text-field"
          type="search"
          id="commune-search"
          name="q"
          value={query}
          placeholder="Koh Thom, កោះធំ, 080404…"
          aria-label="Search commune by Khmer or English name or 6-digit code"
          aria-invalid={error != null}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" className="btn btn--tonal" disabled={busy} aria-busy={busy}>
          <SearchIcon />
          <span className="sr-only">Search</span>
        </button>
      </form>
      <div className="chip-row" style={{ marginTop: 8 }}>
        <button type="button" className="chip label-medium" onClick={sendGpsLocation} disabled={busy}>
          <MapPinIcon /> Send GPS location · ផ្ញើទីតាំង GPS
        </button>
      </div>
      {error && (
        <p className="body-small" style={{ color: "var(--md-sys-color-error)", marginTop: 8 }} role="alert">
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
          No commune matched. Try a Khmer name (កោះធំ), an English variant (Koh Thom), or a 6-digit
          code.
        </p>
      )}
    </div>
  );
}
