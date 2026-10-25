# Estimated implementation cost

| Service | Estimate | Note |
|---|---|---|
| Google Cloud runtime: Cloud Run, Firestore, GCS, Secret Manager, Scheduler | US$20-25 / month | $15 compute, $5 data, under $1 ops |
| Firebase Hosting | US$0 | static export, free tier |
| Vertex text, Gemini 3.8 Flash | under US$0.002 per alert batch | polish and advisor |
| Vertex TTS, Flash-Lite | metered; repeats US$0 | first synthesis only |
| Vertex STT | metered per officer query | audio not persisted |
| MRC, Open-Meteo, Telegram Bot API | US$0 | open data and messaging |
| Current demo | US$0 incremental | self-hosted API with Caddy blue/green |
| Hardware | US$0 capex | no buoys or sensors |

**Coverage:** one hectare of rice saved, about US$500, covers roughly 20 months of fixed infrastructure.

Estimate for the GCP target. The live demo runs self-hosted.

Visual: 8-row service cost table plus a highlight band for coverage. Put target and current demo in separate labels.
