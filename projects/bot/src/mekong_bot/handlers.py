"""python-telegram-bot wiring: a thin shell over BotService.

Every handler funnels into a BotService method and ships back a BotReply
(text, optional inline buttons, optional audio). No business logic here.
"""

from __future__ import annotations

import logging
from functools import wraps
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .service import BotReply, BotService

log = logging.getLogger("mekongpulse.bot")


def _markup(reply: BotReply) -> InlineKeyboardMarkup | None:
    if not reply.buttons:
        return None
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in reply.buttons
        ]
    )


async def _respond(update: Update, reply: BotReply) -> None:
    chat = update.effective_chat
    text = reply.text[:4096]
    query = update.callback_query
    if reply.edit and query is not None and query.message is not None:
        try:
            await query.edit_message_text(text=text, reply_markup=_markup(reply))
            return
        except Exception as exc:  # noqa: BLE001 - stale callback, fall back to a fresh message
            log.warning("message edit failed, sending a new message: %s", exc)
    if reply.audio_bytes:
        try:
            await chat.send_voice(
                voice=InputFile(BytesIO(reply.audio_bytes), filename="bulletin.mp3"),
                caption=text[:1024],
            )
            return
        except Exception as exc:  # noqa: BLE001 - fall back to text
            log.warning("voice send failed, falling back to text: %s", exc)
    await chat.send_message(text=text, reply_markup=_markup(reply))


def _safe(handler):
    """Handlers never crash the polling loop; users get a short apology."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if update.effective_chat is not None:
                # Assessments synthesize a voice clip server-side; keep the chat lively.
                await update.effective_chat.send_action(ChatAction.TYPING)
            await handler(update, context)
        except Exception:  # noqa: BLE001
            log.exception("telegram handler failure")
            if update.effective_chat is not None:
                try:
                    await update.effective_chat.send_message(
                        "⚠️ មានបញ្ហាបច្ចេកទេស — សូមព្យាយាមម្តងទៀត។\n"
                        "Something went wrong on our side — please try again."
                    )
                except Exception:  # noqa: BLE001
                    pass

    return wrapper


def register_handlers(application: Application, service: BotService) -> None:
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.start(update.effective_chat.id))

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.help(update.effective_chat.id))

    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = " ".join(context.args or [])
        await _respond(update, await service.subscribe(update.effective_chat.id, query))

    async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = " ".join(context.args or [])
        await _respond(update, await service.unsubscribe(update.effective_chat.id, query))

    async def mysubs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.my_subscriptions(update.effective_chat.id))

    async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = " ".join(context.args or [])
        await _respond(update, await service.risk(update.effective_chat.id, query))

    async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.report(update.effective_chat.id))

    async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.digest(update.effective_chat.id))

    async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        location = update.message.location
        await _respond(
            update, await service.location(update.effective_chat.id, location.latitude, location.longitude)
        )

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _respond(update, await service.advisor(update.effective_chat.id, update.message.text))

    async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        user = update.effective_user
        reporter = (user.first_name or user.username) if user else None
        await _respond(
            update,
            await service.callback(update.effective_chat.id, query.data, reporter=reporter),
        )

    application.add_handler(CommandHandler("start", _safe(start)))
    application.add_handler(CommandHandler("help", _safe(help_command)))
    application.add_handler(CommandHandler("subscribe", _safe(subscribe)))
    application.add_handler(CommandHandler("unsubscribe", _safe(unsubscribe)))
    application.add_handler(CommandHandler("mysubs", _safe(mysubs)))
    application.add_handler(CommandHandler("risk", _safe(risk)))
    application.add_handler(CommandHandler("report", _safe(report)))
    application.add_handler(CommandHandler("digest", _safe(digest)))
    application.add_handler(MessageHandler(filters.LOCATION, _safe(on_location)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _safe(on_text)))
    application.add_handler(CallbackQueryHandler(_safe(on_callback)))
