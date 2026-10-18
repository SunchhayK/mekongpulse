"""Environment-driven settings shared by every MekongPulse service.

Three first-class environments (development, staging, production) are selected
by the ENVIRONMENT variable; `projects/scripts/switch_env.sh` wires the
matching .env preset. Persistence adapters are chosen from the environment:
PostgreSQL for development/staging, Firestore + GCS for production.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# projects/ root: shared/src/mekong_shared/config.py -> parents[3]
PROJECTS_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_DEFAULT = PROJECTS_ROOT / "data"

ENVIRONMENTS = ("development", "staging", "production")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # --- persistence -----------------------------------------------------
    database_url: str = "postgresql://postgres:postgres@localhost:5432/mekongpulse"
    repository_backend: str | None = None  # postgres | firestore | memory (None = auto)
    firestore_project: str | None = None
    gcs_bucket: str | None = None
    gcs_public_base: str | None = None  # e.g. https://storage.googleapis.com/<bucket>

    # --- external telemetry ----------------------------------------------
    mrc_base_url: str = "https://api.mrcmekong.org/api/v1"
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    http_timeout_seconds: float = 10.0
    weather_refresh_minutes: int = 60  # forecasts update hourly; syncs run every 15 min

    # --- telegram ---------------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_broadcast_channel_id: str | None = None

    # --- gemini -----------------------------------------------------------
    gemini_api_key: str | None = None
    gemini_text_model: str = "gemini-3.8-flash"
    # Comma-separated ordered fallbacks; quotas are per model per day.
    gemini_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash-lite"
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    use_vertex_ai: bool = False
    vertex_project: str | None = None
    vertex_location: str = "asia-southeast1"
    # ADK's GoogleLLM currently stalls on Vertex AI; the native ReAct loop is
    # the supported engine there. Keep ADK as the default for Gemini API keys.
    advisor_use_adk: bool = True

    # --- gateway / security ----------------------------------------------
    admin_token: str | None = None  # Bearer token for scheduler/admin endpoints
    officer_passcode: str | None = None  # browser sign-in passcode (env OFFICER_PASSCODE)
    officer_session_ttl_hours: int = 12  # signed officer session lifetime
    cors_origins: str = "*"  # comma-separated; restricted in production
    log_salt: str = "mekongpulse-dev-salt"  # SHA-256 salt for GPS / id anonymization
    public_base_url: str = "http://localhost:8080"  # audio URLs etc.
    web_base_url: str = "https://ai-builder-cup-9f8cd.web.app"  # officer dashboard link

    # --- domain -----------------------------------------------------------
    data_dir: Path = DATA_DIR_DEFAULT
    audio_dir: Path = DATA_DIR_DEFAULT / "audio"
    sentinel_debounce_hours: float = 6.0
    telemetry_stale_after_minutes: int = 120

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_firestore(self) -> bool:
        return self.is_production

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key) or self.use_vertex_ai

    @property
    def gemini_model_chain(self) -> list[str]:
        """Primary text model followed by configured fallbacks, deduplicated."""
        names = [self.gemini_text_model, *self.gemini_fallback_models.split(",")]
        return list(dict.fromkeys(name.strip() for name in names if name and name.strip()))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
