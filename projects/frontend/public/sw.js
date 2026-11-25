/* MekongPulse lightweight PWA service worker.
 *
 * Caching strategy for rural 3G/4G resilience:
 * - App shell & static Next.js chunks: cache-first / network-first navigation fallback
 * - Commune risk, evidence, and assess API responses: network-first with cache fallback
 * - Spoken Khmer MP3 bulletins (/audio/* and GCS/CDN *.mp3): cache-first
 */

const CACHE_VERSION = "v1";
const SHELL_CACHE = `mekongpulse-shell-${CACHE_VERSION}`;
const DATA_CACHE = `mekongpulse-data-${CACHE_VERSION}`;
const AUDIO_CACHE = `mekongpulse-audio-${CACHE_VERSION}`;
const ACTIVE_CACHES = new Set([SHELL_CACHE, DATA_CACHE, AUDIO_CACHE]);

const SHELL_URLS = [
  "/km/",
  "/en/",
  "/km/commune/",
  "/en/commune/",
  "/manifest.webmanifest",
  "/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) =>
        Promise.allSettled(
          SHELL_URLS.map((url) =>
            fetch(url)
              .then((res) => {
                if (res.ok) return cache.put(url, res);
              })
              .catch(() => undefined),
          ),
        ),
      )
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => !ACTIVE_CACHES.has(key)).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isAudioRequest(url) {
  return (
    url.pathname.startsWith("/audio/") ||
    url.pathname.toLowerCase().endsWith(".mp3")
  );
}

function isCacheableGetApi(url) {
  const path = url.pathname;
  return (
    path.startsWith("/api/v1/communes/risk-map") ||
    /^\/api\/v1\/communes\/[^/]+\/(evidence|reports)$/.test(path) ||
    path.startsWith("/api/v1/telemetry/") ||
    path === "/api/v1/health"
  );
}

function isAssessPost(request, url) {
  return (
    request.method === "POST" &&
    /^\/api\/v1\/communes\/[^/]+\/assess$/.test(url.pathname)
  );
}

function withOfflineHeader(response) {
  const headers = new Headers(response.headers);
  headers.set("X-MekongPulse-Offline-Cache", "1");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && (response.ok || response.type === "opaque")) {
    cache.put(request, response.clone()).catch(() => undefined);
  }
  return response;
}

async function networkFirstData(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone()).catch(() => undefined);
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return withOfflineHeader(cached);
    throw err;
  }
}

async function networkFirstAssess(request, url) {
  const cache = await caches.open(DATA_CACHE);
  let stageKey = "default";
  try {
    const cloned = request.clone();
    const body = await cloned.json();
    if (body && typeof body.crop_stage === "string") {
      stageKey = body.crop_stage;
    }
  } catch {
    // ignore body parse errors
  }
  const cacheKey = new Request(
    `${self.location.origin}/__sw_cache__${url.pathname}?stage=${encodeURIComponent(stageKey)}`,
    { method: "GET" },
  );

  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(cacheKey, response.clone()).catch(() => undefined);
    }
    return response;
  } catch (err) {
    const cached = await cache.match(cacheKey);
    if (cached) return withOfflineHeader(cached);
    throw err;
  }
}

async function networkFirstNavigation(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone()).catch(() => undefined);
    }
    return response;
  } catch {
    const exact = await cache.match(request, { ignoreSearch: true });
    if (exact) return exact;
    const url = new URL(request.url);
    if (url.pathname.includes("/commune")) {
      const communeShell =
        (await cache.match("/km/commune/")) || (await cache.match("/en/commune/"));
      if (communeShell) return communeShell;
    }
    return (
      (await cache.match("/km/")) ||
      (await cache.match("/en/")) ||
      new Response("Offline", { status: 503, statusText: "Offline" })
    );
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  if (isAssessPost(request, url)) {
    event.respondWith(networkFirstAssess(request, url));
    return;
  }

  if (request.method !== "GET") return;

  if (isAudioRequest(url)) {
    event.respondWith(cacheFirst(request, AUDIO_CACHE));
    return;
  }

  if (isCacheableGetApi(url)) {
    event.respondWith(networkFirstData(request));
    return;
  }

  if (url.origin === self.location.origin && url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
  }
});
