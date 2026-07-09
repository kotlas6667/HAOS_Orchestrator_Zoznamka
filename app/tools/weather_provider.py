from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config import settings as app_settings


class WeatherProvider(Protocol):
    async def get_weather(self, city: str) -> dict[str, Any]:
        """Return normalized weather information for a city."""

    async def get_forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        """Return daily forecast for a city (up to 5 days)."""

    async def get_hourly(self, city: str) -> dict[str, Any]:
        """Return hourly forecast (next 12 hours) for a city."""


class MockWeatherProvider:
    async def get_weather(self, city: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "city": city,
            "forecast": "Partly cloudy",
            "temperature_c": 22,
            "wind_kph": 9,
            "provider": "mock",
        }

    async def get_forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        return {
            "status": "mock",
            "city": city,
            "days": days,
            "forecast": [
                {"date": "2026-07-03", "temp_min": 18, "temp_max": 26, "description": "Partly cloudy"},
                {"date": "2026-07-04", "temp_min": 17, "temp_max": 24, "description": "Rain"},
                {"date": "2026-07-05", "temp_min": 19, "temp_max": 27, "description": "Sunny"},
            ],
            "provider": "mock",
        }

    async def get_hourly(self, city: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "city": city,
            "hours": [
                {"time": "14:00", "temp": 24, "description": "Partly cloudy", "icon": "03d"},
                {"time": "15:00", "temp": 25, "description": "Sunny", "icon": "01d"},
                {"time": "16:00", "temp": 24, "description": "Sunny", "icon": "01d"},
            ],
            "provider": "mock",
        }


class OpenWeatherProvider:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        units: str,
        lang: str,
        timeout_sec: float,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._units = units
        self._lang = lang
        self._timeout_sec = timeout_sec

    async def _fetch_weather(self, city: str) -> httpx.Response:
        """Make a single weather API request."""
        params = {
            "q": city,
            "appid": self._api_key,
            "units": self._units,
            "lang": self._lang,
        }
        async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
            return await client.get(self._endpoint, params=params)

    async def _ask_ai_for_city_name(self, original_city: str) -> str | None:
        """Ask GPT to suggest the correct city name with diacritics or English equivalent."""
        if not app_settings.openai_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {app_settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": app_settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a geographic name resolver. The user gives you a city name that was not found "
                        "in the OpenWeatherMap API. Suggest the correct spelling with proper Slovak/Czech diacritics, "
                        "or the English/international name that OpenWeatherMap would recognize. "
                        "Respond with ONLY the corrected city name, nothing else. No quotes, no explanation. "
                        "If you don't know, respond with just the word UNKNOWN."
                    ),
                },
                {
                    "role": "user",
                    "content": f"City not found: {original_city}",
                },
            ],
            "temperature": 0.0,
        }

        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            suggestion = response.json()["choices"][0]["message"]["content"].strip()
            if suggestion and suggestion.upper() != "UNKNOWN" and suggestion.lower() != original_city.lower():
                return suggestion
        except Exception:
            pass
        return None

    async def get_weather(self, city: str) -> dict[str, Any]:
        response = await self._fetch_weather(city)

        # If city not found, ask AI for corrected name and retry
        if response.status_code == 404:
            corrected_city = await self._ask_ai_for_city_name(city)
            if corrected_city:
                response = await self._fetch_weather(corrected_city)
                if response.status_code == 404:
                    return {
                        "status": "error",
                        "city": city,
                        "error": (
                            f"Mesto '{city}' (ani '{corrected_city}') nebolo nájdené v databáze počasia."
                        ),
                        "provider": "openweather",
                    }
            else:
                return {
                    "status": "error",
                    "city": city,
                    "error": f"Mesto '{city}' nebolo nájdené v databáze počasia.",
                    "provider": "openweather",
                }

        response.raise_for_status()
        payload = response.json()

        weather = payload.get("weather") or []
        main = payload.get("main") or {}
        wind = payload.get("wind") or {}

        description = "unknown"
        if weather and isinstance(weather[0], dict):
            description = weather[0].get("description") or "unknown"

        return {
            "status": "live",
            "city": payload.get("name") or city,
            "forecast": description,
            "temperature_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "wind_kph": round((wind.get("speed") or 0) * 3.6, 2),
            "provider": "openweather",
        }

    async def get_forecast(self, city: str, days: int = 3) -> dict[str, Any]:
        """Fetch multi-day forecast using OpenWeather 5-day/3-hour endpoint."""
        params = {
            "q": city,
            "appid": self._api_key,
            "units": self._units,
            "lang": self._lang,
        }
        forecast_url = self._endpoint.replace("/weather", "/forecast")

        async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
            response = await client.get(forecast_url, params=params)

        if response.status_code == 404:
            # Try AI city correction
            corrected_city = await self._ask_ai_for_city_name(city)
            if corrected_city:
                params["q"] = corrected_city
                async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
                    response = await client.get(forecast_url, params=params)
                if response.status_code == 404:
                    return {
                        "status": "error",
                        "city": city,
                        "error": f"Mesto '{city}' (ani '{corrected_city}') nebolo nájdené.",
                        "provider": "openweather",
                    }
            else:
                return {
                    "status": "error",
                    "city": city,
                    "error": f"Mesto '{city}' nebolo nájdené v databáze počasia.",
                    "provider": "openweather",
                }

        response.raise_for_status()
        data = response.json()

        # Group 3-hour entries by day and compute daily min/max/description
        from collections import defaultdict
        daily: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "temps": [], "descriptions": [], "wind_speeds": []
        })

        for entry in data.get("list", []):
            dt_txt = entry.get("dt_txt", "")
            date_str = dt_txt[:10]
            main_data = entry.get("main", {})
            daily[date_str]["temps"].append(main_data.get("temp", 0))
            weather_list = entry.get("weather", [])
            if weather_list:
                daily[date_str]["descriptions"].append(weather_list[0].get("description", ""))
            wind_data = entry.get("wind", {})
            daily[date_str]["wind_speeds"].append(wind_data.get("speed", 0))

        # Build forecast list limited to requested days (skip today if partial)
        from datetime import date as date_type
        today_str = date_type.today().isoformat()
        sorted_dates = sorted(daily.keys())
        # Skip today — user wants "next N days"
        future_dates = [d for d in sorted_dates if d > today_str][:days]

        forecast_list = []
        for d in future_dates:
            info = daily[d]
            temps = info["temps"]
            descriptions = info["descriptions"]
            winds = info["wind_speeds"]
            # Pick most common description (midday-ish)
            midday_desc = descriptions[len(descriptions) // 2] if descriptions else "?"
            forecast_list.append({
                "date": d,
                "temp_min": round(min(temps), 1),
                "temp_max": round(max(temps), 1),
                "description": midday_desc,
                "wind_kph": round(max(winds) * 3.6, 1),
            })

        resolved_city = data.get("city", {}).get("name", city)

        return {
            "status": "live",
            "action": "forecast",
            "city": resolved_city,
            "days": days,
            "forecast": forecast_list,
            "provider": "openweather",
        }

    async def get_hourly(self, city: str) -> dict[str, Any]:
        """Return next 12 hours of 3-hour forecast data for the dashboard."""
        params = {
            "q": city,
            "appid": self._api_key,
            "units": self._units,
            "lang": self._lang,
        }
        forecast_url = self._endpoint.replace("/weather", "/forecast")

        async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
            response = await client.get(forecast_url, params=params)

        if response.status_code == 404:
            # Try AI city correction (same as get_weather)
            corrected_city = await self._ask_ai_for_city_name(city)
            if corrected_city:
                params["q"] = corrected_city
                async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
                    response = await client.get(forecast_url, params=params)
                if response.status_code == 404:
                    return {
                        "status": "error",
                        "city": city,
                        "error": f"Mesto '{city}' (ani '{corrected_city}') nebolo nájdené.",
                        "provider": "openweather",
                    }
            else:
                return {
                    "status": "error",
                    "city": city,
                    "error": f"Mesto '{city}' nebolo nájdené.",
                    "provider": "openweather",
                }

        response.raise_for_status()
        data = response.json()

        # Take next 4 entries (= 12 hours at 3-hour intervals)
        entries = data.get("list", [])[:4]
        hours = []
        for entry in entries:
            dt_txt = entry.get("dt_txt", "")
            time_str = dt_txt[11:16] if len(dt_txt) >= 16 else "?"
            main_data = entry.get("main", {})
            weather_list = entry.get("weather", [])
            icon = weather_list[0].get("icon", "01d") if weather_list else "01d"
            description = weather_list[0].get("description", "?") if weather_list else "?"
            wind_data = entry.get("wind", {})

            hours.append({
                "time": time_str,
                "temp": round(main_data.get("temp", 0), 1),
                "feels_like": round(main_data.get("feels_like", 0), 1),
                "description": description,
                "icon": icon,
                "wind_kph": round((wind_data.get("speed", 0)) * 3.6, 1),
                "humidity": main_data.get("humidity", 0),
            })

        resolved_city = data.get("city", {}).get("name", city)

        return {
            "status": "live",
            "action": "hourly",
            "city": resolved_city,
            "hours": hours,
            "provider": "openweather",
        }
