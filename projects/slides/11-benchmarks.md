# Prototype performance report / benchmarking

| Service path                | Measured                      | Note                                           |
| --------------------------- | ----------------------------- | ---------------------------------------------- |
| Firebase Hosting            | TTFB 191 ms; LCP 491 ms       | static export, global CDN                      |
| Public API risk map         | 443 ms public; 25-66 ms local | Public HTTPS ingress, Caddy, FastAPI, Postgres |
| Agentic advisor (Vertex)    | 11.5 s                        | one ReAct tool call                            |
| Agentic watch run (Vertex)  | 17.8 s                        | evidence, draft, 3 tool calls                  |
| Vertex Khmer STT            | 6.3 s                         | 60 s clip                                      |
| Vertex TTS                  | 35.9 s first; 25 ms cached    | content-addressed MP3                          |
| Telegram approve to publish | immediate                     | message_id returned                            |

**Application:** 288/288 tests. 0.8 ms spatial lookup. 0.005 ms agronomy. 1.65-1.87 s sync. 52.5 KiB gzip risk map.

**Scope:** current demo runs FastAPI, Postgres, Caddy, and local audio on a self-hosted host with public HTTPS ingress. Cloud Run, Firestore, GCS, and Secret Manager are the GCP target. Cold start budget under 1.5 s.

Measured on staging and a local benchmark run, 18-19 Oct 2026. Tests: 155 shared, 89 backend, 44 bot. API, sync, voice, and dashboard method: `projects/BENCHMARKS.md`.

Visual: 7-row service table, then two compact lines for app metrics and scope.
