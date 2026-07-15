from __future__ import annotations

import re

from app.schemas import PromptResponse


def trim_to_discord_limit(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "️"
    "]+",
    flags=re.UNICODE,
)


_ENTITY_ID_PARENS_PATTERN = re.compile(r"\s*\([a-z_]+\.[a-zA-Z0-9_]+\)")


def clean_for_speech(text: str) -> str:
    """Strip markdown/emoji/entity_id noise so text reads naturally through TTS."""
    text = _EMOJI_PATTERN.sub("", text)
    text = _ENTITY_ID_PARENS_PATTERN.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("*", "")
    text = re.sub(r"[•▪●]", ", ", text)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _format_todo(result: dict) -> str:
    """Format TODO responses for Discord."""
    if result.get("status") == "error":
        return f"⚠️ {result.get('error', 'Neznáma chyba')}"

    action = result.get("action", "")

    if action == "add":
        if result.get("status") == "duplicate":
            return f"⚠️ {result.get('reply', 'Duplicita')}"
        return f"✅ Pridané: **{result.get('task', '')}** (#{result.get('id', '?')})"

    if action == "complete":
        return f"✅ Hotovo: ~~{result.get('task', '')}~~"

    if action == "remove":
        return f"🗑️ {result.get('message', 'Odstránené')}"

    if action == "clear_done":
        return f"🧹 {result.get('message', 'Vyčistené')}"

    if action == "list":
        pending = result.get("pending", [])
        done = result.get("done", [])

        if not pending and not done:
            return "📋 Zoznam je prázdny. Žiadne úlohy."

        lines = []
        if pending:
            lines.append(f"📋 **Úlohy** ({len(pending)}):")
            for t in pending:
                lines.append(f"  {t['id']}. {t['task']}")
        if done:
            lines.append(f"\n✅ **Dokončené** ({len(done)}):")
            for t in done[:5]:
                lines.append(f"  ~~{t['task']}~~")
        return "\n".join(lines)

    return f"📋 {result.get('message', 'OK')}"


def _format_homeassistant(result: dict) -> str:
    """Format Home Assistant responses for Discord."""
    if result.get("status") == "error":
        return f"⚠️ {result.get('error', 'Neznáma chyba')}"

    if result.get("status") == "clarify":
        return f"❓ {result.get('reply', '')}"

    action = result.get("action", "")

    # Service call result (turn_on, turn_off, toggle, etc.)
    if action in ("turn_on", "turn_off", "toggle") or "." in action:
        entity = result.get("entity_id", "?")
        msg = result.get("message", f"{action} → {entity}")
        return f"🏠 ✅ {msg}"

    # Single entity state
    if "state" in result and "entity_id" in result:
        name = result.get("friendly_name", result.get("entity_id", "?"))
        state = result.get("state", "?")
        attrs = result.get("attributes", {})
        lines = [f"🏠 **{name}**: {state}"]
        # Show useful attributes
        if "temperature" in attrs:
            lines.append(f"🌡️ Teplota: {attrs['temperature']}°C")
        if "brightness" in attrs:
            lines.append(f"💡 Jas: {round(attrs['brightness'] / 255 * 100)}%")
        if "current_temperature" in attrs:
            lines.append(f"🌡️ Aktuálna: {attrs['current_temperature']}°C")
        return "\n".join(lines)

    # List entities
    if action == "list_entities":
        entities = result.get("entities", [])
        total = result.get("total", len(entities))
        if not entities:
            return "🏠 Žiadne zariadenia sa nenašli."
        lines = [f"🏠 **Zariadenia** ({total} celkom):"]
        for e in entities[:15]:
            name = e.get("friendly_name") or e.get("entity_id", "?")
            state = e.get("state", "?")
            lines.append(f"• **{name}** — {state}")
        if total > 15:
            lines.append(f"_...a ďalších {total - 15}_")
        return "\n".join(lines)

    # List automations
    if action == "list_automations":
        automations = result.get("automations", [])
        if not automations:
            return "🏠 Žiadne automatizácie."
        lines = [f"🏠 **Automatizácie** ({len(automations)}):"]
        for a in automations[:15]:
            name = a.get("friendly_name") or a.get("entity_id", "?")
            state = a.get("state", "?")
            lines.append(f"• **{name}** — {state}")
        return "\n".join(lines)

    # Fallback
    return f"🏠 Hotovo: {result}"


def _format_calendar(result: dict) -> str:
    """Format Calendar responses for Discord."""
    if result.get("status") == "error":
        return f"⚠️ {result.get('reply', result.get('error', 'Neznáma chyba'))}"

    if result.get("status") == "clarify":
        return f"❓ {result.get('reply', '')}"

    action = result.get("action", "")

    # message field — update/delete confirmation
    if result.get("message"):
        return f"📅 ✅ {result.get('message')}"

    if action == "create":
        summary = result.get("summary", "?")
        start = result.get("start", "")
        time_str = start.split("T")[1][:5] if "T" in start else ""
        date_str = start.split("T")[0] if "T" in start else ""
        return f"📅 ✅ Udalosť vytvorená: **{summary}**\n🕐 {date_str} o {time_str}"

    if action == "update":
        return f"📅 ✅ {result.get('message', 'Udalosť aktualizovaná')}"

    if action == "delete":
        deleted = result.get("deleted", [])
        if deleted:
            return f"🗑️ Vymazané: {', '.join(deleted)}"
        return f"🗑️ {result.get('message', 'Vymazané')}"

    # List events (today or upcoming) — also shown as clarification
    events = result.get("events", [])
    if not events:
        if action == "today":
            return "📅 Dnes nemáš žiadne udalosti. Voľný deň! 🎉"
        return "📅 Žiadne nadchádzajúce udalosti."

    title = "📅 **Dnes**" if action == "today" else f"📅 **Nadchádzajúce** ({result.get('days', 7)} dní)"
    lines = [f"{title} ({len(events)}):"]

    last_date = ""
    for e in events:
        # Group by date
        event_date = e.get("start", "")[:10]
        if event_date != last_date:
            from datetime import datetime
            try:
                d = datetime.fromisoformat(event_date)
                day_name = d.strftime("%a %-d.%-m.")
            except Exception:
                day_name = event_date
            lines.append(f"  **{day_name}**")
            last_date = event_date

        name = e.get("summary", "(bez názvu)")
        time = e.get("start_time", "")
        if e.get("all_day"):
            lines.append(f"    📌 {name} (celý deň)")
        elif time:
            lines.append(f"    🕐 {time} — {name}")
        else:
            lines.append(f"    • {name}")

    lines.append("")
    return "\n".join(lines)


def _format_weather(result: dict) -> str:
    # Handle error response (e.g. city not found)
    if result.get("status") == "error":
        error_msg = result.get("error", "Neznáma chyba")
        city = result.get("city", "?")
        return f"⚠️ **Počasie — {city}**\n{error_msg}"

    # Multi-day forecast
    if result.get("action") == "forecast":
        city = result.get("city", "?")
        days = result.get("days", 3)
        forecast_list = result.get("forecast", [])
        if not forecast_list:
            return f"⚠️ **Predpoveď — {city}**\nŽiadne dáta."

        lines = [f"📅 **Predpoveď — {city}** ({days} dni):"]
        for day in forecast_list:
            date_str = day.get("date", "?")
            # Format date nicely
            try:
                from datetime import datetime
                d = datetime.fromisoformat(date_str)
                day_names = ["Po", "Ut", "St", "Št", "Pi", "So", "Ne"]
                formatted = f"{day_names[d.weekday()]} {d.day}.{d.month}."
            except Exception:
                formatted = date_str

            temp_min = day.get("temp_min", "?")
            temp_max = day.get("temp_max", "?")
            desc = day.get("description", "?")
            wind = day.get("wind_kph", "")
            wind_str = f" | 💨 {wind} km/h" if wind else ""
            lines.append(f"  **{formatted}**: {temp_min}°–{temp_max}°C — {desc}{wind_str}")

        return "\n".join(lines)

    city = result.get("city", "?")
    temp = result.get("temperature_c")
    forecast = result.get("forecast", "?")
    wind = result.get("wind_kph")
    feels = result.get("feels_like_c")

    lines = [f"**Pocasie — {city}**"]
    if temp is not None:
        lines.append(f"🌡️  Teplota: **{temp} °C**")
    if feels is not None:
        lines.append(f"🤔  Pocitova: **{feels} °C**")
    lines.append(f"☁️  Stav: {forecast}")
    if wind is not None:
        lines.append(f"💨  Vietor: {wind} km/h")
    return "\n".join(lines)


def _format_gmail(result: dict) -> str:
    # Send confirmation
    if result.get("action") == "send" and result.get("status") == "success":
        recipient = result.get("recipient", "?")
        subject = result.get("subject", "?")
        return f"✅ **Email odoslaný**\n📬 Komu: {recipient}\n📌 Predmet: {subject}"

    # Send error
    if result.get("action") == "send" and result.get("status") == "error":
        error = result.get("error", "Neznáma chyba")
        return f"❌ **Email sa nepodarilo odoslať**\n{error}"

    # Count result
    if "count" in result:
        return f"📬 V schránke máš **{result['count']}** emailov ({result.get('query', '')})"

    # Single email detail
    if "body_preview" in result:
        position = result.get("position")
        pos_str = f" [{position}.]" if position else ""
        lines = [
            f"📧{pos_str} **{result.get('subject', 'Bez predmetu')}**",
            f"👤 Od: {result.get('from', '?')}",
            f"📅 {result.get('date', '')}",
            f"",
            result.get("body_preview", ""),
        ]
        return "\n".join(lines)

    # Email list
    emails = result.get("emails", [])
    if not emails:
        return "📭 Žiadne emaily sa nenašli."
    lines = [f"**Emaily** ({len(emails)}):"]
    for i, mail in enumerate(emails[:5], 1):
        sender = mail.get("from", "?")
        subject = mail.get("subject", "(bez predmetu)")
        lines.append(f"{i}. **{subject}**\n   od: {sender}")
    return "\n".join(lines)


def build_discord_reply(prompt: str, response: PromptResponse) -> str:
    if not response.executions:
        return "Nepodarilo sa spracovat poziadavku."

    execution = response.executions[0]
    result = execution.result
    tool = execution.tool

    if tool == "chat":
        if result.get("status") == "ignored":
            return ""
        chat_reply = str(result.get("reply", "")).strip()
        if chat_reply:
            return trim_to_discord_limit(chat_reply)
        return "Nepodarilo sa vygenerovať odpoveď. Skús to znova."

    if tool == "weather":
        return trim_to_discord_limit(_format_weather(result))

    if tool == "calendar":
        return trim_to_discord_limit(_format_calendar(result))

    if tool == "homeassistant":
        return trim_to_discord_limit(_format_homeassistant(result))

    if tool == "todo":
        return trim_to_discord_limit(_format_todo(result))

    if tool == "gmail":
        return trim_to_discord_limit(_format_gmail(result))

    if tool == "dating_status":
        reply = str(result.get("reply", "")).strip()
        return trim_to_discord_limit(reply or "Stav zoznamiek nie je dostupný.")

    # Fallback pre ostatne tooly
    lines: list[str] = []
    for key, value in result.items():
        if key in {"status", "action", "provider", "raw", "target_webhook_id"}:
            continue
        if isinstance(value, dict):
            continue
        lines.append(f"**{key}:** {value}")

    return trim_to_discord_limit("\n".join(lines) or "Hotovo.")


def normalize_discord_prompt(message_content: str, *, prefix: str) -> str:
    content = message_content.strip()
    normalized_prefix = prefix.strip()

    if not normalized_prefix:
        return content

    lowered = content.lower()
    lowered_prefix = normalized_prefix.lower()
    if lowered.startswith(lowered_prefix):
        return content[len(normalized_prefix) :].strip()

    return ""
