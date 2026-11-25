"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

export const OFFLINE_CACHE_EVENT = "mekongpulse:offline-cache";

/**
 * Registers the PWA service worker and displays a concise offline/cached banner
 * when the device loses connectivity or renders cached offline data.
 */
export function OfflineBanner() {
  const t = useTranslations("Offline");
  const [offline, setOffline] = useState(false);
  const [servingCache, setServingCache] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateOnline = () => {
      const isOff = !window.navigator.onLine;
      setOffline(isOff);
      if (!isOff) setServingCache(false);
    };
    const onOfflineCache = () => {
      setServingCache(true);
    };

    updateOnline();
    window.addEventListener("online", updateOnline);
    window.addEventListener("offline", updateOnline);
    window.addEventListener(OFFLINE_CACHE_EVENT, onOfflineCache);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Non-fatal: app still works without offline caching
      });
    }

    return () => {
      window.removeEventListener("online", updateOnline);
      window.removeEventListener("offline", updateOnline);
      window.removeEventListener(OFFLINE_CACHE_EVENT, onOfflineCache);
    };
  }, []);

  if (!offline && !servingCache) return null;

  return (
    <div className="offline-banner body-small" role="status" aria-live="polite">
      <span className="offline-banner-dot" aria-hidden="true" />
      <span>{offline ? t("offlineNotice") : t("cachedNotice")}</span>
    </div>
  );
}
