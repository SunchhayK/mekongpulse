"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

function LanguageSwitcherInner() {
  const locale = useLocale();
  const t = useTranslations("LanguageSwitcher");
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const query: Record<string, string> = {};
  const code = searchParams.get("code");
  const stage = searchParams.get("stage");
  if (code) query.code = code;
  if (stage) query.stage = stage;
  const hasQuery = Object.keys(query).length > 0;

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
            href={hasQuery ? { pathname, query } : pathname}
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

function LanguageSwitcherFallback() {
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

/**
 * Unified Khmer | EN pill for all routes. Preserves ?code= and ?stage= query
 * parameters on commune and assistant pages while staying static-export safe.
 */
export function LanguageSwitcher() {
  return (
    <Suspense fallback={<LanguageSwitcherFallback />}>
      <LanguageSwitcherInner />
    </Suspense>
  );
}
