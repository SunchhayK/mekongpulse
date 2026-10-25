# MekongPulse demo script

**Length:** 3:40. **Hard stop:** 4:00.
**Track:** Sustainability & Social Impact.

## Before you start, not timed

Do these in order. They remove the long waits from the live demo.

1. Open `https://ai-builder-cup-9f8cd.web.app/en/` and click **Refresh**. Confirm the dashboard is populated: a Danger count, **1,544 communes scored**, and four stations. If it shows 0, click Refresh once more and wait 5 seconds.
2. Open `https://ai-builder-cup-9f8cd.web.app/en/commune/?code=030101`. Press **Listen**. Wait until the player shows a duration, for example `0:00 / 1:21`. Pause at 0:00. This caches the Khmer MP3.
3. Open `https://ai-builder-cup-9f8cd.web.app/en/assistant/`. Sign in with the officer passcode. Click **Focus a commune**, enter `030101`, then run **Draft a status update**. Wait for the answer. Expand **Tools used**. Leave the answer on screen. If you do not have the passcode, stay in draft-only mode and do not show publishing.
4. Open **@MekongPulseBot** on the phone. Share a GPS pin in Kampong Cham or Kandal. Pick **Ripening**. Load the voice note. Leave the chat open.
5. Browser zoom 100%. Hide bookmarks. Mute notifications. Close personal tabs.
6. Keep four tabs in this order: dashboard, Batheay, assistant, slide deck. Leave the deck on slide 11 or 12.

The officer session lasts 12 hours. The first TTS can take up to a minute, so never generate audio live during the demo.

## Run of show

Start the timer on your first word.

### 0:00-0:20 | Hook

**Show:** Dashboard, 51 communes in Danger.

**Say:**
"Cambodia's Lower Mekong Basin floods every year. MRC and Google Flood Hub publish river levels in meters. A farmer still does not know what to do in their field. MekongPulse turns those readings into a crop-stage-specific Khmer voice instruction."

### 0:20-0:50 | The basin picture

**Show:** Risk bar and station table.

**Do:** Point at 51 Danger, 159 Advisory, 2 Warning. Point at the four MRC stations.

**Say:**
"Right now the dashboard shows 51 communes in Danger, 159 Advisory, 2 Warning. Four gauges update every 15 minutes. The risk engine maps them to 1,544 communes with elevation and levee margin. The deterministic engine owns the risk verdict. The model does not guess it."

**Do:** Click **Batheay** in Highest risk. This opens the commune page.

### 0:50-1:35 | The last mile

**Show:** Batheay commune page, Danger badge.

**Do:** Press **Listen** and let the Khmer voice note play for 8 to 10 seconds. Pause.

**Say:**
"Batheay is in Danger. The commune chief gets a 30 to 60 second Khmer voice note, the evidence, and the field directive. Listen."

**Say:**
"Same page, four rice stages. Ripening means emergency harvest. Tillering with heavy rain means hold fertilizer. The stage is stored once, so every alert is specific. The link is shareable to Telegram or a loudspeaker."

**Do:** Point at the four stage buttons. Do not switch stages live unless you pre-warmed that audio.

### 1:35-2:05 | Why the warning can be trusted

**Show:** Scroll to **How we know this**.

**Do:** Point at Confidence, the QC checks, the cross-checks, and the evidence chain.

**Say:**
"Every risk row opens to its evidence: station reading, QC, confidence, and field reports. This is how we avoid a black-box warning. The map covers 1,544 communes. Tap a dot for its bulletin. A station click opens the 7-day hydrograph with alarm and flood thresholds."

### 2:05-2:50 | Officer assistant

**Show:** Pre-warmed assistant answer with the draft.

**Do:** Expand **Tools used**. Scroll the bilingual draft. Point at **Post it to the channel**, but do not click it.

**Say:**
"The agentic officer assistant is the human in the loop. I asked it to draft a status update for Batheay. It pulled station evidence and the commune risk, then wrote the bilingual draft. Expand Tools used to see every call. Nothing publishes without an officer."

**Say:**
"This is the split: Gemini writes and explains. The deterministic engine owns the risk. The officer approves the publish."

### 2:50-3:20 | Telegram

**Show:** Phone with @MekongPulseBot.

**Do:** Open the Batheay chat. Play the Khmer voice note for 5 seconds.

**Say:**
"On Telegram, a farmer or commune chief shares a GPS pin. The bot resolves the commune, returns the risk card, and plays the Khmer voice note. One tap stores the rice stage. /report sends ground truth back to the console."

### 3:20-3:40 | Close

**Show:** Slide 11, then slide 12.

**Say:**
"Under the hood: FastAPI, Postgres, Gemini 3.8 Flash, Flash-Lite TTS, Firebase Hosting, Cloud Run target. 288 tests, 0.8 millisecond spatial lookup, 25 millisecond cached audio. The pilot target is 30 communes, 300 stage profiles, 2,500 hectares protected. Forecasters sell meters. MekongPulse sells the next action."

**Do:** End on the live URL and GitHub.

## If something fails

- **Dashboard shows 0 communes:** Click Refresh and wait 5 seconds. If it stays empty, switch to the slide 10 dashboard screenshot and keep talking.
- **Khmer audio is still preparing:** Use the pre-warmed clip. Do not wait. If it still fails, show the Khmer text directives and move on.
- **Assistant is slow:** Use the pre-warmed answer. If the draft is not ready, use the pre-warmed **Summarize current risk** answer and skip the draft line. Never start a live assistant turn during the 4 minutes.
- **Telegram fails:** Skip 2:50-3:20 and replay 5 seconds of the commune voice note. Say the Telegram flow is the same audio and risk card.
- **Stage switch triggers "Preparing...":** Stop. Go back to the default Ripening tab. The stage switch regenerates TTS and can take a minute.

## Do not

- Do not click **Post it to the channel** during the demo.
- Do not switch rice stages live unless that stage was pre-warmed.
- Do not run a live assistant prompt during the 4 minutes.
- Do not read numbers from a stale dashboard. Refresh before you start.

## URLs

- Dashboard: `https://ai-builder-cup-9f8cd.web.app/en/`
- Batheay: `https://ai-builder-cup-9f8cd.web.app/en/commune/?code=030101`
- Khmer Batheay: `https://ai-builder-cup-9f8cd.web.app/km/commune/?code=030101`
- Officer assistant: `https://ai-builder-cup-9f8cd.web.app/en/assistant/`
- Bot: `@MekongPulseBot`
- Repo: `https://github.com/SunchhayK/mekongpulse`
