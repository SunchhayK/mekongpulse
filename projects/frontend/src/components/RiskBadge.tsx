import type { FloodRiskTier } from "@/lib/api";
import { TIER_META } from "@/lib/design";

export interface RiskBadgeProps {
  /** Inundation risk tier calculated by the spatial reasoning engine */
  tier: FloodRiskTier;
  /** Estimated hours until flood arrival (e.g. 36) */
  leadTimeHours?: number;
  /** Display language: 'km' (Khmer) or 'en' (English) */
  lang?: "km" | "en";
  /** Material 3 badge size */
  size?: "small" | "large";
}

export function RiskBadge({ tier, leadTimeHours, lang = "en", size = "small" }: RiskBadgeProps) {
  const meta = TIER_META[tier];
  return (
    <span
      className={`risk-badge ${size === "large" ? "risk-badge--large" : ""} ${
        size === "large" ? "label-large" : "label-medium"
      }`}
      data-tier={tier}
      role="status"
    >
      <span aria-hidden="true">{meta.emoji}</span>
      {lang === "km" ? meta.labelKh : meta.labelEn}
      {leadTimeHours != null && (
        <span className="lead-time">
          · ~{leadTimeHours}h{lang === "km" ? " ទៀត" : ""}
        </span>
      )}
    </span>
  );
}
