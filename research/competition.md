# Google Cloud AI Builder Cup 2026 — competition research

All sources accessed 18 Oct 2026. "Official" = Hack2skill-run microsite or its linked Terms; anything else is labelled secondary.

## What it is

- **Name:** Google Cloud AI Builder Cup (2026 edition), powered by Hack2skill. Microsite footer credits "Gen AI Academy APAC Edition" — a related Google Cloud + Hack2skill program. No evidence of any earlier AI Builder Cup edition (domain `aibuildercup.com` first archived 6 Oct 2026; no 2025 winners exist). Treat 2026 as edition one. [S1][S3]
- **Organizer:** Hack2skill. Official disclaimer: the program is "organized by Hack2skill and sponsored by Google Cloud… independently operated by Hack2skill and is not directly administered by Google Cloud." Google Cloud supplies "technical expertise access, and educational resources." [S1]
- **Region:** JAPAC (Japan + Asia-Pacific), a single regional pool. Cambodia teams compete regionally; no Cambodia-specific or GDG-Cambodia edition/page found. [S1]
- **Eligibility:** 21+; working professionals, entrepreneurs, startups only; students strictly ineligible (one student disqualifies the whole team, even after the finale); all members must be JAPAC residents; cross-country JAPAC teams allowed; teams of 2–4 (register solo, form team later); one theme/one submission per person/team; only 2 members per team travel to Singapore. [S1][S2]
- **Timeline (2026):** Registration 1 Sep – 11 Oct; team formation to 14 Oct; build 7 Sep – 18 Oct; **submission deadline 18 Oct 2026** (timezone not stated on site); evaluation 19 Oct – 6 Nov; finalists announced 7 Nov; in-person Grand Finale (Demo Day) in Singapore 4 Dec 2026. Registration is now closed per the microsite ticker. [S1][S3]
- **Prizes:** USD 30,000 total — Winner $10,000; 1st runner-up $7,000; 2nd runner-up $5,000; plus four $2,000 awards: Best Use of Google Cloud AI Tools, Most Impactful Solution, Social Choice, Best UI/UX. Finalists get sponsored flights, accommodation and event-day meals (visas are the team's own responsibility); only 2 members may attend. Cash pays within 60 days of the event. Free entry. [S1][S2]
- **IP:** Terms grant the Organizer a 6-month right of first refusal on an exclusive licence to all submitted materials, and a worldwide licence to publicise submissions. Relevant to any post-hackathon commercialisation plan for MekongPulse. [S2]

## Themes

Six themes; same judging rubric for all; pick exactly one. [S1]

1. BFSI: Intelligent Risk, Fraud & Financial Experiences
2. Retail & Commerce: Intelligent Customer and Business Experiences
3. Manufacturing: Intelligent Operations & Industrial Efficiency
4. Media, Content & Digital Experiences
5. Future of Work & Enterprise Productivity
6. **Sustainability & Social Impact** — official definition: "an AI-powered solution that addresses a meaningful environmental or societal challenge. Solutions may focus on improving resource efficiency, increasing accessibility, strengthening resilience, supporting communities, or enabling more informed and sustainable decision-making." Flood early warning + agronomic advisory maps to "strengthening resilience" and "supporting communities". [S1]

- Legacy copy on the same page also lists "(Healthcare, Education, Sustainability, Accessibility, Social Good)" as categories — inconsistent with the six themes; residual wording from earlier Google Cloud/Hack2skill programs. Use "Sustainability & Social Impact" as the theme label. [S1]
- No per-theme sub-problem-statement PDF was found on the microsite; the six theme descriptions are the published problem statements. An official session explains them: "AI Builder Cup | Introductory & Problem Statement Explainer Session" (Hack2skill YouTube). [S1][S4]

## Judging

Weights match across the microsite and the Terms: [S1][S2]

- **Technical Merit & Gen AI Implementation — 40%.** Meaningful GenAI use that *directly* contributes to solving the problem; functional, technically sound implementation; scalability/sustainability beyond the prototype.
- **Problem Alignment & Impact — 25%.** Fit to the chosen theme; "clear and meaningful value for its intended users, organization, industry, community, or other relevant stakeholders."
- **Innovation & Creativity — 25%.** Originality/differentiation; creative GenAI use "beyond a basic or superficial implementation".
- **User Experience & Solution Design — 10%.** Usability/accessibility for intended users; cohesive integration of components including GenAI.

Process: a first scoring round (19 Oct – 6 Nov) shortlists finalists; shortlisted teams demo live in Singapore before a panel "of Google Cloud & industry experts"; judges to be announced closer to the finale. [S1]

## Submission requirements

Mandatory artefacts: [S1][S2]

- **Working deployed live URL** on Cloud Run / GCP / Firebase. Solutions built primarily on other clouds are ineligible.
- **Video demo.** Conflict in official docs: FAQs and themes page say 3 minutes / "under 3 minutes"; the Terms say "strictly three to four minutes". Safest is ≤3:00. Host on YouTube, Vimeo or public Drive link.
- **Public GitHub repository.** Fresh code only — "pre-existing projects, or work started before the program launch, will not be considered."
- **Deck (PDF)** explaining problem, impact, feasibility and scalability.
- **Language:** all materials (code, docs, deck) in English.
- **AI requirement:** must use Google AI models (Gemini or Gemma family) or be built on agentic platforms (Agent Platform, Antigravity, AI Studio).
- A working end-to-end prototype is enough — no need for a full product.

## Winners/patterns

- **No AI Builder Cup winners or finalists exist yet.** Shortlist is due 7 Nov 2026 and the finale 4 Dec 2026 — both after today. No prior-edition winners either. [S1]
- Related-program proxy only: the Google Cloud Gen AI Exchange Hackathon (India; second edition concluded Dec 2025, run by Google Cloud with Hack2skill) produced 10 winning teams across student/professional tracks, described in press coverage as demonstrating "real-world, scalable impact" (secondary; article body did not render for me). The Gen AI Academy APAC Edition 2026 (Google Cloud + Hack2skill) is the umbrella learning program this Cup sits alongside. [S5][S6]
- **Unverified local claims:** `aibuildercupdocs/01_COMPETITION_AND_JUDGE_GUIDE.md` names past "Grand Champions (Padayon Ko)" and runners-up (Savour, BaldMann) plus a "$350k Google for Startups credits" prize. No primary or secondary source corroborates this. Its rubric (40/25/25/10) does match the official text; its extras (Discord activity tracking, roster-lock mechanics) look like extrapolation. Do not build strategy on these. [S7]
- Contestable patterns from the official text itself (not inferred): impact counts 25% and rewards "clear and meaningful value for intended users"; GenAI must be load-bearing (40%); scalability is explicitly scored; accessibility/usability is scored; the tagline is "Build in JAPAC. Build for the world" — i.e. local-difficulty → regional/gLOBAL scale is the intended narrative. [S1]

## Implications for MekongPulse

- **Theme:** submit under Sustainability & Social Impact; mirror its wording (resilience, communities, informed and sustainable decisions) in the deck.
- **Score planning:** GenAI technical execution is the single biggest block (40%) — show a multi-agent pipeline where Gemini does real work (Khmer voice-note generation, risk summarisation), not a chat wrapper; deploy on Cloud Run; document architecture.
- **Impact (25%):** name beneficiaries precisely (commune disaster committees, farmers) and quantify (people reached, warning lead time, value protected). "Measurable real-world viability" is the scored phrase.
- **Innovation (25%):** differentiate from Google Flood Hub — forecasting already exists; the novelty is last-mile delivery in Khmer via Telegram voice + commune-level routing. Architectural/UX novelty scores; "using an LLM" does not.
- **UX (10%):** playable Khmer voice note and fast-loading dashboard in the demo; the prototype must work end-to-end live.
- **Category-prize targets:** Most Impactful Solution ($2k), Best Use of Google Cloud AI Tools ($2k), Social Choice (public vote).
- **Hard constraints to respect now:** deadline today (18 Oct); registration closed 11 Oct — confirm the team is actually registered; publish a public GitHub repo whose history reads as fresh in-window code; English-only deck/video/code comments; keep the video ≤3:00 given the doc conflict; no third-party cloud in the shown path (Cloud Run + Firebase only); only 2 members can travel if shortlisted.
- **IP caution:** the 6-month right of first refusal on an exclusive licence applies to everything submitted. [S2]

## Sources

- [S1] Official microsite (Hack2skill), accessed 18 Oct 2026: https://aibuildercup.com/ (overview, timeline, disclaimer); https://aibuildercup.com/themes.html (themes, build rules, submission, partial judging); https://aibuildercup.com/rewards.html (prizes); https://aibuildercup.com/Faqs.html (eligibility, team size, submission format, travel, judging-process answers).
- [S2] Official Terms & Conditions, "Terms and Conditions - AI Builder Cup JAPAC" (published Google Doc linked from microsite), accessed 18 Oct 2026: https://docs.google.com/document/d/e/2PACX-1vRm7ChZ6Ij9fG7uFDkxzUMpwgVeBmnQ6cMDnAIEEX84AiLBOOQ9cYbl3S5OzFBbcVb8TF55s-eVpiXb/pub
- [S3] Wayback Machine captures of the microsite, 6 Oct 2026 (registration-open snapshot; earliest capture of the domain), accessed 18 Oct 2026: https://web.archive.org/web/20261006023541/https://aibuildercup.com/
- [S4] Hack2skill YouTube channel — "AI Builder Cup | Introductory & Problem Statement Explainer Session", identified via oEmbed (video page returned HTTP 429 on fetch), accessed 18 Oct 2026: https://www.youtube.com/watch?v=mhDd6qSBMg4
- [S5] Gen AI Academy APAC Edition 2026 event page (Hack2skill), referenced in community posts; page did not render directly for me, accessed 18 Oct 2026: https://hack2skill.com/event/apac-genaiacademy
- [S6] Secondary news: YourStory, "Google Cloud Gen AI Exchange Hackathon: The 10 innovations that stood out this year" (Dec 2025/Jan 2026) — headline/summary only, body did not render, accessed 18 Oct 2026: https://yourstory.com/2025/12/google-cloud-gen-ai-exchange-hackathon-the-10-innovations-that-stood-out-this-year
- [S7] Secondary listing: Metropolis Japan, "AI Builder Cup 2026" — corroborates six themes and JAPAC framing, accessed 18 Oct 2026: https://metropolisjapan.com/events/ai-builder-cup-2026/
- Local context (not an official source; claims flagged above): `/Users/ruined/Home/Projects/AiBuilderCup/aibuilderdocs/01_COMPETITION_AND_JUDGE_GUIDE.md`, `/Users/ruined/Home/Projects/AiBuilderCup/handoff_bytelab_ai_builder_cup.md`.
