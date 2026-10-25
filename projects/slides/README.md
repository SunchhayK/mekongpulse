# AI Builder Cup 2026 slide content

Team ByteLab. Track: Sustainability & Social Impact.

One file per template slide. Copy the title, bullets, and visual note into the deck. The set is 12 content slides. Slide 1 carries the team line, so no separate cover slide is included.

| # | Slide | File | Visual |
|---|---|---|---|
| 1 | Problem statement | `01-problem-statement.md` | 3 stat cards + gap arrow |
| 2 | Brief about the idea | `02-brief-about-the-idea.md` | 4-step strip |
| 3 | Opportunities | `03-opportunities.md` | 3 columns |
| 4 | Features | `04-features.md` | 2x3 feature cards |
| 5 | Process flow | `05-process-flow.md` | Mermaid flow |
| 6 | Wireframes | `06-wireframes.md` | 3-screen block layout |
| 7 | Architecture | `07-architecture.md` | Mermaid architecture |
| 8 | Technologies | `08-technologies.md` | Stack table |
| 9 | Estimated cost | `09-estimated-cost.md` | Service cost table + coverage line |
| 10 | Prototype snapshots | `10-snapshots.md` | 3 screenshots |
| 11 | Benchmarks | `11-benchmarks.md` | Service-path benchmark table |
| 12 | Future development | `12-future-development.md` | 3-column roadmap |

## Assets

- `assets/screenshots/` has three prototype screens: console, officer assistant, Khmer commune page.
- `assets/diagrams/` has rendered PNGs for slides 5 and 7.
- `diagrams/` has the editable Mermaid sources. Paste a `.mmd` file into Mermaid Live or render with `mmdc`.

Slide 9 itemizes Cloud Run, Firestore, GCS, Secret Manager, Scheduler, Firebase Hosting, Vertex text, TTS, and STT. Slide 11 separates service-path latency from application timings and labels the current self-hosted demo against the GCP target.

## Presenter script

See `../demo-script.md` for the 3:40 live demo run of show, pre-warm checklist, and fallbacks.

## Sources

- Product: `../../product-report.md`
- Technical: `../../technical-report.md`
- Research: `../../research/landscape.md`
- Benchmarks: `../BENCHMARKS.md`
- Test counts measured 19 Oct 2026: 155 shared, 89 backend, 44 bot. Total 288.
