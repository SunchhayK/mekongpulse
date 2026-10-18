"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

/**
 * Khmer | EN pill for the header. Renders real anchors to the pre-rendered
 * locale routes (/km, /en), so it works in the static export even before
 * hydration; next-intl's Link handles the client-side transition.
 */
export function LanguageSwitcher() {
  const locale = useLocale();
  const t = useTranslations("LanguageSwitcher");
  const pathname = usePathname();

  return (
    <span className="lang-switch label-small" role="group" aria-label={t("aria")}>
      {routing.locales.map((option, index) => (
        <span key={option} className="lang-switch-option">
          {index > 0 && (
            <span className="lang-sep" aria-hidden="true">
              |
            </span>
          )}
          <Link
            href={pathname}
            locale={option}
            aria-current={option === locale ? "true" : undefined}
            lang={option}
          >
            {option === "km" ? t("km") : t("en")}
          </Link>
        </span>
      ))}
    </span>
  );
}
