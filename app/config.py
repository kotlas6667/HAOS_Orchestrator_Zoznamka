from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    app_name: str = "Orchestrator"
    app_env: str = "dev"

    # Discord
    discord_provider: str = "mock"
    discord_webhook_url: str | None = None
    discord_username: str = "Orchestrator Bot"
    discord_timeout_sec: float = 8.0
    discord_bot_enabled: bool = False
    discord_bot_token: str | None = None
    discord_bot_channel_id: int | None = None
    discord_bot_require_mention: bool = False
    discord_bot_prefix: str = ""
    discord_bot_allowed_users: str = ""  # Comma-separated Discord user IDs (empty = allow all)

    @field_validator("discord_bot_channel_id", mode="before")
    @classmethod
    def _empty_channel_id_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    # OpenAI GPT (routing + chat)
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", env="OPENAI_MODEL")

    # Chat
    chat_provider: str = "openai"
    chat_system_prompt: str = (
        "Si TomBot — osobný asistent ovládaný cez Discord. Odpovedaj vždy po slovensky, stručne a priateľsky.\n\n"
        "Tvoje KONKRÉTNE schopnosti (toto vieš reálne robiť):\n"
        "1. 🌤️ Počasie — aktuálne počasie v ľubovoľnom meste\n"
        "2. 📧 Gmail — čítať emaily, posielať emaily, zhrnutia, počet správ\n"
        "3. 📅 Kalendár — čo mám dnes, nadchádzajúce udalosti, vytvoriť event\n"
        "4. 🏠 Home Assistant — ovládanie smart home zariadení\n"
        "5. 📋 TODO zoznam — pridať úlohu, zobraziť, označiť ako hotové\n"
        "6. 💬 Posielanie správ cez Discord/webhook\n"
        "7. 🤖 Bežná konverzácia — odpovede na otázky, pomoc, rady\n\n"
        "PRAVIDLÁ:\n"
        "- Keď sa ťa pýtajú čo vieš/umíš, VŽDY odpovedz konkrétnymi schopnosťami zo zoznamu vyššie.\n"
        "- Odpovedaj na základe toho čo REÁLNE vieš robiť, nie všeobecne.\n"
        "- Buď stručný — max 2-3 vety na bežné otázky.\n"
        "- Ak niečo nevieš alebo nemáš k tomu prístup, povedz to priamo."
    )

    # Weather
    weather_provider: str = "openweather"
    weather_default_city: str = "Senica"
    weather_api_url: str = "https://api.openweathermap.org/data/2.5/weather"
    weather_timeout_sec: float = 8.0
    weather_units: str = "metric"
    weather_lang: str = "sk"
    openweather_api_key: str | None = None

    # Gmail
    gmail_provider: str = "mock"
    gmail_user_email: str | None = None
    gmail_credentials_json: str | None = None
    gmail_token_pickle: str | None = None

    # Google Calendar
    calendar_provider: str = "mock"
    calendar_token_pickle: str = "token_calendar.pickle"

    # Home Assistant
    ha_provider: str = "mock"
    ha_url: str | None = None
    ha_token: str | None = None
    ha_timeout_sec: float = 10.0

    # Elite Date bot (separate local process, see elitedate_bot/)
    elitedate_bot_url: str = "http://127.0.0.1:8600"
    elitedate_auto_send: bool = Field(default=False, validation_alias="ELITEDATE_AUTO_SEND")

    # Tinder bot (separate local process, see tinder_bot/)
    tinder_bot_url: str = "http://127.0.0.1:8601"
    tinder_auto_send: bool = Field(default=False, validation_alias="TINDER_AUTO_SEND")

    # Spoločný skill pre AI návrhy odpovedí v Discorde (ED + Tinder). Prázdne = súbor / default.
    dating_reply_skill: str = Field(default="", validation_alias="DATING_REPLY_SKILL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
