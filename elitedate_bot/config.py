from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    # Elite Date credentials
    elitedate_email: str = ""
    elitedate_password: str = ""
    elitedate_login_url: str = "https://www.elitedate.sk/prihlaseni"

    # Where this bot's own local HTTP server listens (orchestrator calls this).
    # Standalone HA add-on: set BOT_HOST=0.0.0.0 in Nastaveniach / .env.
    bot_host: str = "127.0.0.1"
    bot_port: int = 8600

    # Where the orchestrator's FastAPI app listens (this bot calls that).
    # Standalone HA add-on: http://haos_orchestrator:8000 via Nastavenia / .env.
    orchestrator_url: str = "http://127.0.0.1:8000"

    # Polling
    poll_interval_min_sec: float = 90.0
    poll_interval_max_sec: float = 180.0

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")


settings = BotSettings()
