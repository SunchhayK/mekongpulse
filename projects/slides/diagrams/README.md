# Diagrams

Two editable Mermaid sources:

- `05-process-flow.mmd`: data ingest, risk scoring, agronomy, voice, delivery, and the officer approval loop.
- `07-architecture.mmd`: sources, runtime, Google AI, data stores, and client surfaces.

Render with Mermaid Live (https://mermaid.live) or the Mermaid CLI:

```bash
npx @mermaid-js/mermaid-cli -i 05-process-flow.mmd -o ../assets/diagrams/05-process-flow.png -w 2400
npx @mermaid-js/mermaid-cli -i 07-architecture.mmd -o ../assets/diagrams/07-architecture.png -w 2000
```

The PNGs in `../assets/diagrams/` are reference renders for the slide files.
