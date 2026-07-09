from __future__ import annotations

from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.weather_provider import MockWeatherProvider, OpenWeatherProvider, WeatherProvider


class WeatherTool(Tool):
    name = "weather"
    description = "Provides weather planning data with mock/live provider support."

    def __init__(self) -> None:
        self.provider = self._build_provider()

    def _build_provider(self) -> WeatherProvider:
        if settings.weather_provider.lower() == "openweather" and settings.openweather_api_key:
            return OpenWeatherProvider(
                api_key=settings.openweather_api_key,
                endpoint=settings.weather_api_url,
                units=settings.weather_units,
                lang=settings.weather_lang,
                timeout_sec=settings.weather_timeout_sec,
            )
        return MockWeatherProvider()

    def _extract_city(self, prompt: str) -> str:
        words = prompt.replace(",", " ").replace("?", " ").split()
        for i, token in enumerate(words):
            if token.lower() in {"v", "in", "for", "pre", "na"} and i + 1 < len(words):
                return words[i + 1]
        filler = {"myslim", "myslím", "myslím", "mislím", "prosím", "prosim", "myslím"}
        for word in reversed(words):
            if word.lower() not in filler:
                return word
        return settings.weather_default_city

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        city = ctx.get("city", "").strip()
        if not city:
            city = settings.weather_default_city

        action = ctx.get("action", "current")
        days = ctx.get("days", 3)

        if action == "forecast":
            result = await self.provider.get_forecast(city, days=days)
        elif action == "hourly":
            result = await self.provider.get_hourly(city)
        else:
            result = await self.provider.get_weather(city)

        if result.get("provider") == "mock":
            result["next_step"] = "Provide weather API details and switch WEATHER_PROVIDER=openweather."

        return result
