# Benchmarks

Measured on the staging deployment (2026-10-18 UTC). The "before" column is
commit `93f661b` (before the sync cost cuts); "after" is `ad8aec5`.

## Environment

- Host: 12-core Ubuntu laptop server, 7.1 GB RAM, Docker, Postgres 16.15.
- API: FastAPI in Docker on `localhost:8080`, exposed through a Cloudflare tunnel
  at `https://mekongpulse-api.labyrinth.buzz`.
- Dashboard: static Next.js export on Firebase Hosting
  (`https://ai-builder-cup-9f8cd.web.app`).
- External API numbers were taken from macOS over the public URL; localhost
  numbers isolate application cost from the network path.

## Reproduce

```bash
# API latency, payload size, and cold/cached voice assessment
python3 scripts/benchmark_api.py --runs 3 --assess 030101

# On the server: sync wall time, per-table row deltas, host and DB footprint
ssh labyrinth-ts 'cd ~/mekongpulse/projects && set -a && . ./.env.staging && set +a \
  && python3 scripts/benchmark_server.py'
```

Page metrics were captured with a Chrome DevTools performance trace on
`/km/` (desktop, cache disabled). Use the DevTools Performance panel or the
Chrome DevTools MCP `performance_start_trace` tool to reproduce.

## API

| endpoint | before (median) | after (median, 5 runs) | transferred (gzip) | raw |
|---|---:|---:|---:|---:|
| `/health` | 270 ms | 376 ms | 0.1 KiB | 0.1 KiB |
| `/telemetry/latest` | 255 ms | 537 ms | 0.3 KiB | 1.0 KiB |
| `/communes/risk-map` | 462 ms | 443 ms | 52.5 KiB | 523.0 KiB |
| `/communes/030101` | 276 ms | 230 ms | 0.2 KiB | 0.2 KiB |
| `/communes/030101/evidence` | 256 ms | 266 ms | 2.0 KiB | 5.0 KiB |
| `/communes/030101/reports` | 235 ms | 975 ms* | 0.0 KiB | 0.0 KiB |

\* External medians are noisy: the origin is a laptop on Wi-Fi also running
unrelated containers, and the 5-run minimum for `/reports` was 246 ms while the
median was 975 ms. On localhost the same endpoints cost: health **2–4 ms**,
risk-map **25–66 ms**, evidence **7–21 ms** across runs. The risk-map payload is
523 KiB raw and ~50 KiB gzipped.

## Sync and writes

| metric | before | after |
|---|---:|---:|
| Sync wall time | 8.2–9.0 s (one 19.5 s) | **1.65–1.87 s** |
| Risk rows written per sync | 1,544 (every sync) | **0** on unchanged data (writes only changed rows) |
| Weather rows inserted per sync | ~20 (every sync) | 0 within the 60-minute window |
| Syncs per day | 192 (cron called sync + patrol) | **96** |
| Risk writes per day | ~296,000 | ≤148,000 worst case, 0 on steady ticks |
| Weather rows per day | ~3,700 | ~480 (hourly refresh) |
| Observations per day | 768 | 384 |

Steady-state syncs reuse the cached forecast. The first sync after a backend
restart, or after the 60-minute window expires, still fetches Open-Meteo for all
provinces and takes roughly the pre-change 8–9 s; the table's after numbers
describe the 95% of ticks that hit the cache.

The 15-minute cron now calls `/patrol/run` only; patrol performs the sync
first. Unchanged risk rows are skipped by comparing tier, score, reason, lead
time, drivers, station, and estimate (timestamps excluded). Tests:
`shared/tests/test_sync_cost.py`.

## Voice assessment

| path | before | after |
|---|---:|---:|
| First assessment (Gemini TTS synthesis) | 22.3 s | 22.3 s (unchanged; only on a new briefing) |
| Repeat view, same briefing | 1.29 s | **0.55 s** |
| Cold LLM polish (first view after restart, incl. model rotation) | — | 4.45 s |
| Audio URL reuse | shared | shared (`v1-<digest>.mp3`) |

Two caches: the MP3 is content-addressed by the deterministic briefing inputs,
and the polished Khmer text is cached by template digest. Repeat views make no
Gemini calls.

## Dashboard

| metric | value |
|---|---:|
| LCP | 491 ms |
| TTFB | 191 ms |
| Render delay | 300 ms |
| CLS | 0.03 |
| JS (gzip) | ~340 KiB |
| Static export | 2.1 MB |

## Host snapshot (after)

- 12 cores, 7,147 MiB RAM, 97 GB / 500 GB disk.
- Load: 1.59–1.73 (includes unrelated containers).
- `backend` 90 MiB / 0.18% CPU, `db` 57 MiB / 0.00%, `bot` 54 MiB / 0.00%.
- Database: 10 MB total; largest table `communes` 1.6 MB.

## Vertex AI runtime (current, 2026-10-18)

The deployment now runs through Vertex AI (`global`) with the native ReAct advisor engine.

| metric | value |
|---|---:|
| Advisor turn (one tool call) | 11.5 s |
| Khmer STT (≈60 s clip) | 6.3 s |
| New bulletin TTS — Flash-Lite, 58.6 s audio | 35.9 s |
| Repeat assessment, cached audio + polish | 25 ms |
| Audio delivery | `200 audio/mpeg` (469 KiB) |

Model: `gemini-3.8-flash-lite-tts` (cache namespace `v2`). The earlier voice
numbers above were measured on the Gemini API with Flash TTS; Vertex Flash-Lite
costs 33% less on audio output, and its first generation after a restart was
35.9 s versus 74 s for Flash TTS, while warm-path synthesis is similar. Repeats
stay instant because both the MP3 and the polished text are cached.

The cache signature now buckets river level to 0.1 m and 48-hour rain to 5 mm,
and rate to the bulletin's fast/slow/stable wording (namespace `v3`), so a
15-minute telemetry tick no longer forces a new MP3 for a shared link. Shared
commune URLs also carry the selected crop stage.

## Cost implications

- On PostgreSQL these writes are not billed; the savings are CPU, WAL, and
  ingestion time.
- Firestore free tier (Spark): 20k writes / 50k reads per day. The pre-cut
  per-commune model needed ~296k writes and ~296k reads per day; after the cuts
  it is ≤148k writes worst case and ~148k reads (the sync still loads the risk
  map). Firestore Spark still requires the snapshot-document design (one 598 KB
  doc, 1 write per sync) if it is ever used without billing.
- The binding quota is Gemini: bulletin polish is now cached and TTS is
  content-addressed, so repeat demo views consume no model calls.
