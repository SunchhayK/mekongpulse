# Technologies to be used in the solution

| Layer      | Stack                                                                                                                                                       |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI         | Gemini 3.8 Flash for bulletin polish and the ReAct advisor. Gemini 3.8 Flash-Lite TTS for Khmer audio. Gemini audio understanding for Khmer speech to text. |
| Resilience | Ordered Gemini fallback: 3.8, 3.7, 3.6, 3.5-lite. Google ADK or native ReAct loop.                                                                          |
| Agentic layer | Google ADK pattern and native ReAct loop. Tools: station telemetry, commune search, crop directive, evidence, voice synthesis, draft, publish. Tool calls are traced. |
| Backend    | Python 3.12, FastAPI, Uvicorn, Pydantic, HTTPX, Shapely STRtree.                                                                                            |
| Data       | PostgreSQL for dev and staging. Firestore for the cloud target. Local disk or GCS for audio.                                                                |
| Frontend   | Next.js 14 static export, React 18, next-intl Khmer-first routing, Leaflet, react-markdown.                                                                 |
| Delivery   | Telegram Bot API, Firebase Hosting, Cloud Run target, Docker Compose with Caddy blue/green.                                              |
| Scheduling | Google Cloud Scheduler target. Host cron in the self-hosted demo.                                                                                           |

**Why this stack:** open telemetry and free weather data keep input cost at zero. Gemini writes the Khmer bulletin, speaks it, transcribes officer questions, and runs the advisor. The risk verdict stays deterministic.

Visual: four columns: AI, backend, data, delivery.
