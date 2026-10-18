"use client";

import { useTranslations } from "next-intl";
import type { FloodRiskTier } from "@/lib/api";
import { TIER_META } from "@/lib/design";

export interface RiskBadgeProps {
  /** Inundation risk tier calculated by the spatial reasoning engine */
  tier: FloodRiskTier;
  /** Estimated hours until flood arrival (e.g. 36) */
  leadTimeHours?: number;
  /** Material 3 badge size */
  size?: "small" | "large";
}

export function RiskBadge({ tier, leadTimeHours, size = "small" }: RiskBadgeProps) {
  const t = useTranslations("Tier");
  return (
    <span
      className={`risk-badge ${size === "large" ? "risk-badge--large label-large" : "label-medium"}`}
      data-tier={tier}
      role="status"
    >
      <span className="dot" aria-hidden="true" />
      {t(tier)}
      {leadTimeHours != null && (
        <span className="lead-time">{t("lead", { hours: leadTimeHours })}</span>
      )}
    </span>
  );
}
