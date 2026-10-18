"""MekongPulse shared domain engine.

Layering (TRD §2.2): domain models and rules have no framework dependencies;
infrastructure clients (MRC, Open-Meteo, repository adapters) degrade gracefully;
application orchestration (ingestion pipeline, sentinel patrol, ADK tools) binds
them together for the FastAPI gateway and the Telegram bot.
"""

__version__ = "0.9.0"
