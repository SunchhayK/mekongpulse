// Shared design constants: risk tier metadata, crop stages, projections.

import type { CropStage, FloodRiskTier } from "./api";

export const TIER_ORDER: FloodRiskTier[] = ["NORMAL", "ADVISORY", "WARNING", "DANGER"];

export const TIER_META: Record<
  FloodRiskTier,
  { color: string; emoji: string; labelKh: string; labelEn: string }
> = {
  NORMAL: { color: "#10b981", emoji: "🟢", labelKh: "ធម្មតា", labelEn: "NORMAL" },
  ADVISORY: { color: "#fbbf24", emoji: "🟡", labelKh: "ប្រុងប្រយ័ត្ន", labelEn: "ADVISORY" },
  WARNING: { color: "#f97316", emoji: "🟠", labelKh: "ព្រមាន", labelEn: "WARNING" },
  DANGER: { color: "#ef4444", emoji: "🔴", labelKh: "គ្រោះថ្នាក់", labelEn: "DANGER" },
};

export const CROP_STAGES: { value: CropStage; labelKh: string; labelEn: string }[] = [
  { value: "TILLERING", labelKh: "បែកកូន", labelEn: "Tillering" },
  { value: "VEGETATIVE", labelKh: "លូតលាស់", labelEn: "Vegetative" },
  { value: "FLOWERING", labelKh: "ចេញផ្កា", labelEn: "Flowering" },
  { value: "RIPENING", labelKh: "ទុំ", labelEn: "Ripening" },
];

export function tierSeverity(tier: FloodRiskTier): number {
  return TIER_ORDER.indexOf(tier);
}

// Approximate Cambodia basin bounding box for the offline SVG map.
export const KH_BBOX = { minLat: 9.9, maxLat: 14.7, minLng: 102.3, maxLng: 107.7 };

export function project(
  lat: number,
  lng: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const x = ((lng - KH_BBOX.minLng) / (KH_BBOX.maxLng - KH_BBOX.minLng)) * width;
  const y = (1 - (lat - KH_BBOX.minLat) / (KH_BBOX.maxLat - KH_BBOX.minLat)) * height;
  return { x, y };
}

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
