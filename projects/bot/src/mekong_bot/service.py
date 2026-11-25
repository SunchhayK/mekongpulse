"""MekongPulse bot behaviors (PTB-free and fully testable).

The Telegram layer (handlers.py) only shuttles text between updates and these
methods, so subscription, risk, location, and advisor flows stay pure async
code that tests can drive without any network.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Awaitable, Callable
from uuid import uuid4

from mekong_shared.adk_agent import AdvisorUnavailable, StepLLM, answer
from mekong_shared.adk_tools import TELEGRAM_MESSAGE_LIMIT, AdvisorToolContext, AdvisorTools
from mekong_shared.agronomy import stage_for_planting_date
from mekong_shared.config import Settings
from mekong_shared.models import (
    AgentRunStatus,
    AssessmentResult,
    Commune,
    CropStage,
    CropType,
)
from mekong_shared.pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline
from mekong_shared.repository import Repository
from mekong_shared.spatial import OutsideBasinError
from mekong_shared.watch import run_watch

try:  # concurrent workstream adds these to shared; bot codes to their contract
    from mekong_shared.models import FieldReport, FieldReportStatus
except ImportError:  # ponytail: local stand-ins until shared exports them, then delete

    class FieldReportStatus(StrEnum):
        WATER_REACHED = "water_reached"
        NO_WATER = "no_water"
        OTHER = "other"

    @dataclass
    class FieldReport:
        id: str
        commune_code: str
        status: FieldReportStatus
        reported_at: datetime
        note: str | None = None
        reporter_label: str | None = None
        source: str = "telegram"


log = logging.getLogger("mekongpulse.bot")

WELCOME = (
    "🌊 MekongPulse — ជំនួយការជំនន់ទឹក និងកសិកម្ម\n"
    "Flood warning and crop advisor for the Mekong, Bassac, and Tonle Sap.\n"
    "\n"
    "/subscribe <ឈ្មោះឃុំ ឬកូដ> — តាមដានឃុំមួយ / track a commune\n"
    "/mysubs — បញ្ជីតាមដាន / your subscriptions\n"
    "/risk [ឈ្មោះឃុំ] — កម្រិតហានិភ័យឥឡូវនេះ / current risk + advice\n"
    "/report — រាយការណ៍ទឹកនៅវាលរបស់អ្នក / report water at your fields\n"
    "/digest — របាយការណ៍ប្រចាំថ្ងៃ / daily digest\n"
    "/watch — 🛡 choose a commune / ជ្រើសរើសឃុំ\n"
    "📍 ផ្ញើទីតាំង — send your location to find your commune\n"
    "💬 សួរខ្ញុំជាខ្មែរ ឬអង់គ្លេស — ask the agronomy advisor anything\n"
    "\n"
    "ឧទាហរណ៍ / Example: /subscribe Koh Thom"
)

FIELD_REPORT_CHOICES: tuple[tuple[str, str], ...] = (
    ("water_reached", "💧 ទឹកមកដល់វាលស្រែ / Water reached the fields"),
    ("no_water", "🌾 គ្មានទឹកមកដល់វាល / No water reached"),
    ("other", "❓ ផ្សេងទៀត ឬមិនប្រាកដ / Other or unsure"),
)

DIGEST_UNAVAILABLE = (
    "📰 របាយការណ៍ប្រចាំថ្ងៃមិនទាន់អាចប្រើបានទេ — សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។\n"
    "The daily digest is unavailable right now — please try again later."
)

WATCH_USAGE = (
    "🛡 សូមសរសេរ៖ /watch <ឈ្មោះឃុំ ឬកូដ>\n"
    "Usage: /watch <commune name or code>"
)


@dataclass
class BotReply:
    text: str
    buttons: list[list[tuple[str, str]]] | None = None  # (label, callback_data)
    audio_bytes: bytes | None = None  # Khmer voice bulletin, sent as a Telegram voice note
    edit: bool = False  # replace the originating message instead of sending a new one


class BotService:
    def __init__(
        self,
        settings: Settings,
        pipeline: Pipeline,
        repo: Repository,
        *,
        llm: StepLLM | None = None,
        publisher: Callable[[str], Awaitable[dict]] | None = None,
    ) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.repo = repo
        self.llm = llm  # scripted engine for tests; None = ADK/Gemini in prod
        self.publisher = publisher
        self._tools: AdvisorTools | None = None
        self._watch_lock = asyncio.Lock()

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

    @staticmethod
    def _parse_subscribe_args(raw: str) -> tuple[str, CropType | None, date | None]:
        """Parse `/subscribe <commune> [RICE|VEGETABLES|LIVESTOCK] [YYYY-MM-DD]`."""
        tokens = (raw or "").strip().split()
        crop_type: CropType | None = None
        planting_date: date | None = None
        remaining: list[str] = []
        for token in tokens:
            upper = token.upper()
            if crop_type is None and upper in CropType._value2member_map_:
                crop_type = CropType(upper)
                continue
            if planting_date is None and len(token) == 10 and token[4] == "-" and token[7] == "-":
                try:
                    planting_date = date.fromisoformat(token)
                    continue
                except ValueError:
                    pass
            remaining.append(token)
        return " ".join(remaining).strip(), crop_type, planting_date

    async def subscribe(self, chat_id: str | int, query: str) -> BotReply:
        commune_query, crop_type, planting_date = self._parse_subscribe_args(query)
        if not commune_query:
            return BotReply(
                "សូមសរសេរ: /subscribe <ឈ្មោះឃុំ ឬកូដ> [RICE|VEGETABLES|LIVESTOCK] [YYYY-MM-DD]\n"
                "Usage: /subscribe <commune name or 6-digit code> [crop_type] [planting_date]"
            )
        commune = await self._commune(commune_query) if commune_query.isdigit() else None
        if commune is None:
            hits = self.pipeline.gazetteer.search(commune_query, limit=8)
            if not hits:
                return BotReply(self._not_found(commune_query))
            if len(hits) > 1:
                buttons = [[(self._label(h), f"sub:{h.code}")] for h in hits]
                return BotReply(
                    "ឃើញឃុំច្រើន — សូមជ្រើសរើស / Multiple communes found — pick one:",
                    buttons=buttons,
                )
            commune = hits[0]

        if crop_type in (CropType.VEGETABLES, CropType.LIVESTOCK):
            return await self.subscribe_crop_type(
                chat_id, commune.code, crop_type.value, planting_date=planting_date
            )
        if planting_date is not None:
            inferred_stage = stage_for_planting_date(planting_date)
            return await self.subscribe_stage(
                chat_id,
                commune.code,
                inferred_stage.value,
                crop_type=CropType.RICE,
                planting_date=planting_date,
            )
        return self._stage_prompt(commune)

    def _stage_prompt(self, commune: Commune) -> BotReply:
        buttons = [
            [(f"{stage.label_kh} / {stage.label_en}", f"crop:{commune.code}:{stage.value}")]
            for stage in CropStage
        ]
        return BotReply(
            f"{self._label(commune)}\nជ្រើសដំណាក់កាលស្រូវ / Choose the rice stage:", buttons=buttons
        )

    async def subscribe_stage(
        self,
        chat_id: str | int,
        code: str,
        stage_value: str,
        *,
        crop_type: CropType = CropType.RICE,
        planting_date: date | None = None,
    ) -> BotReply:
        commune = await self._commune(code)
        if commune is None:
            return BotReply(self._not_found(code))
        try:
            stage = CropStage(stage_value)
        except ValueError:
            return BotReply("ដំណាក់កាលមិនត្រឹមត្រូវ / Unknown crop stage.")
        await self.repo.upsert_subscription(
            str(chat_id),
            commune.code,
            stage.value,
            crop_type=crop_type.value,
            planting_date=planting_date,
        )
        planted_line = (
            f"📅 ថ្ងៃដាំ / Planting date: {planting_date.isoformat()}\n" if planting_date else ""
        )
        buttons = [
            [
                (
                    f"🥬 {CropType.VEGETABLES.label_kh} / {CropType.VEGETABLES.label_en}",
                    f"croptype:{commune.code}:{CropType.VEGETABLES.value}",
                ),
                (
                    f"🐄 {CropType.LIVESTOCK.label_kh} / {CropType.LIVESTOCK.label_en}",
                    f"croptype:{commune.code}:{CropType.LIVESTOCK.value}",
                ),
            ]
        ]
        return BotReply(
            f"✅ ចុះឈ្មោះតាមដាន {self._label(commune)}\n"
            f"({stage.label_kh} / {stage.label_en})\n"
            f"{planted_line}"
            "យើងនឹងជូនដំណឹងពេលហានិភ័យកើនឡើង។\n"
            "You will get an alert when the risk for this commune escalates.\n"
            "ពិនិត្យឥឡូវ / check now: /risk",
            buttons=buttons,
        )

    async def subscribe_crop_type(
        self,
        chat_id: str | int,
        code: str,
        crop_type_value: str,
        *,
        planting_date: date | None = None,
        edit: bool = False,
    ) -> BotReply:
        commune = await self._commune(code)
        if commune is None:
            return BotReply(self._not_found(code), edit=edit)
        try:
            crop_type = CropType(crop_type_value.upper())
        except ValueError:
            return BotReply("ប្រភេទដំណាំមិនត្រឹមត្រូវ / Unknown crop type.", edit=edit)
        if crop_type is CropType.RICE:
            return self._stage_prompt(commune)
        await self.repo.upsert_subscription(
            str(chat_id),
            commune.code,
            None,
            crop_type=crop_type.value,
            planting_date=planting_date,
        )
        return BotReply(
            f"✅ ចុះឈ្មោះតាមដាន {self._label(commune)}\n"
            f"({crop_type.label_kh} / {crop_type.label_en})\n"
            "យើងនឹងជូនដំណឹងពេលហានិភ័យកើនឡើង។\n"
            "You will get an alert when the risk for this commune escalates.\n"
            "ពិនិត្យឥឡូវ / check now: /risk",
            edit=edit,
        )

    async def confirm_stage_advance(
        self, chat_id: str | int, code: str, new_stage_value: str
    ) -> BotReply:
        commune = await self._commune(code)
        if commune is None:
            return BotReply(self._not_found(code), edit=True)
        try:
            new_stage = CropStage(new_stage_value)
        except ValueError:
            return BotReply("ដំណាក់កាលមិនត្រឹមត្រូវ / Unknown crop stage.", edit=True)

        existing = next(
            (s for s in await self.repo.subscriptions_for_chat(str(chat_id)) if s.commune_id == commune.code),
            None,
        )
        crop_type = existing.crop_type if existing is not None else CropType.RICE
        planting_date = existing.planting_date if existing is not None else None
        await self.repo.upsert_subscription(
            str(chat_id),
            commune.code,
            new_stage.value,
            crop_type=crop_type.value,
            planting_date=planting_date,
        )
        return BotReply(
            f"✅ បានអាប់ដេតដំណាក់កាលស្រូវសម្រាប់ {self._label(commune)} ទៅជា "
            f"{new_stage.label_kh} ({new_stage.label_en})។\n"
            f"Updated your rice stage for {self._label(commune)} to {new_stage.label_en}.",
            edit=True,
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
            crop_type_val = getattr(sub, "crop_type", CropType.RICE)
            crop_str = getattr(crop_type_val, "value", crop_type_val)
            crop = f" • {crop_str}" if crop_str and crop_str != CropType.RICE.value else ""
            stage = f" • {getattr(sub.crop_stage, 'value', sub.crop_stage)}" if sub.crop_stage else ""
            planted = (
                f" • planted {sub.planting_date.isoformat()}"
                if getattr(sub, "planting_date", None)
                else ""
            )
            last = (
                f" (last alert: {sub.last_notified_risk_tier.value})"
                if sub.last_notified_risk_tier
                else ""
            )
            lines.append(f"• {name}{crop}{stage}{planted}{last} — /risk {sub.commune_id}")
        return BotReply("\n".join(lines))

    async def report(self, chat_id: str | int) -> BotReply:
        subs = await self.repo.subscriptions_for_chat(str(chat_id))
        codes = list(dict.fromkeys(sub.commune_id for sub in subs))[:8]
        if not codes:
            return BotReply(
                "មិនទាន់មានឃុំសម្រាប់រាយការណ៍ទេ — ចាប់ផ្តើមដោយ /subscribe <ឈ្មោះឃុំ> សិន។\n"
                "No communes to report on yet — use /subscribe <commune>, then /report again."
            )
        buttons = []
        for code in codes:
            commune = await self._commune(code)
            buttons.append([(self._label(commune) if commune else code, f"fr:{code}")])
        return BotReply(
            "📍 រាយការណ៍ស្ថានភាពទឹកនៅវាល — សូមជ្រើសរើសឃុំ\n"
            "Report what the water is doing at your fields — pick a commune:",
            buttons=buttons,
        )

    async def digest(self, chat_id: str | int) -> BotReply:
        try:
            # added by a concurrent workstream; import lazily so the bot runs without it
            from mekong_shared.digest import build_digest

            khmer, _english = await build_digest(self.repo, self.settings)
        except Exception:  # noqa: BLE001 - digest is best-effort, never a crash
            log.warning("digest unavailable", exc_info=True)
            return BotReply(DIGEST_UNAVAILABLE)
        return BotReply(khmer)

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

    def _officer_ids(self) -> set[int]:
        raw = self.settings.officer_telegram_ids or ""
        return {int(part.strip()) for part in raw.split(",") if part.strip().isdigit()}

    def _is_officer(self, chat_id: str | int) -> bool:
        try:
            return int(chat_id) in self._officer_ids()
        except (TypeError, ValueError):
            return False

    def _watch_disabled(self) -> str:
        base = (self.settings.web_base_url or "").rstrip("/")
        return (
            "🛡 Telegram approval is not enabled for this chat.\n"
            f"Use the web officer console: {base}/km/assistant\n"
            "Set OFFICER_TELEGRAM_IDS to enable Telegram approval."
        )

    async def watch(
        self, chat_id: str | int, query: str, *, edit: bool = False
    ) -> BotReply:
        """Run a watch pass, or show the top-risk picker when no commune is given."""
        if not self._is_officer(chat_id):
            return BotReply(self._watch_disabled(), edit=edit)

        query = (query or "").strip()
        if not query:
            risks = await self.repo.risk_map()
            if not risks:
                return BotReply(WATCH_USAGE, edit=edit)
            ranked = sorted(
                risks, key=lambda risk: (risk.tier.severity, risk.score), reverse=True
            )[:5]
            buttons = [
                [
                    (
                        f"{risk.tier.emoji} {risk.commune_code} · "
                        f"{(risk.commune_name_en or risk.commune_name_kh or '')[:32]}",
                        f"watch:pick:{risk.commune_code}",
                    )
                ]
                for risk in ranked
            ]
            buttons.append([("🔄 Refresh list", "watch:menu")])
            text = (
                "🛡 ជ្រើសរើសឃុំសម្រាប់ការឃ្លាំមើល (ហានិភ័យខ្ពស់បំផុត):\n"
                "Choose a commune for the watch run (highest current risk):\n\n"
                "ឬផ្ញើ /watch <ឈ្មោះឃុំ>\n"
                "Or send /watch <commune name> — e.g. /watch Batheay"
            )
            return BotReply(text, buttons=buttons, edit=edit)

        commune = await self._commune(query) if query.isdigit() else None
        if commune is None and not query.isdigit():
            hits = self.pipeline.gazetteer.search(query, limit=5)
            if not hits:
                return BotReply(self._not_found(query), edit=edit)
            if len(hits) > 1:
                buttons = [[(self._label(h), f"watch_pick:{h.code}")] for h in hits]
                return BotReply(
                    "🛡 ឃើញឃុំច្រើន — សូមជ្រើសរើសឃុំសម្រាប់ការឃ្លាំមើល\n"
                    "Multiple communes matched — choose one for the watch run:",
                    buttons=buttons,
                    edit=edit,
                )
            commune = hits[0]
        if commune is None:
            return BotReply(self._not_found(query), edit=edit)
        try:
            run = await run_watch(self.pipeline, commune.code, llm=self.llm)
        except (CommuneNotFound, AssessmentUnavailable):
            return BotReply(
                "⚠️ មិនអាចបង្កើតការឃ្លាំមើលសម្រាប់ឃុំនេះបានទេ។\n"
                "A watch run is not available for this commune right now.",
                edit=edit,
            )
        except Exception:  # noqa: BLE001 - the bot must not crash on a provider failure
            log.exception("watch run failed for commune %s", commune.code)
            return BotReply(
                "⚠️ ការឃ្លាំមើលបរាជ័យ — សូមព្យាយាមម្តងទៀត។\n"
                "Watch run failed — please try again.",
                edit=edit,
            )

        text = self._watch_text(run)[:TELEGRAM_MESSAGE_LIMIT]
        return BotReply(
            text,
            buttons=[
                [
                    ("✅ Approve & publish", f"watch:approve:{run.id}"),
                    ("❌ Reject", f"watch:reject:{run.id}"),
                ]
            ],
            edit=edit,
        )

    def _watch_text(self, run) -> str:
        previous = run.previous_tier.value if run.previous_tier else "—"
        return (
            f"🛡 Watch run — {run.commune_name_en or run.commune_name_kh or run.commune_code} "
            f"({run.commune_code})\n"
            f"Tier: {previous} → {run.current_tier.value}\n\n"
            f"{run.rationale}\n\n"
            f"📝 Draft:\n{run.draft_khmer}"
        )

    async def _watch_action(self, chat_id: str | int, action: str, run_id: str) -> BotReply:
        if not self._is_officer(chat_id):
            return BotReply(self._watch_disabled(), edit=True)
        # Serialize approvals so a double tap cannot publish twice.
        async with self._watch_lock:
            return await self._watch_action_locked(chat_id, action, run_id)

    async def _watch_action_locked(
        self, chat_id: str | int, action: str, run_id: str
    ) -> BotReply:
        run = await self.repo.get_agent_run(run_id)
        if run is None:
            return BotReply("Watch run not found.", edit=True)
        if run.status is not AgentRunStatus.PENDING_APPROVAL:
            return BotReply(f"This run is already {run.status.value}.", edit=True)

        now = datetime.now(timezone.utc)
        if action == "reject":
            updated = run.model_copy(
                update={
                    "status": AgentRunStatus.REJECTED,
                    "rejected_at": now,
                    "approved_by": "telegram",
                }
            )
            await self.repo.update_agent_run(updated)
            return BotReply("❌ Watch run rejected. Nothing was published.", edit=True)

        if self.publisher is None:
            return BotReply(
                "⚠️ Publishing is not configured for this bot.\n"
                "Approve from the web officer console instead.",
                edit=True,
            )

        claim_fn = getattr(self.repo, "claim_agent_run_for_publish", None)
        if claim_fn is not None:
            claimed = await claim_fn(run_id)
            if claimed is None:
                latest = await self.repo.get_agent_run(run_id)
                status_label = latest.status.value if latest else "claimed"
                return BotReply(f"This run is already {status_label}.", edit=True)
            run = claimed

        text = run.draft_khmer
        if run.draft_english:
            text = f"{text}\n\n{run.draft_english}"
        text = text[:TELEGRAM_MESSAGE_LIMIT]
        result = await self.publisher(text)
        if not isinstance(result, dict) or result.get("status") == "error" or "error" in result:
            detail = str(
                (result or {}).get("detail")
                or (result or {}).get("error")
                or "Telegram rejected the post"
            )
            failed = run.model_copy(
                update={
                    "status": AgentRunStatus.FAILED,
                    "approved_by": f"telegram:{chat_id}",
                    "error": detail[:500],
                }
            )
            await self.repo.update_agent_run(failed)
            return BotReply(f"❌ Publish failed: {detail}", edit=True)

        updated = run.model_copy(
            update={
                "status": AgentRunStatus.PUBLISHED,
                "approved_at": now,
                "approved_by": "telegram",
                "published_at": now,
                "published_message_id": result.get("message_id"),
                "published_text": text,
                "error": None,
            }
        )
        await self.repo.update_agent_run(updated)
        message_id = updated.published_message_id
        suffix = f" (message #{message_id})" if message_id else ""
        return BotReply(f"✅ Published to the public channel{suffix}.", edit=True)

    async def callback(
        self, chat_id: str | int, data: str, *, reporter: str | None = None
    ) -> BotReply:
        parts = (data or "").split(":")
        if parts[0] == "watch" and len(parts) == 3 and parts[1] in ("approve", "reject"):
            return await self._watch_action(chat_id, parts[1], parts[2])
        if parts[0] == "watch" and len(parts) == 3 and parts[1] == "pick":
            return await self.watch(chat_id, parts[2], edit=True)
        if parts[0] == "watch_pick" and len(parts) == 2:
            return await self.watch(chat_id, parts[1], edit=True)
        if parts[0] == "watch" and len(parts) == 2 and parts[1] == "menu":
            return await self.watch(chat_id, "", edit=True)
        if parts[0] == "sub" and len(parts) == 2:
            commune = await self._commune(parts[1])
            if commune is None:
                return BotReply(self._not_found(parts[1]))
            return self._stage_prompt(commune)
        if parts[0] == "crop" and len(parts) == 3:
            return await self.subscribe_stage(chat_id, parts[1], parts[2])
        if parts[0] == "croptype" and len(parts) == 3:
            return await self.subscribe_crop_type(chat_id, parts[1], parts[2], edit=True)
        if parts[0] == "stage_confirm" and len(parts) == 3:
            return await self.confirm_stage_advance(chat_id, parts[1], parts[2])
        if parts[0] == "risk" and len(parts) == 2:
            return await self._risk_for(chat_id, parts[1])
        if parts[0] == "fr" and len(parts) == 2:
            commune = await self._commune(parts[1])
            if commune is None:
                return BotReply(self._not_found(parts[1]))
            return self._status_prompt(commune)
        if parts[0] == "frr" and len(parts) == 3:
            return await self._file_field_report(parts[1], parts[2], reporter)
        return BotReply("មិនស្គាល់ប៊ូតុងនេះ / Unknown action.")

    # --- internals ---------------------------------------------------------------

    def _status_prompt(self, commune: Commune) -> BotReply:
        buttons = [
            [(label, f"frr:{commune.code}:{value}")] for value, label in FIELD_REPORT_CHOICES
        ]
        return BotReply(
            f"📍 {self._label(commune)}\n"
            "តើទឹកនៅវាលស្រែរបស់អ្នកយ៉ាងណា? / What is the water doing at your fields?",
            buttons=buttons,
            edit=True,
        )

    async def _file_field_report(
        self, code: str, status_value: str, reporter: str | None
    ) -> BotReply:
        commune = await self._commune(code)
        if commune is None:
            return BotReply(self._not_found(code))
        try:
            status = FieldReportStatus(status_value)
        except ValueError:
            return BotReply("ស្ថានភាពទឹកមិនត្រឹមត្រូវ / Unknown water status.")
        await self.repo.add_field_report(
            FieldReport(
                id=uuid4().hex,
                commune_code=commune.code,
                status=status,
                reporter_label=reporter,
                source="telegram",
                reported_at=datetime.now(timezone.utc),
            )
        )
        label = dict(FIELD_REPORT_CHOICES)[status_value]
        return BotReply(
            f"🙏 អរគុណ — បានកត់ត្រារាយការណ៍សម្រាប់ {self._label(commune)}៖\n"
            f"{label}\n"
            "របាយការណ៍របស់អ្នកអាចមើលឃើញដោយមន្ត្រី។\n"
            f"Thanks — your report for {self._label(commune)} is recorded and visible to officials.",
            edit=True,
        )

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
            result = await self.pipeline.assess_commune(code, stage, with_audio=True)
        except (CommuneNotFound, AssessmentUnavailable):
            return BotReply(
                f"⚠️ មិនទាន់អាចវាយតម្លៃឃុំ {code} បានទេ (មិនមានទិន្នន័យស្ថានីយ)\n"
                "No station telemetry for this commune yet — try again after the next sync."
            )
        buttons = None
        if not subscribed:
            buttons = [[("🔔 ចុះឈ្មោះតាមដាន / Subscribe to alerts", f"sub:{code}")]]
        return BotReply(
            self._risk_card(result),
            buttons=buttons,
            audio_bytes=await self._voice_bytes(result),
        )

    async def _voice_bytes(self, result: AssessmentResult) -> bytes | None:
        """Fetch the clip bytes for Telegram; its servers cannot reach dev URLs (localhost)."""
        if result.audio is None or self.pipeline.audio_store is None:
            return None
        try:
            return await self.pipeline.audio_store.get(result.audio.uri)
        except Exception:  # noqa: BLE001 - audio is best-effort; the text card always goes out
            log.warning("voice clip fetch failed; sending text only", exc_info=True)
            return None

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
