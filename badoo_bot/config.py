from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    # Badoo login is phone OTP / email code / Google — not a plain password form.
    # First run: BADOO_HEADLESS=false + noVNC, complete Google (or phone) login
    # manually; later headless runs reuse /data/chrome-profile cookies.
    badoo_login_url: str = "https://badoo.com/en/signin/"
    badoo_home_url: str = "https://badoo.com/"

    bot_host: str = Field(default="0.0.0.0", validation_alias="BADOO_BOT_HOST")
    bot_port: int = Field(default=8602, validation_alias="BADOO_BOT_PORT")

    orchestrator_url: str = "http://8c003d88-haos-orchestrator:8000"

    # Polling
    poll_enabled: bool = Field(default=True, validation_alias="BADOO_POLL_ENABLED")
    poll_interval_min_sec: float = Field(default=90.0, validation_alias="BADOO_POLL_INTERVAL_MIN_SEC")
    poll_interval_max_sec: float = Field(default=180.0, validation_alias="BADOO_POLL_INTERVAL_MAX_SEC")

    page_settle_sec: float = Field(default=3.0, validation_alias="BADOO_PAGE_SETTLE_SEC")
    wait_timeout_sec: float = Field(default=30.0, validation_alias="BADOO_WAIT_TIMEOUT_SEC")

    browser: str = Field(default="chrome", validation_alias="BADOO_BROWSER")
    headless: bool = Field(default=True, validation_alias="BADOO_HEADLESS")
    browser_binary: str | None = Field(default=None, validation_alias="BADOO_BROWSER_BINARY")
    webdriver_path: str | None = Field(default=None, validation_alias="BADOO_WEBDRIVER_PATH")
    window_size: str = Field(default="1366,768", validation_alias="BADOO_WINDOW_SIZE")
    user_agent: str | None = Field(default=None, validation_alias="BADOO_USER_AGENT")
    user_data_dir: str | None = Field(default=None, validation_alias="BADOO_USER_DATA_DIR")

    geolocation_enabled: bool = Field(default=True, validation_alias="BADOO_GEOLOCATION_ENABLED")
    geolocation_latitude: float = Field(default=48.1486, validation_alias="BADOO_GEOLOCATION_LAT")
    geolocation_longitude: float = Field(default=17.1077, validation_alias="BADOO_GEOLOCATION_LON")

    auto_send: bool = Field(default=False, validation_alias="BADOO_AUTO_SEND")

    seen_messages_file: str = "badoo_bot/.seen_messages.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")


settings = BotSettings()
