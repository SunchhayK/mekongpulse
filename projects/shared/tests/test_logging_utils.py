"""Regression guard: transport loggers must not leak request URLs at INFO.

httpx logs full request URLs at INFO level; Telegram API URLs embed the bot
token (`https://api.telegram.org/bot<token>/getMe`), which would land in Cloud
Logging. `configure_logging` must keep those loggers at WARNING or above.
"""

from __future__ import annotations

import logging

from mekong_shared.logging_utils import configure_logging


def test_configure_logging_silences_transport_loggers() -> None:
    configure_logging("test-service")
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
