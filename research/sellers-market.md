# MekongPulse — Sellers and buyers: paddy traders, collectors, millers, dryers

Researched 2026-10-18. Every claim carries a source ID [S#]; every URL in Sources was **accessed 2026-10-18**. **Inference:** marks my reasoning, not sourced fact. Where I found no evidence I say "not found" rather than guess.

## 1. Who the sellers are, and how they get information today

- Farmgate sales run farmer → paddy collector/agent → trader or miller. **89% of paddy-selling farmers sell to collectors**, and **46% of collectors are neighbouring lowland-rice farmers** collecting as a seasonal side business [S3]; separately, **>89% of farmers sell to village traders and 60% of communes have no miller** [S9].
- Paddy leaves the farm at **≥24% moisture**, priced on moisture, variety, purity, broken-grain share and "the current state of the market" [S1]. Collectors' and traders' own stated constraints: variable paddy quality, "**limited warehouse capacity that forces compromised marketing decisions**", and limited, costly finance [S1].
- **What exists today**: the CRF / "Cambodia Rice News" **district-level wet paddy price bulletin** — a Khmer table of riel/kg ranges per variety across named districts of Battambang, Pursat, Kampong Thom, Kampong Cham, Takeo and Prey Veng, footnoted "prices above are determined based on quality" and carrying CRF plus government ministry seals [S11][S12, observed 18 Oct 2026]. It is an **image**, pushed to Telegram and Facebook at **1–3 day intervals during harvest** (25, 28, 30 Sep; 2, 5, 7, 14, 16 Oct 2026) [S12].
- **Facebook is where sudden operational news arrives.** This season a Battambang farmer said a dam-release notice reached farmers "only a day in advance and farmers found about it on Facebook" — "If I had received the information a week earlier, I might have been able to harvest some of the rice" [S8]. **Inference:** collectors are both the price-setter's agent and the farmer's main information source, so the gap is structural, not accidental.
- **Not found:** any provincial, MAFF or MOC product that forecasts harvest timing or flood risk *for buyers*. Official outputs are historical (NCDM damage counts) or narrative (§3).

## 2. Early and mid-harvest gluts: what the record shows

- **Timing is the damage multiplier.** The 2011 ADB assessment states the flood "aggravated the negative impact since the **wet season rice was almost at harvesting stage**"; 405,686 ha affected, 232,377 ha damaged, farm-gate paddy valued at USD 305/t against rice export at USD 604/t [S2]. Field work in Sangke, Battambang found 30% of planting area damaged against 11% nationally, complete submergence starting mid-September [S21].
- **2020**: 137,160 ha of rice fields flooded by 17 Oct, 232,551 ha affected by 22 Oct across 19 provinces [S19]. **2026, live now**: floods after an El Niño drought; 72,440 ha affected by 28 Sep and 156,125 ha by 30 Sep, Battambang hardest hit, with MAFF saying food security and exports were not threatened [S8][S13].
- **Wet-paddy price collapse needs no flood.** Nov 2025: paddy fell to **600 riel/kg from 1,150–1,250** a year earlier, traders "reluctant to buy", farmer federation citing missing warehouses and "problematic middlemen" [S7]. Mar 2022 Siem Reap: wet jasmine at **760 riel/kg, down from 800–960**; "we need to harvest and sell immediately to traders. And it is the traders who set prices, leaving farmers no choice" [S10].
- **Why they sell wet and fast**: "farmers often sell rice immediately after harvesting due to insufficient drying, storage, and milling capacity" [S5]; "limited storage capacity between the farm gate and millers forces down prices" [S1].
- **Buyer behaviour in a glut**: the CRF president said millers were "aggressively buying paddy from farmers now to keep demand steady and prevent further price declines", funded by ARDB; contract farming paid cooperatives **1,620/1,580 riel/kg against 1,300 to brokers** [S20]. State credit followed: USD 40m for harvest-period purchase (Nov 2025) [S6] and a USD 200m ARDB facility for mills to "buy and store" paddy (Sep 2026) [S13].
- **Not found:** any source quantifying a *moisture discount* in riel/kg, or measuring dryer-demand spikes during a flood-driven early harvest. The quality-price link is repeatedly asserted [S1][S11] but never quantified. **Inference:** the discount is real, opaque and negotiated, so no dashboard can model it today.

## 3. Market information that already exists: coverage, format, latency, access

| Source | Content | Geography | Cadence / latency | Format, API | Paddy? |
| --- | --- | --- | --- | --- | --- |
| CRF / Cambodia Rice News | Wet paddy riel/kg by district and variety | District | 1–3 days in harvest [S12] | **JPG image**, no API | Yes |
| MAFF AMO / AMIS | ~150 markets, ~250 commodities, collected 3×/week [S15] | Market | 3×/week collection | **amis.org.kh did not resolve 18 Oct 2026** [S15] | Reported, unreachable |
| WFP Price Database via HDX | "Rice (mixed, low quality)" retail + wholesale, KHR/USD | 25 provinces, 86 markets | Monthly (15th); file dated 11 Oct 2026 | **CSV, free CKAN API** | **No — verified 0 paddy rows in 91,682** |
| WFP Cambodia Market & Seasonal Monitoring | Household retail food/fuel/fertilizer; rainfall, soil moisture, river level | 36 markets/10 provinces; national | Monthly PDF [S14] | PDF, no API | No |
| FAO GIEWS Country Brief | Production, export and price narrative | National | Semi-annual (2 Feb 2026) [S6] | HTML | No |
| FAO FPMA | Monthly price trends, sourced from AMO-MAFF AMIS | National | Monthly [S15] | Bulletin | No |
| USDA FAS GAIN | MY production/trade plus harvest windows (wet Aug–Sep short/medium, Oct–Jan long; dry Feb–Apr) | National | 1–2×/yr [S5] | PDF | No |

**Inference (the gap):** seller price information is *current-day, district, image-only and unarchived*; machine-readable information is *milled-rice-only and ~1 month stale*; and **nothing reviewed is forward-looking**. No source joins a harvest window, a crop stage and a flood forecast.

## 4. Is Telegram in documented use among Cambodian traders and farmers?

- Cambodia's Ministry of Information reports **Telegram exceeding 10 million users** (2026) against Facebook's 15.6m [S16]. Telegram has held "most popular messaging app in the country" status since early 2023 and is popular "among businesses and government agencies… Many businesses use Telegram to communicate with customers and employees" [S17]. In agriculture, **60% of farmers in the Kampong Thom pilot area already used Telegram** [S18], and the national EWS pushes to Telegram groups [S22].
- **Directly trader-facing**: the district paddy price bulletin is distributed on a **Telegram channel with 2,691 subscribers**, posted every 1–3 days through the harvest [S12 — observed 18 Oct 2026; official CRF affiliation not verified].
- **Not found:** any named Telegram or WhatsApp *trading* group where Cambodian collectors, traders or millers negotiate volume or price. The evidence supports **one-way broadcast of prices, not two-way trading.** **Inference:** "traders coordinate on Telegram" would overclaim; "prices reach traders on Telegram" is supported.

## 5. A buyer digest: what the engine can produce, and what is genuinely new

The engine already holds commune risk tier (NORMAL → DANGER) from station rise-rate × elevation gazetteer, per-subscriber crop stage, 48h rainfall and soil moisture, with a stated 36–72h lead time [S23]. A digest is a re-render: *which communes have ripening-stage crops inside the risk window, and how many hectares are exposed.*

- **Genuinely new**: forward-looking, commune-level, **stage-aware harvest urgency**. Flood Hub and MRC stop at hazard [S24]; WFP seasonal monitoring is monthly and national [S14]; CRF reports today's price, not tomorrow's risk [S11].
- **Not new**: the price leg (CRF, sub-weekly, district) [S11][S12]; the harvest window (USDA/FAO calendars) [S5][S6]; damage accounting (NCDM, after the fact) [S8][S13]; hazard itself (MRC, Flood Hub) [S24].
- **Inference:** the digest's only defensible content is the intersection — this commune, this week — which is also exactly what is most abusable (§6).

## 6. Risk check: could this harm smallholders?

- The asymmetry is long-documented: "the buyer's side is always in a better position than the seller's side… transactions are conducted with information gap… there is no standard price of transactions and the selling price is decided transaction by transaction" [S3]. The same report records "inaccurate weighing methods… and counting only the number of bags then multiplying by less weight" as **rampant**, with farmers retaliating by concealing high-moisture grain and impurities, after which "buyers lower the unit price" — a self-reinforcing spiral [S3].
- Sellers must sell: "because farmers need cash immediately after the harvest to repay their debts, they **must take the price offered**" [S1]. Absent grading standards, "even wet paddy can attract a price similar to that of dry" [S1]. **Inference:** a wetness discount cannot be assumed to be applied fairly, which undercuts any "buyers will pay more for early dry paddy" pitch.
- **On the record this season:** the Cambodian Farmer Community Federation welcomed the USD 200m mill credit but asked "whether the money will actually benefit farmers or whether most of the benefits will go to large rice mills", and urged inspections of "weighing scales and **moisture measurements at paddy collection points to reduce potential exploitation**", plus prompt payment [S13].
- **Inference:** a forecast of *which commune will be in distress in 48 hours*, given to the already-advantaged side, becomes a **buying-timing advantage at the moment the seller cannot refuse** — the collector arrives before the crest, when the alternative is losing the crop. A public digest does the opposite: it lets the farmer harvest, dry or hold, and lets cooperatives pre-commit. Which effect dominates is not settled in the literature reviewed; it depends on whether the signal is restricted or public. That is a design decision, not a data question.

## Implications for MekongPulse

**Should sellers/traders be a named persona? No.** There is no sourced evidence buyers lack flood-risk information or have asked for it, and the one documented buyer-side need — district paddy prices — is already met every 1–3 days by CRF on Telegram, in the trade's own language and format [S11][S12]. It would also seat PER-002 (smallholder) and its counterparty in one channel, against §6 [S1][S3][S13]. The defensible seller-adjacent audience, if any, is the **contract-farming cooperative and its exporter** (AMRU-style at 1,620/1,580 riel/kg vs 1,300 to brokers [S20]) — but their need is price, not hazard, and they are already served [S22].

**Roadmap feature 1 — justified and cheap: a public "harvest-urgency layer."** Aggregate existing engine output (risk tier × ripening stage × 48h rain/soil moisture) into a commune-level, forward-looking view of where ripening crops sit inside the 36–72h window, published **only** on surfaces that are already public: the broadcast channel and the read-only console [S23]. No new data, no new collection, no new permissions — an aggregation query plus a harvest-season recurring line. It is the one genuinely new signal in §5, and publishing it symmetrically informs farmers, cooperatives and the loudspeaker track at the same instant as any buyer reading the same channel.

**Roadmap feature 2 — not a buyer feed; a pre-commitment nudge.** If anything follows, make it the cooperative case: surface the public digest to agricultural cooperatives and CRF members so purchase commitments are made **before** the crest rather than at the distress price. Cite the contract-farming price evidence [S20], and measure it as hectares pre-committed ahead of a warning — not buyer signups.

**What to avoid.**
- A restricted, paid or "verified buyer" digest, or any output gated away from farmers. Same data, opposite ethics (§6).
- Commune "distress" or "opportunity" rankings, or timing hints ("buy in week 42") — the exploitation vector in [S13] with a forecast attached.
- **Any farmgate paddy price model.** The only free machine-readable series has no paddy rows (verified, 91,682) [S15], the CRF bulletin is image-only and current-day [S11], and ADB found quality-to-price unreliable without grading [S1].
- Scraping or republishing the CRF bulletin [S11][S12]; treating MAFF AMIS as live data (`amis.org.kh` did not resolve) [S15].
- Collecting or exposing buyer/collector contacts in the farmer bot — it would route the documented weighing and moisture practices [S3][S13] to the farmer's weakest moment.
- Claiming "unmet information need among traders" in the pitch. The sourced claim is narrower: **the price is published, the risk is not.**

## Sources (all accessed 2026-10-18)

- [S1] ADB, *Cambodia: Agriculture, Rural Development and Natural Resources Sector Assessment* (2013) — ≥24% MC, price determinants, collector/trader constraints, "must take the price offered", grading gap: https://www.adb.org/sites/default/files/linked-documents/44321-013-cam-ssa.pdf
- [S2] ADB, *Flood Damage Emergency Reconstruction Project — Preliminary Damage and Loss Assessment* (2012) — 2011 flood hit "almost at harvesting stage"; 405,686 ha; USD 305/t farm-gate paddy: https://www.adb.org/sites/default/files/linked-documents/46009-001-cam-oth-01.pdf
- [S3] JICA, *Study on the Improvement of the Marketing System and Post-harvest Quality Control of Rice* — information gap, inaccurate weighing rampant, 89%/46% collector structure: https://openjicareport.jica.go.jp/pdf/11837077_02.pdf
- [S5] USDA FAS GAIN CB2025-0006, *Cambodia: Grain and Feed Update* (17 Dec 2025) — immediate sale due to drying/storage/milling capacity; wet/dry harvest windows: https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Grain%20and%20Feed%20Update_Phnom%20Penh_Cambodia_CB2025-0006
- [S6] FAO GIEWS, *Country Brief — Cambodia* (ref. 2 Feb 2026) — USD 40m harvest-period paddy purchase: https://www.fao.org/giews/countrybrief/country.jsp?code=KHM
- [S7] CamboJA News, 4 Nov 2025 — wet paddy 600 vs 1,150–1,250 riel/kg; traders reluctant to buy: https://cambojanews.com/farmers-struggle-with-falling-rice-price-plea-for-govt-support
- [S8] Cambodianess, 1 Oct 2026 — 72,440 ha affected; "found out on Facebook"; "a week earlier" request: https://cambodianess.com/article/cambodian-farmers-suffer-double-blow-as-floods-follow-drought
- [S9] ADB, *Improving Rice Production and Commercialization in Cambodia* (2014) — 89% sell to village traders; 60% of communes without a miller: https://www.adb.org/sites/default/files/publication/77825/improving-rice-production-cambodia_3.pdf
- [S10] Cambodianess, 6 Mar 2022 — wet jasmine 760 vs 800–960 riel/kg; "it is the traders who set prices": https://cambodianess.com/article/farmers-in-siem-reap-are-concerned-as-traders-prices-for-rice-remain-low
- [S11] CRF, *Wet Paddy Price* bulletin, 5 Oct 2026 — Khmer, district-level, quality footnote: http://www.crf.org.kh/?id=1599&lg=en&page=api_location_detail · image: http://crf.org.kh/public/api_project/crf/article/1599/photo_2026-10-06_11-00-57.jpg
- [S12] Telegram channel "ព័ត៌មានស្រូវអង្ករកម្ពុជា / Cambodia Rice News", 2,691 subscribers; price posts 25/28/30 Sep and 2/5/7/14/16 Oct 2026: https://t.me/s/cambodiaricefederation
- [S13] Cambodianess, 19 Sep 2026 — USD 200m ARDB facility for mills; call to inspect scales and moisture measurement: https://cambodianess.com/article/cambodia-sets-200-million-credit-package-to-help-rice-mills-buy-and-store-paddy · and Cambodianess, 30 Sep 2026 — 156,125 ha damaged: https://cambodianess.com/article/flooding-damages-over-150000-hectares-of-rice-but-food-security-remains-stable
- [S14] WFP, *Cambodia Market & Seasonal Monitoring Update* (Jul 2026); *Seasonal Monitoring in Cambodia* (Aug 2026): https://www.wfp.org/publications/wfp-cambodia-market-seasonal-monitoring-update · https://www.wfp.org/publications/seasonal-monitoring-cambodia
- [S15] WFP Cambodia food prices on HDX — **CSV downloaded and parsed 18 Oct 2026**: 91,682 rows, commodities = milled "Rice (mixed, low quality)" plus non-rice, **zero paddy rows**, 25 provinces / 86 markets, latest 15 Sep 2026: https://data.humdata.org/dataset/wfp-food-prices-for-cambodia · AMIS described at ~150 markets / ~250 commodities / 3× weekly: https://casdp.maff.gov.kh/files/document/262cf85a35a747f024766d26966e1f1d1679296642.pdf (note: **amis.org.kh failed DNS resolution 18 Oct 2026**)
- [S16] Khmer Times, 30 Apr 2026, on the Ministry of Information press-freedom report — Facebook 15.6m, **Telegram >10m users**: https://www.khmertimeskh.com/501889789/social-media-dominates-cambodias-information-landscape-says-report
- [S17] Kiripost, 28 Jun 2023 — Telegram the most popular messaging app; used by businesses and government agencies: https://kiripost.com/stories/rise-of-messaging-app-telegram-in-cambodia
- [S18] CGIAR, 2024 — ChivCheat; 60% of farmers in the Kampong Thom pilot area already used Telegram: https://www.cgiar.org/news-events/news/turning-cashew-dreams-into-reality-chivcheats-ai-chatbot-on-its-way-to-transform-cambodian-agriculture
- [S19] ReliefWeb, *Cambodia: Floods — Oct 2020* — 137,160 ha flooded (17 Oct), 232,551 ha affected (22 Oct), 19 provinces: https://reliefweb.int/disaster/fl-2020-000212-khm
- [S20] Amru Rice news page — contract price 1,620/1,580 vs 1,300 riel/kg to brokers; millers "aggressively buying": https://amrurice.com.kh/page/5?cat=-1
- [S21] Kamoshita & Ouk, 2015, *Field level damage of deepwater rice by the 2011 Southeast Asian Flood* — 30% of Sangke district damaged vs 11% nationally: https://agris.fao.org/search/en/records/65de22e44c5aef494fda2f48
- [S22] Asian Farmers Association, 20 Nov 2025 — FWN collective paddy sales; "the upcoming CRF paddy selling platform": https://asianfarmers.org/cambodia-fwn-strengthening-farmers-incomes-through-collective-paddy-sales
- [S23] MekongPulse internal — commune risk tiers, per-subscriber crop stage, 48h rain, soil moisture, 36–72h lead time: `product-report.md` FR-03 and JRN-04/05/Tier 2–3; `technical-report.md` line 751.
- [S24] Prior MekongPulse research — hazard-only incumbents (MRC, Google Flood Hub): `research/landscape.md` §1.1.
