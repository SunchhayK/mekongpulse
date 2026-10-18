// Client-side CSV export helpers (RFC 4180) for the officials' console.
// Pure string builders plus one DOM download shim; no server round-trip.

import type { CommuneRiskRow } from "./api";

/** Quote when a field holds a comma, a quote, a line break, or edge whitespace. */
const NEEDS_QUOTING = /[",\r\n]|^\s|\s$/;

function csvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (!NEEDS_QUOTING.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

export function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows.map((row) => row.map(csvField).join(",")).join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
  // UTF-8 BOM: Excel otherwise mis-reads Khmer names as a legacy codepage.
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

const RISK_REGISTER_HEADER = [
  "commune_code",
  "commune_name_kh",
  "commune_name_en",
  "province",
  "tier",
  "score",
  "lead_time_hours",
  "station_id",
  "estimated",
  "lat",
  "lng",
  "updated_at",
];

export function riskRegisterCsv(rows: CommuneRiskRow[]): string {
  return toCsv([
    RISK_REGISTER_HEADER,
    ...rows.map((row) => [
      row.commune_code,
      row.commune_name_kh,
      row.commune_name_en,
      row.province,
      row.tier,
      row.score,
      row.lead_time_hours,
      row.station_id,
      row.estimated ? "true" : "false",
      row.lat,
      row.lng,
      row.updated_at,
    ]),
  ]);
}
