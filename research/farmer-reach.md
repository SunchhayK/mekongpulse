# MekongPulse — Farmer reach in Cambodia: channels, competence, training, trust

Researched 2026-10-18. Every URL accessed 2026-10-18. [S#] keys are in the sources table. **Inference:** marks reasoning, not sourced fact. "Not found" means I looked and found no evidence. Cross-references to sibling notes use `research/features-scan.md` §, `research/sellers-market.md` §, `research/gov-workflow.md`.

## Sources

| Key | Source |
| --- | --- |
| S1 | DataReportal, *Digital 2026: Cambodia* (data: late 2025), https://datareportal.com/reports/digital-2026-cambodia |
| S2 | AKP via Ministry of Information, "Cambodian PM's Telegram Channel, the Biggest Channel by Subscribers", 6 Jul 2023, https://www.information.gov.kh/articles/108667 |
| S3 | Telemetr, @spmhunsen channel statistics (accessed 2026-10-18; ~652K subscribers), https://telemetr.io/en/channels/1782078279-spmhunsen |
| S4 | NCDM official Telegram channel @ncdmcambodia (accessed 2026-10-18; ~4.1K subscribers), https://tg.me/ncdmcambodia ; stats https://telemetr.io/en/channels/1370216664-ncdmcambodia |
| S5 | Cambo Agriculture Telegram channel (accessed 2026-10-18; 7.13K subscribers; several Khmer posts/day: ministry notices, job posts, university admissions, agronomy files), https://t.me/s/camboagriculture |
| S6 | Hem, R.; Ty, M.; Yoeu, A.; Vong, R.; Molina Carpio, L.; Hoem, S. (2024), "Unlocking the Digital Potential: Evaluating Smartphone-based Digital Competence among Cambodian Farmers", *IJASR* 7(4):28–40, doi:10.56293/IJASR.2024.6004, https://www.ijasr.org/paper/66742c4a2831d.pdf |
| S7 | AsiaDHRRA SEEDS, train-of-trainers digital literacy workshop with farmers' organizations, Phnom Penh, 24–25 Feb 2025, https://www.asiadhrra.org/asiadhrra/tot-kh-seeds/ |
| S8 | AsiaDHRRA SEEDS, digital literacy and online-marketing trainings for co-op members, Kampong Chhnang and Takeo, June 2025, https://www.asiadhrra.org/asiadhrra/seeds-digital-agri-cambodia/ |
| S9 | Cam Agri Hub — MAFF/IRRI (PCRL) repository of Cambodian digital agriculture tools; app submission route open, https://pcrl.maff.gov.kh/ |
| S10 | IFAD, "IFAD and Grow Asia to support farmers with digital tools to modernize agriculture in Southeast Asia" (SEEDS; IFAD + Korea MAFRA; ~12,000 smallholders across Cambodia, Philippines, Viet Nam), https://www.ifad.org/en/w/news/ifad-and-grow-asia-to-support-farmers-with-digital-tools-to-modernize-agriculture-in-southeast-asia |

## 1. Platform reach: where Cambodians are

- Late 2025: 21.7M mobile connections (121% of population, 94% broadband-capable); 12.0M internet users (67.3%); **32.7% of the population offline**; 14.0M social-media identities (77.9%); **73.4% of the population rural**; median age 26.2 [S1].
- Facebook ad reach 14.0M (77.9% of population; 120% of adults); Messenger 8.90M (49.7% of population; **75.7% of adults**); **TikTok 11.3M adults (97.5% of adults**; 94.5% of internet users); Instagram 1.85M; X 718K; LinkedIn 880K [S1].
- Telegram is **not among the platforms DataReportal covers for Cambodia** [S1]. **Inference:** for population reach, Facebook/Messenger/TikTok are the platforms; Telegram reach cannot be assumed.

## 2. Telegram in Cambodia: a broadcast institution, not a farmer DM channel

- Ministry of Posts and Telecommunications (2023): the PM's Telegram channel was the most-subscribed channel of any world leader [S2]; it still has ~652K subscribers today [S3].
- NCDM runs an official Telegram channel (~4.1K subscribers) alongside its Facebook page [S4].
- Agriculture noticeboards exist and are active: Cambo Agriculture has 7.13K subscribers with several Khmer posts per day (ministry announcements, job ads, admissions, agronomy files) [S5]. The district paddy price bulletin goes out on a Telegram channel with 2,691 subscribers every 1–3 days in harvest (sellers-market.md §4 [S12]). MAFF/PEARL agromet bulletins are distributed via Telegram and Facebook (features-scan.md §1.6). EWS 1294 pushes alerts into Telegram groups (features-scan.md §1.3). 60% of farmers in a Kampong Thom cashew pilot area already used Telegram (features-scan.md §1.5).
- The Ministry of Information reportedly counts Telegram above 10M users (2026) against Facebook's 15.6M (sellers-market.md §4 [S16][S17]). **Inference:** install counts and use patterns differ; the observed Telegram activity is overwhelmingly one-way posting, consistent with an announcement medium rather than messaging at scale.
- **Not found:** any evidence that a farmer-facing Telegram *bot* has meaningful adoption in Cambodia. Khmer Telegram chatbots exist (ChivCheat, Krova — features-scan.md §1.5), but no adoption numbers are published.
- **Inference:** Telegram's real Cambodian fit is **channels**, and its audience skews to the relay layer — officials, agri-sector workers, students, market actors, urban family members. That layer is exactly who forwards warnings onward to farmers.

## 3. The last mile is not an app

- The national alerting path is EWS 1294: registration by dialling, delivery via IVR voice calls, loudspeakers, ABC radio, SMS and Telegram groups, operated by PCDM/NCDM officials; >2M alerts to 125,000+ subscribers by 2022 and ~190,000 registered users with 41 sensors by Jan 2024 (features-scan.md §1.3). The PIN impact assessment records the delivery preferences and comprehension patterns behind this design (gov-workflow.md).
- 99.2% of surveyed farmers owned a smartphone and households averaged ~3 (S6). **Inference:** the constraint is not phones or coverage; it is software competence, literacy and habit. Voice-first, zero-install, relay-mediated delivery is the realistic design.

## 4. Digital competence: the survey evidence

Hem et al. (2024): 400 farmers, gender-balanced, 10 districts in 8 randomly selected provinces, Jan–Feb 2024 [S6].

- Education level is significantly associated with digital competence: using/managing social-media apps (p=0.000), **installing and using other applications such as agri-apps (p=0.000)**, integrating external links (p=0.000), judging fact vs fake (p=0.000). Gender and age group were mostly not significant; respondents over 65 showed the lowest proficiency [S6].
- Only **17 of 400 respondents** answered "yes" to knowing how to install and use other applications (such as agri-apps) on a smartphone [S6, Table 2]. The published table shows duplicated rows for several other questions, so single cells are weak evidence; the direction (very low app-install competence) is still clear.
- The paper's recommendations: government-established systems plus **training of extension officers and farmers**; ICT in primary/secondary curricula [S6]. It also cites a UNDP youth assessment where digital literacy scored 47–51%, with internet safety lowest.

**Inference:** anything requiring an app install, an account, or a text conversation excludes the majority of farmers today. The feasible farmer-adjacent surfaces are (a) voice played by a person or a loudspeaker, (b) familiar feeds (Facebook/Telegram channels) that already carry prices and ministry news, (c) printed or visible artifacts.

## 5. Training models that exist — and who they train

- AsiaDHRRA/CamboDHRRA SEEDS (IFAD + Korea MAFRA): digital literacy and digital marketing workshops delivered to **agricultural cooperatives and farmers' organizations**, not individual farmers — train-of-trainers, Phnom Penh, Feb 2025 [S7]; province trainings in June 2025 with e.g. 22 women farmers from one co-op [S8]. SEEDS covers ~12,000 smallholders across three countries so far [S10].
- [S6] itself recommends extension-officer training as the leverage point.

**Inference:** the established Cambodian pattern trains organizations and relay staff, who then carry tools to their members. A farmer-facing chat tool would require training that no program currently scales to individuals.

## 6. Trust and verification: what the record shows

- EWS 1294's credibility rests on institutional voice (NCDM/PCDM operators) and familiar channels (a phone call, a loudspeaker), not on data display (features-scan.md §1.3; gov-workflow.md).
- MRC publishes an explicit limitations notice on its own data: "the station reading alone cannot tell you whether an area is flooded…", and accuracy decays with forecast distance (features-scan.md §1.2).
- Flood Hub's expert layer exposes a **"verified model" flag** and a lower-confidence coverage toggle — verification state as a first-class UI element (features-scan.md §1.1).
- Farmers act on what reaches familiar feeds: a 2026 Battambang dam-release notice arrived "only a day in advance and farmers found out about it on Facebook" (sellers-market.md §1 [S8]).
- Fact-vs-fake judgement is one of the weakest measured competences and is education-linked [S6].

**Inference:** trust is produced by naming sources and observation times, **showing verification/check state per reading**, admitting limits, and appearing in channels people already use. A risk number with no provenance chain cannot earn trust; one with provenance, checks and honest limits can.

## 7. Implications for MekongPulse (proposal only — nothing here is shipped)

1. **The web is not the farmer's front door either.** Keep the officials' console as decision support; if a public web surface exists, make it a **shareable, Khmer-first, voice-first commune page** that relay people (commune chiefs, co-op staff, extension officers, family members) open and play aloud. Do not assume farmers browse it. [S6][S7][S8]
2. **Telegram = channel first.** Publish forwardable Khmer bulletins (escalation posts plus a digest) with links to commune pages; treat the audience as the relay layer. Reach existing agriculture channels by making posts easy to forward or co-publish rather than building an audience from zero. [S2][S4][S5]
3. **If a bot remains, give it a relay/verification role**: report what is actually happening on the ground ("water reached your fields? yes/no + photo") from named focal points, feeding the console — not farmer Q&A. This closes the model-vs-reality gap with local eyes. [S6; features-scan.md §2 ranked #2]
4. **Build a verification/evidence layer** wherever numbers appear: source and observation time per reading; freshness; deterministic QC on the 30-day station series (gaps, stuck values, spikes, range); cross-source agreement (MRC gauge vs Open-Meteo); an evidence chain from reading → threshold → tier → stage directive; a confidence label per commune; the MRC-style limitations notice; and commune-to-gauge distance. [features-scan.md §1.1–1.2; S6]
5. **Khmer-first i18n** with a proper framework (Khmer default, English secondary) on every web surface. [S1]
6. **Advisor chat: retarget to trained users** (officials, extension officers, co-op staff) or drop it from farmer surfaces entirely. Training at scale targets organizations, not individual farmers. [S6][S7][S8]
7. **Partnerships over new audience-building**: Cam Agri Hub accepts tool submissions (MAFF/IRRI) [S9]; EWS 1294 owns alerting — hand off, do not rebuild (features-scan.md §3).
