"""Telegram dispatcher: subscriber fan-out, audio paths, failure isolation."""

from __future__ import annotations

from datetime import datetime, timezone

from mekong_shared.models import RiskTier, SentinelAlert, Subscription

from mekong_bot.dispatcher import make_telegram_dispatcher


class FakeBot:
    def __init__(self, raise_for: set[str] | None = None) -> None:
        self.messages: list[tuple[object, str]] = []
        self.voices: list[tuple[object, object, str | None]] = []
        self._raise_for = raise_for or set()

    async def send_message(self, chat_id, text, **kwargs) -> None:
        if str(chat_id) in self._raise_for:
            raise RuntimeError("chat blocked the bot")
        self.messages.append((chat_id, text))

    async def send_voice(self, chat_id, voice, caption=None, **kwargs) -> None:
        if str(chat_id) in self._raise_for:
            raise RuntimeError("chat blocked the bot")
        self.voices.append((chat_id, voice, caption))


def _alert(**overrides) -> SentinelAlert:
    base = dict(
        commune_id="030502",
        risk_tier=RiskTier.WARNING,
        directive_title="Emergency harvest acceleration",
        bulletin_text="សារព្រមានទឹកជំនន់ពី MekongPulse\n" + ("ព្រមាន! " * 700),
        dispatched_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return SentinelAlert(**base)


def _subs() -> list[Subscription]:
    return [
        Subscription(telegram_chat_id="111", commune_id="030502"),
        Subscription(telegram_chat_id="222", commune_id="030502"),
    ]


async def test_dispatch_text_to_subscribers_and_channel(pipeline, settings):
    pipeline.settings = settings.model_copy(update={"telegram_broadcast_channel_id": "-100999"})
    bot = FakeBot()
    dispatch = make_telegram_dispatcher(pipeline, bot)

    delivered = await dispatch(_alert(), _subs())

    assert delivered == 2
    chat_ids = [chat for chat, _ in bot.messages]
    assert chat_ids == [111, 222, -100999]  # subscribers int-coerced, then channel
    texts = [text for _, text in bot.messages]
    assert all(len(text) <= 4096 for text in texts)
    assert all("សារព្រមាន" in text for text in texts)


async def test_dispatch_uses_public_https_audio_url(pipeline):
    bot = FakeBot()
    dispatch = make_telegram_dispatcher(pipeline, bot)
    url = "https://storage.googleapis.com/bucket/030502/warning_1.mp3"

    delivered = await dispatch(_alert(audio_url=url), _subs()[:1])

    assert delivered == 1
    assert bot.messages == []
    (chat_id, voice, caption) = bot.voices[0]
    assert chat_id == 111 and voice == url
    assert caption is not None and len(caption) <= 1024


async def test_dispatch_local_audio_reads_from_store(pipeline, settings):
    (settings.audio_dir / "030502").mkdir(parents=True, exist_ok=True)
    (settings.audio_dir / "030502" / "warning_1.mp3").write_bytes(b"MP3DATA")
    bot = FakeBot()
    dispatch = make_telegram_dispatcher(pipeline, bot)

    delivered = await dispatch(
        _alert(audio_url="http://localhost:8080/audio/030502/warning_1.mp3"), _subs()[:1]
    )

    assert delivered == 1
    voice = bot.voices[0][1]
    assert voice.read() == b"MP3DATA"


async def test_dispatch_falls_back_to_text_when_audio_missing(pipeline):
    bot = FakeBot()
    dispatch = make_telegram_dispatcher(pipeline, bot)
    delivered = await dispatch(
        _alert(audio_url="http://localhost:8080/audio/030502/missing.mp3"), _subs()[:1]
    )
    assert delivered == 1
    assert bot.voices == []
    assert bot.messages[0][0] == 111


async def test_dispatch_isolates_subscriber_failures(pipeline, settings):
    pipeline.settings = settings.model_copy(update={"telegram_broadcast_channel_id": None})
    bot = FakeBot(raise_for={"222"})
    dispatch = make_telegram_dispatcher(pipeline, bot)

    delivered = await dispatch(_alert(), _subs())

    assert delivered == 1  # 222 failed, 111 delivered, run survived
    assert [chat for chat, _ in bot.messages] == [111]
