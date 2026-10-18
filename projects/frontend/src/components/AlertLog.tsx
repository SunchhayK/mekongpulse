"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type AlertLogEntry } from "@/lib/api";
import { formatDateTime, TIER_META } from "@/lib/design";

const LOG_LIMIT = 50;

/** Alert dispatch log for the officials' console (FR-10). */
export function AlertLog() {
  const [entries, setEntries] = useState<AlertLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .alertLog(LOG_LIMIT)
      .then((next) => {
        if (!cancelled) setEntries(next);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError && err.status >= 500
            ? `Alert log gateway: the dispatch log is unavailable (HTTP ${err.status}).`
            : "Alert log gateway: could not load the dispatch log.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="card" id="alerts" aria-label="Alert dispatch log">
      <div className="card-title-row">
        <h2 className="title-medium" style={{ margin: 0 }}>
          Alert dispatch log / កំណត់ហេតុការជូនដំណឹង
        </h2>
        <span className="body-small muted">latest {LOG_LIMIT} · newest first</span>
      </div>

      {loading ? (
        <div className="shimmer" style={{ height: 140 }} aria-busy="true" />
      ) : error ? (
        <p className="error-banner body-medium" role="alert">
          {error}
        </p>
      ) : entries.length === 0 ? (
        <p className="empty-state body-medium" data-empty="true">
          No alerts dispatched yet.
        </p>
      ) : (
        <div className="summary-table-wrap">
          <table className="summary-table body-small" aria-label="Alert dispatch log, newest first">
            <thead>
              <tr>
                <th scope="col">Dispatched</th>
                <th scope="col">Commune</th>
                <th scope="col">Province</th>
                <th scope="col">Tier</th>
                <th scope="col">Directive</th>
                <th scope="col">Recipients</th>
                <th scope="col">Voice note</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id ?? `${entry.commune_code}-${entry.dispatched_at}`}>
                  <td className="muted">{formatDateTime(entry.dispatched_at)}</td>
                  <td>
                    <span lang="km">{entry.commune_name_kh || entry.commune_code}</span>
                    <br />
                    {entry.commune_name_en || entry.commune_code}
                  </td>
                  <td className="muted">{entry.province ?? "—"}</td>
                  <td>
                    <span className="tier-cell">
                      <span
                        className="tier-dot"
                        style={{ background: TIER_META[entry.risk_tier].color }}
                        aria-hidden="true"
                      />
                      {TIER_META[entry.risk_tier].labelEn}
                    </span>
                  </td>
                  <td>
                    {entry.directive_title || "—"}
                    {entry.bulletin_text ? (
                      <details className="body-small" style={{ marginTop: 4 }}>
                        <summary className="muted">Bulletin / សេចក្តីលម្អិត</summary>
                        <p lang="km" className="muted" style={{ margin: "6px 0 0" }}>
                          {entry.bulletin_text}
                        </p>
                      </details>
                    ) : null}
                  </td>
                  <td className="mono">{entry.recipients_count.toLocaleString()}</td>
                  <td>
                    {entry.audio_url ? (
                      <a
                        href={entry.audio_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open the Khmer voice bulletin for ${entry.commune_name_en || entry.commune_code} in a new tab`}
                      >
                        Listen
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
