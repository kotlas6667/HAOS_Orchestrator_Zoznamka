from __future__ import annotations

from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.calendar_provider import MockCalendarProvider, RealCalendarProvider


class CalendarTool(Tool):
    name = "calendar"
    description = "Google Calendar — view events, create events, check schedule."

    def __init__(self) -> None:
        self.provider = self._create_provider()

    def _create_provider(self):
        if getattr(settings, "calendar_provider", "mock") == "oauth":
            return RealCalendarProvider(
                credentials_path=settings.gmail_credentials_json,
                token_path=getattr(settings, "calendar_token_pickle", "token_calendar.pickle"),
            )
        return MockCalendarProvider()

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "today")
        days = int(ctx.get("days", 7))
        max_results = int(ctx.get("max_results", 10))

        if action == "today":
            return await self.provider.get_today_events()

        if action == "upcoming":
            return await self.provider.get_events(days=days, max_results=max_results)

        if action == "create":
            summary = ctx.get("summary", "")
            start = ctx.get("start", "")
            end = ctx.get("end", "")
            description = ctx.get("description", "")
            print(f"[Calendar] create: summary='{summary}', start='{start}', end='{end}'")
            if not summary or not start:
                return {
                    "status": "error",
                    "reply": "Pre vytvorenie udalosti potrebujem názov a čas. Napr.: 'Pridaj meeting zajtra o 10:00 — Standup'",
                }
            # Ensure timezone offset is present (Europe/Bratislava = UTC+1 winter, UTC+2 summer)
            from datetime import datetime, timedelta
            import zoneinfo
            if start and "+" not in start and "Z" not in start:
                try:
                    tz = zoneinfo.ZoneInfo("Europe/Bratislava")
                    start_dt = datetime.fromisoformat(start).replace(tzinfo=tz)
                    start = start_dt.isoformat()
                except (ValueError, KeyError):
                    pass
            if end and "+" not in end and "Z" not in end:
                try:
                    tz = zoneinfo.ZoneInfo("Europe/Bratislava")
                    end_dt = datetime.fromisoformat(end).replace(tzinfo=tz)
                    end = end_dt.isoformat()
                except (ValueError, KeyError):
                    pass
            # If no end time, default to 1 hour after start
            if not end and start:
                try:
                    start_dt = datetime.fromisoformat(start)
                    end = (start_dt + timedelta(hours=1)).isoformat()
                except ValueError:
                    end = start
            print(f"[Calendar] final: start='{start}', end='{end}'")
            return await self.provider.create_event(summary, start, end, description)

        if action == "update":
            summary = ctx.get("summary", "")
            date = ctx.get("date", "")
            new_start = ctx.get("start", "")
            new_end = ctx.get("end", "")
            old_time = ctx.get("old_time", "")

            # If missing key identifiers, list events on that date and ask for confirmation
            if not summary or not date:
                if date:
                    events_result = await self.provider.get_events_on_date(date)
                    events = events_result.get("events", [])
                    if events:
                        event_list = "\n".join([f"• {e['start_time']} — {e['summary']}" for e in events])
                        return {
                            "status": "clarify",
                            "reply": f"Ktorú udalosť chceš zmeniť? Nájdené udalosti z {date}:\n{event_list}\n\nUpresnite: názov udalosti a nový čas.",
                        }
                    return {"status": "error", "reply": f"V {date} neboli nájdené žiadne udalosti."}
                return {"status": "error", "reply": "Pre úpravu udalosti potrebujem presne: názov udalosti, dátum a nový čas. Napr: 'uprav Test z 3.7.2026 z 16:00 na 15:00'"}

            if not new_start:
                return {
                    "status": "clarify",
                    "reply": f"Na aký čas chceš zmeniť udalosť '{summary}' z {date}? Zadaj nový čas (napr. '15:00').",
                }

            from datetime import datetime, timedelta
            import zoneinfo
            tz = zoneinfo.ZoneInfo("Europe/Bratislava")

            if "+" not in new_start and "Z" not in new_start:
                try:
                    new_start = datetime.fromisoformat(new_start).replace(tzinfo=tz).isoformat()
                except ValueError:
                    pass

            if not new_end:
                try:
                    start_dt = datetime.fromisoformat(new_start)
                    new_end = (start_dt + timedelta(hours=1)).isoformat()
                except ValueError:
                    new_end = new_start
            elif "+" not in new_end and "Z" not in new_end:
                try:
                    new_end = datetime.fromisoformat(new_end).replace(tzinfo=tz).isoformat()
                except ValueError:
                    pass

            return await self.provider.update_event(summary, date, old_time, new_start, new_end)

        if action == "delete":
            date = ctx.get("date", "")
            event_id = ctx.get("event_id", "")
            if event_id:
                return await self.provider.delete_event(event_id)
            if date:
                # Show events first and ask for confirmation if no specific name given
                summary = ctx.get("summary", "")
                if not summary:
                    # List what will be deleted
                    events_result = await self.provider.get_events(days=1, max_results=20)
                    events = events_result.get("events", [])
                    if not events:
                        return {"status": "error", "reply": f"V {date} neboli nájdené žiadne udalosti."}
                    if len(events) > 1:
                        event_list = "\n".join([f"• {e['start_time']} — {e['summary']}" for e in events])
                        return {
                            "status": "clarify",
                            "reply": f"Našiel som {len(events)} udalostí v {date}. Ktorú chceš vymazať?\n{event_list}\n\nNapiš presný názov, alebo 'všetky' pre vymazanie všetkých.",
                        }
                return await self.provider.delete_events_on_date(date)
            return {"status": "error", "reply": "Pre vymazanie potrebujem dátum (napr. 'vymaž udalosti z 3.7.2026')."}

        return {"status": "error", "error": f"Neznáma akcia: {action}"}
