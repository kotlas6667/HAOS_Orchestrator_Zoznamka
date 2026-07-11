from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    # Tinder credentials. Tinder normally logs in via phone-number OTP, Google,
    # Facebook, or Apple rather than a plain email+password form — fill in
    # whichever the account actually uses, leave the rest empty. Because OTP/
    # captcha can't be driven reliably by Selenium, point `tinder_user_data_dir`
    # at a persistent Chrome profile directory: run once with TINDER_HEADLESS=false,
    # solve the login challenge manually in that window, then switch back to
    # headless — later runs reuse the saved profile and skip the challenge.
    tinder_email: str = ""
    tinder_password: str = ""
    tinder_phone: str = ""
    tinder_login_url: str = "https://tinder.com/app/login"

    # Where this bot's own local HTTP server listens (orchestrator calls this).
    # Explicit env var names below (TINDER_*, via validation_alias — pydantic v2
    # does not support the old pydantic-v1 `Field(env=...)` kwarg) avoid
    # colliding with elitedate_bot's generically-named BOT_HOST/BROWSER/etc.
    # when both share the same .env.
    bot_host: str = Field(default="127.0.0.1", validation_alias="TINDER_BOT_HOST")
    bot_port: int = Field(default=8601, validation_alias="TINDER_BOT_PORT")

    # Where the orchestrator's FastAPI app listens (this bot calls that)
    orchestrator_url: str = "http://127.0.0.1:8000"

    # Polling
    poll_enabled: bool = Field(default=True, validation_alias="TINDER_POLL_ENABLED")
    poll_interval_min_sec: float = Field(default=90.0, validation_alias="TINDER_POLL_INTERVAL_MIN_SEC")
    poll_interval_max_sec: float = Field(default=180.0, validation_alias="TINDER_POLL_INTERVAL_MAX_SEC")

    # Pause after each navigation / tab switch — Tinder's SPA is slow to render.
    page_settle_sec: float = Field(default=3.0, validation_alias="TINDER_PAGE_SETTLE_SEC")
    # Max wait for any single Selenium / health-check step (seconds).
    wait_timeout_sec: float = Field(default=10.0, validation_alias="TINDER_WAIT_TIMEOUT_SEC")
    # After clicking Správy — wait for the inbox list to paint (like reading a screenshot).
    spravy_settle_sec: float = Field(default=10.0, validation_alias="TINDER_SPRAVY_SETTLE_SEC")

    # Browser
    browser: str = Field(default="chrome", validation_alias="TINDER_BROWSER")  # supported: chrome, edge
    headless: bool = Field(default=True, validation_alias="TINDER_HEADLESS")
    browser_binary: str | None = Field(default=None, validation_alias="TINDER_BROWSER_BINARY")
    webdriver_path: str | None = Field(default=None, validation_alias="TINDER_WEBDRIVER_PATH")
    window_size: str = Field(default="1366,768", validation_alias="TINDER_WINDOW_SIZE")
    user_agent: str | None = Field(default=None, validation_alias="TINDER_USER_AGENT")
    user_data_dir: str | None = Field(default=None, validation_alias="TINDER_USER_DATA_DIR")

    geolocation_enabled: bool = Field(default=True, validation_alias="TINDER_GEOLOCATION_ENABLED")
    geolocation_latitude: float = Field(default=48.1486, validation_alias="TINDER_GEOLOCATION_LAT")
    geolocation_longitude: float = Field(default=17.1077, validation_alias="TINDER_GEOLOCATION_LON")

    seen_messages_file: str = "tinder_bot/.seen_messages.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")


settings = BotSettings()
