from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    # Elite Date credentials
    elitedate_email: str = ""
    elitedate_password: str = ""
    elitedate_login_url: str = "https://www.elitedate.sk/prihlaseni"

    # Where this bot's own local HTTP server listens (orchestrator calls this).
    # HA add-on must bind 0.0.0.0 so the orchestrator container can reach /send.
    bot_host: str = "0.0.0.0"
    bot_port: int = 8600

    # Where the orchestrator's FastAPI app listens (this bot calls that).
    # HA lokálne add-ony: DNS = local-{slug} s pomlčkami.
    orchestrator_url: str = "http://8c003d88-haos-orchestrator:8000"

    # Polling (parity with Tinder: poll_enabled in HA Nastavenia)
    poll_enabled: bool = Field(default=True, validation_alias="POLL_ENABLED")
    poll_interval_min_sec: float = Field(default=90.0, validation_alias="POLL_INTERVAL_MIN_SEC")
    poll_interval_max_sec: float = Field(default=180.0, validation_alias="POLL_INTERVAL_MAX_SEC")

    # Browser
    browser: str = "chrome"  # supported: chrome, edge
    headless: bool = True
    browser_binary: str | None = None
    webdriver_path: str | None = None
    chrome_binary: str | None = None  # backward compatible alias
    chromedriver_path: str | None = None  # backward compatible alias
    window_size: str = "1366,768"
    user_agent: str | None = None

    seen_messages_file: str = "elitedate_bot/.seen_messages.json"

    # Morning greet on „Noví členovia“ (disabled by default).
    morning_greet_enabled: bool = False
    morning_greet_max_profiles: int = 10
    morning_greet_hour: int = 7
    morning_greet_minute: int = 0
    morning_greet_message: str = "Ahoj :-)"

    # Filter defaults matching the user's „Noví členovia“ UI preset.
    morning_greet_age_from: int = 34
    morning_greet_age_to: int = 41
    morning_greet_height_to: int = 166
    morning_greet_distance_km: int = 75

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")


settings = BotSettings()
