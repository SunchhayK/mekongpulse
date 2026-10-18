import { getRequestConfig } from "next-intl/server";
import { routing, type Locale } from "./routing";

// Request-scoped i18n configuration. `setRequestLocale(locale)` is called in
// the [locale] root layout, so this stays compatible with `output: "export"`
// (no middleware / headers, no dynamic rendering).
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: Locale = routing.locales.includes(requested as Locale)
    ? (requested as Locale)
    : routing.defaultLocale;

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
    timeZone: "Asia/Phnom_Penh",
  };
});
