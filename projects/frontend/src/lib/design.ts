// Shared design constants: risk tier metadata and map bounds.

import type { FloodRiskTier } from "./api";

export const TIER_ORDER: FloodRiskTier[] = ["NORMAL", "ADVISORY", "WARNING", "DANGER"];

export const TIER_META: Record<
  FloodRiskTier,
  { color: string; ink: string; labelKh: string; labelEn: string }
> = {
  NORMAL: { color: "var(--tier-normal)", ink: "var(--tier-normal-ink)", labelKh: "ធម្មតា", labelEn: "Normal" },
  ADVISORY: { color: "var(--tier-advisory)", ink: "var(--tier-advisory-ink)", labelKh: "ប្រុងប្រយ័ត្ន", labelEn: "Advisory" },
  WARNING: { color: "var(--tier-warning)", ink: "var(--tier-warning-ink)", labelKh: "ព្រមាន", labelEn: "Warning" },
  DANGER: { color: "var(--tier-danger)", ink: "var(--tier-danger-ink)", labelKh: "គ្រោះថ្នាក់", labelEn: "Danger" },
};

export function tierSeverity(tier: FloodRiskTier): number {
  return TIER_ORDER.indexOf(tier);
}

// Approximate Cambodia basin bounding box; centers the interactive Leaflet map.
export const KH_BBOX = { minLat: 9.9, maxLat: 14.7, minLng: 102.3, maxLng: 107.7 };

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Phnom_Penh",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return dateTimeFormat.format(date);
}

export function formatMeters(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function formatRate(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)} m/hr`;
}
