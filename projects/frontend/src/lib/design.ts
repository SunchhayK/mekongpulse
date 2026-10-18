// Shared design constants: risk tier metadata and map bounds.

import type { FloodRiskTier } from "./api";

export const TIER_ORDER: FloodRiskTier[] = ["NORMAL", "ADVISORY", "WARNING", "DANGER"];

// Tier labels live in src/messages/*.json under the "Tier" namespace.
export const TIER_META: Record<FloodRiskTier, { color: string; ink: string }> = {
  NORMAL: { color: "var(--tier-normal)", ink: "var(--tier-normal-ink)" },
  ADVISORY: { color: "var(--tier-advisory)", ink: "var(--tier-advisory-ink)" },
  WARNING: { color: "var(--tier-warning)", ink: "var(--tier-warning-ink)" },
  DANGER: { color: "var(--tier-danger)", ink: "var(--tier-danger-ink)" },
};

export function tierSeverity(tier: FloodRiskTier): number {
  return TIER_ORDER.indexOf(tier);
}

// Approximate Cambodia basin bounding box; centers the interactive Leaflet map.
export const KH_BBOX = { minLat: 9.9, maxLat: 14.7, minLng: 102.3, maxLng: 107.7 };

/**
 * BCP 47 tag used for Intl formatting. Falls back to en-GB when the runtime
 * lacks Khmer locale data (supportedLocalesOf returns an empty list).
 */
export function intlLocale(appLocale: string): string {
  const candidates = appLocale === "km" ? ["km-KH", "km"] : ["en-GB"];
  for (const candidate of candidates) {
    try {
      if (Intl.DateTimeFormat.supportedLocalesOf(candidate).length > 0) return candidate;
    } catch {
      // Intl unavailable — fall through to the default.
    }
  }
  return "en-GB";
}

const dateTimeFormats = new Map<string, Intl.DateTimeFormat>();

export function formatDateTime(iso: string, locale = "en"): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const tag = intlLocale(locale);
  let formatter = dateTimeFormats.get(tag);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(tag, {
      timeZone: "Asia/Phnom_Penh",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    dateTimeFormats.set(tag, formatter);
  }
  return formatter.format(date);
}

export function formatNumber(value: number, locale = "en"): string {
  return new Intl.NumberFormat(intlLocale(locale)).format(value);
}

export function formatMeters(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function formatRate(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)} m/hr`;
}
