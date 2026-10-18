import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  // Khmer is the primary audience language; English is the secondary locale.
  locales: ["km", "en"],
  defaultLocale: "km",
});

export type Locale = (typeof routing.locales)[number];
