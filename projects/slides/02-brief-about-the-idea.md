# Brief about the idea

**MekongPulse: an AI agronomist in every farmer's phone, and a command picture for every commune chief.**

## What it does

1. Ingests 4 MRC river gauges and Open-Meteo rain and soil data every 15 minutes.
2. Scores the 1,544 station-mapped communes out of 1,661 into Normal, Advisory, Warning, or Danger.
3. Combines risk, rice stage, and rain into a field directive.
4. Speaks the directive in Khmer and sends it to Telegram and the web.

## Who it serves

- Commune chiefs and relay people: voice bulletins for loudspeakers and share links.
- Extension officers: evidence, drafts, and channel publish.
- Farmers: clear actions in Khmer, no reading required.

**Agentic layer:** a ReAct (reason and act) officer assistant calls telemetry, evidence, crop directive, draft, and publish tools. A watch agent runs on risk transitions and stops for officer approval.

**Status:** live prototype, 288 passing tests, Firebase web console, self-hosted API.

Visual: four-step strip with icons: ingest, score, advise, speak. Add an agentic-layer callout below it.
