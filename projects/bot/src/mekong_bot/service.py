"""MekongPulse bot behaviors (PTB-free and fully testable).

The Telegram layer (handlers.py) only shuttles text between updates and these
methods, so subscription, risk, location, and advisor flows stay pure async
code that tests can drive without any network.
"""

from __future__ import annotations

from dataclasses import dataclass

from mekong_shared.adk_agent import AdvisorUnavailable, StepLLM, answer
from mekong_shared.adk_tools import AdvisorToolContext, AdvisorTools
from mekong_shared.config import Settings
from mekong_shared.models import AssessmentResult, Commune, CropStage
from mekong_shared.pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline
from mekong_shared.repository import Repository
from mekong_shared.spatial import OutsideBasinError

WELCOME = (
    "🌊 MekongPulse — ជំនួយការជំនន់ទឹក និងកសិកម្ម\n"
    "Flood warning and crop advisor for the Mekong, Bassac, and Tonle Sap.\n"
    "\n"
    "/subscribe <ឈ្មោះឃុំ ឬកូដ> — តាមដានឃុំមួយ / track a commune\n"
    "/mysubs — បញ្ជីតាមដាន / your subscriptions\n"
    "/risk [ឈ្មោះឃុំ] — កម្រិតហានិភ័យឥឡូវនេះ / current risk + advice\n"
    "📍 ផ្ញើទីតាំង — send your location to find your commune\n"
    "💬 សួរខ្ញុំជាខ្មែរ ឬអង់គ្លេស — ask the agronomy advisor anything\n"
    "\n"
    "ឧទាហរណ៍ / Example: /subscribe Koh Thom"
)


@dataclass
class BotReply:
    text: str
    buttons: list[list[tuple[str, str]]] | None = None  # (label, callback_data)
    audio_url: str | None = None


class BotService:
    def __init__(
        self,
        settings: Settings,
        pipeline: Pipeline,
        repo: Repository,
        *,
        llm: StepLLM | None = None,
    ) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.repo = repo
        self.llm = llm  # scripted engine for tests; None = ADK/Gemini in prod
        self._tools: AdvisorTools | None = None

    @property
    def tools(self) -> AdvisorTools:
        if self._tools is None:
            self._tools = AdvisorTools(AdvisorToolContext(self.pipeline))
        return self._tools

    # --- commands --------------------------------------------------------------

    async def start(self, chat_id: str | int) -> BotReply:
        return BotReply(WELCOME)

    async def help(self, chat_id: str | int) -> BotReply:
        return BotReply(WELCOME)

    async def subscribe(self, chat_id: str | int, query: str) -> BotReply:
        query = (query or "").strip()
        if not query:
            return BotReply(
                "សូមសរសេរ: /subscribe <ឈ្មោះឃុំ ឬកូដ>\n"
                "Usage: /subscribe <commune name or 6-digit code>"
            )
        commune = await self._commune(query) if query.isdigit() else None
        if commune is not None:
            return self._stage_prompt(commune)
        hits = self.pipeline.gazetteer.search(query, limit=8)
        if not hits:
            return BotReply(self._not_found(query))
        if len(hits) == 1:
            return self._stage_prompt(hits[0])
        buttons = [[(self._label(h), f"sub:{h.code}")] for h in hits]
        return BotReply("ឃើញឃុំច្រើន — សូមជ្រើសរើស / Multiple communes found — pick one:", buttons=buttons)

    def _stage_prompt(self, commune: Commune) -> BotReply:
        buttons = [
            [(f"{stage.label_kh} / {stage.label_en}", f"crop:{commune.code}:{stage.value}")]
            for stage in CropStage
        ]
        return BotReply(
            f"{self._label(commune)}\nជ្រើសដំណាក់កាលស្រូវ / Choose the rice stage:", buttons=buttons
        )

    async def subscribe_stage(self, chat_id: str | int, code: str, stage_value: str) -> BotReply:
        commune = await self._commune(code)
        if commune is None:
            return BotReply(self._not_found(code))
        try:
            stage = CropStage(stage_value)
        except ValueError:
            return BotReply("ដំណាក់កាលមិនត្រឹមត្រូវ / Unknown crop stage.")
        await self.repo.upsert_subscription(str(chat_id), commune.code, stage.value)
        return BotReply(
            f"✅ ចុះឈ្មោះតាមដាន {self._label(commune)}\n"
            f"({stage.label_kh} / {stage.label_en})\n"
            "យើងនឹងជូនដំណឹងពេលហានិភ័យកើនឡើង។\n"
            "You will get an alert when the risk for this commune escalates.\n"
            "ពិនិត្យឥឡូវ / check now: /risk"
        )

    async def unsubscribe(self, chat_id: str | int, query: str) -> BotReply:
        query = (query or "").strip()
        if not query:
            return BotReply("សូមសរសេរ: /unsubscribe <ឈ្មោះឃុំ ឬកូដ>")
        commune = await self._commune(query) if query.isdigit() else None
        if commune is None:
            hits = self.pipeline.gazetteer.search(query, limit=1)
            commune = hits[0] if hits else None
        if commune is None:
            return BotReply(self._not_found(query))
        removed = await self.repo.remove_subscription(str(chat_id), commune.code)
        if not removed:
            return BotReply(
                f"មិនបានចុះឈ្មោះតាមដាន {self._label(commune)} ទេ។\n"
                f"Not subscribed to {self._label(commune)}."
            )
        return BotReply(
            f"🔕 បានបញ្ចប់ការតាមដាន {self._label(commune)}\n"
            f"Unsubscribed from {self._label(commune)}."
        )

    async def my_subscriptions(self, chat_id: str | int) -> BotReply:
        subs = await self.repo.subscriptions_for_chat(str(chat_id))
        if not subs:
            return BotReply(
                "មិនទាន់មានការតាមដានទេ។ /subscribe <ឈ្មោះឃុំ> ដើម្បីចាប់ផ្តើម។\n"
                "No subscriptions yet — use /subscribe <commune>."
            )
        lines = ["📋 ការតាមដានរបស់អ្នក / Your subscriptions:"]
        for sub in subs:
            commune = await self._commune(sub.commune_id)
            name = self._label(commune) if commune else sub.commune_id
            stage = f" • {sub.crop_stage.value}" if sub.crop_stage else ""
            last = (
                f" (last alert: {sub.last_notified_risk_tier.value})"
                if sub.last_notified_risk_tier
                else ""
            )
            lines.append(f"• {name}{stage}{last} — /risk {sub.commune_id}")
        return BotReply("\n".join(lines))

    async def risk(self, chat_id: str | int, query: str = "") -> BotReply:
        query = (query or "").strip()
        if query:
            commune = await self._commune(query) if query.isdigit() else None
            if commune is None:
                hits = self.pipeline.gazetteer.search(query, limit=1)
                commune = hits[0] if hits else None
            if commune is None:
                return BotReply(self._not_found(query))
            return await self._risk_for(chat_id, commune.code)
        subs = await self.repo.subscriptions_for_chat(str(chat_id))
        if not subs:
            return BotReply(
                "មិនទាន់មានការតាមដានទេ — សាក /risk <ឈ្មោះឃុំ> ឬ /subscribe។\n"
                "No subscriptions yet — try /risk <commune> or /subscribe."
            )
        cards = []
        for sub in subs:
            reply = await self._risk_for(chat_id, sub.commune_id)
            cards.append(reply.text)
        return BotReply("\n\n".join(cards))

    async def location(self, chat_id: str | int, lat: float, lng: float) -> BotReply:
        try:
            resolved = self.pipeline.gazetteer.resolve(lat, lng)
        except OutsideBasinError:
            return BotReply(
                "📍 ទីតាំងនេះនៅក្រៅអាងទន្លេមេគង្គកម្ពុជា។ សូមផ្ញើទីតាំងក្នុងប្រទេសកម្ពុជា។\n"
                "That location is outside the monitored Cambodian basin."
            )
        reply = await self._risk_for(chat_id, resolved.commune.code)
        header = f"📍 {self._label(resolved.commune)} (via {resolved.method})"
        return BotReply(f"{header}\n\n{reply.text}", buttons=reply.buttons)

    async def advisor(self, chat_id: str | int, text: str) -> BotReply:
        text = (text or "").strip()
        if not text:
            return BotReply("សូមសរសេរសំណួរ / Please type a question.")
        history = await self.repo.recent_turns(str(chat_id), limit=12)
        try:
            reply_text = await answer(self.tools, history, text, self.settings, llm=self.llm)
        except AdvisorUnavailable:
            return BotReply(
                "🤖 មិនអាចភ្ជាប់ AI advisor បានទេ (ត្រូវការ GEMINI_API_KEY)។\n"
                "សាកប្រើ /risk សម្រាប់ទិន្នន័យផ្ទាល់។\n"
                "The advisor needs a Gemini key; use /risk for live risk and directives meanwhile."
            )
        if not reply_text.strip():
            reply_text = "សូមសួរឡើងវិញ / I could not produce an answer; please rephrase."
        await self.repo.append_turn(str(chat_id), "user", text)
        await self.repo.append_turn(str(chat_id), "assistant", reply_text)
        return BotReply(reply_text)

    async def callback(self, chat_id: str | int, data: str) -> BotReply:
        parts = (data or "").split(":")
        if parts[0] == "sub" and len(parts) == 2:
            commune = await self._commune(parts[1])
            if commune is None:
                return BotReply(self._not_found(parts[1]))
            return self._stage_prompt(commune)
        if parts[0] == "crop" and len(parts) == 3:
            return await self.subscribe_stage(chat_id, parts[1], parts[2])
        if parts[0] == "risk" and len(parts) == 2:
            return await self._risk_for(chat_id, parts[1])
        return BotReply("មិនស្គាល់ប៊ូតុងនេះ / Unknown action.")

    # --- internals ---------------------------------------------------------------

    async def _risk_for(self, chat_id: str | int, code: str) -> BotReply:
        subs = await self.repo.subscriptions_for_chat(str(chat_id))
        stage = CropStage.RIPENING
        subscribed = False
        for sub in subs:
            if sub.commune_id == code:
                subscribed = True
                if sub.crop_stage:
                    stage = sub.crop_stage
        try:
            result = await self.pipeline.assess_commune(code, stage)
        except (CommuneNotFound, AssessmentUnavailable):
            return BotReply(
                f"⚠️ មិនទាន់អាចវាយតម្លៃឃុំ {code} បានទេ (មិនមានទិន្នន័យស្ថានីយ)\n"
                "No station telemetry for this commune yet — try again after the next sync."
            )
        buttons = None
        if not subscribed:
            buttons = [[("🔔 ចុះឈ្មោះតាមដាន / Subscribe to alerts", f"sub:{code}")]]
        return BotReply(self._risk_card(result), buttons=buttons)

    async def _commune(self, code: str) -> Commune | None:
        return self.pipeline.gazetteer.get(code) or await self.repo.get_commune(code)

    @staticmethod
    def _label(commune: Commune) -> str:
        province = f" · {commune.province_en}" if commune.province_en else ""
        return f"{commune.name_kh} ({commune.name_en}{province})"

    @staticmethod
    def _not_found(query: str) -> str:
        return (
            f"រកមិនឃើញ «{query}» — សាកឈ្មោះខ្មែរ ឬអង់គ្លេស ឬកូដឃុំ (ឧ. 080404)។\n"
            f"Could not find “{query}”. Try a Khmer/English name or a 6-digit code."
        )

    @staticmethod
    def _risk_card(result: AssessmentResult) -> str:
        tier = result.risk_tier
        lines = [
            f"{tier.emoji} {tier.label_kh} / {tier.label_en} — "
            f"{result.commune_name_kh} ({result.commune_name_en})"
        ]
        if result.lead_time_hours is not None:
            lines.append(
                f"⏱ ប្រហែល {result.lead_time_hours} ម៉ោងទៀត / ~{result.lead_time_hours}h until flooding"
            )
        if result.estimated:
            lines.append("⚠️ ទិន្នន័យប៉ាន់ស្មាន / estimated telemetry — act conservatively")
        for directive in result.directives[:3]:
            lines.append(f"• {directive.title_kh}: {directive.instruction_kh}")
        if result.directives:
            primary = result.directives[0]
            lines.append(f"EN: {primary.title_en} — {primary.instruction_en}")
        return "\n".join(lines)
