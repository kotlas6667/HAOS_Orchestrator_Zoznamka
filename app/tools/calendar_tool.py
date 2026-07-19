from __future__ import annotations

from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.calendar_provider import MockCalendarProvider, RealCalendarProvider
from app.tools import google_accounts


class CalendarTool(Tool):
    name = "calendar"
    description = "Google Calendar — view events, create events, check schedule."

    def __init__(self) -> None:
        self._providers: dict[str, RealCalendarProvider] = {}
        self.provider = self._create_provider()

    def reload_providers(self) -> None:
        self._providers.clear()
        self.provider = self._create_provider()

    def _oauth_active(self) -> bool:
        if google_accounts.list_accounts():
            return True
        if getattr(settings, "calendar_provider", "mock") != "oauth":
            return False
        from pathlib import Path
        token = getattr(settings, "calendar_token_pickle", "token_calendar.pickle")
        return Path(token).is_file()

    def _create_provider(self):
        accounts = google_accounts.list_accounts()
        cred_path = str(google_accounts.find_credentials_path() or settings.gmail_credentials_json or "")
        if accounts:
            for acc in accounts:
                self._providers[acc["id"]] = RealCalendarProvider(
                    credentials_path=cred_path,
                    token_path=acc.get("token_path"),
                    account_id=acc.get("id"),
                    account_email=acc.get("email"),
                    allow_interactive_oauth=False,
                )
            default = google_accounts.get_account()
            if default and default["id"] in self._providers:
                return self._providers[default["id"]]
            return next(iter(self._providers.values()))

        if self._oauth_active():
            return RealCalendarProvider(
                credentials_path=settings.gmail_credentials_json,
                token_path=getattr(settings, "calendar_token_pickle", "token_calendar.pickle"),
                allow_interactive_oauth=False,
            )

        return MockCalendarProvider()

    def _resolve_provider(self, context: dict[str, Any]):
        if not self._providers:
            return self.provider
        account_id = (context.get("account_id") or "").strip()
        raw_account = (context.get("account") or "").strip()
        email = (context.get("email") or context.get("account_email") or "").strip()
        needle = (email or raw_account).strip()

        if account_id and account_id in self._providers:
            return self._providers[account_id]
        if raw_account and raw_account in self._providers:
            return self._providers[raw_account]
        if needle:
            acc = google_accounts.get_account(email=needle) or google_accounts.find_account_fuzzy(needle)
            if acc and acc.get("id") in self._providers:
                return self._providers[acc["id"]]
        return self.provider

    def _specific_account(self, ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("account") or ctx.get("account_id") or ctx.get("email") or ctx.get("account_email"))

    async def _aggregate_events(
        self,
        *,
        action: str,
        days: int,
        max_results: int,
    ) -> dict[str, Any]:
        """Merge today/upcoming events from every connected Google account."""
        per_account: list[dict[str, Any]] = []
        merged: list[dict[str, Any]] = []
        for pid, prov in self._providers.items():
            acc = getattr(prov, "account_email", None) or pid
            if action == "today":
                result = await prov.get_today_events()
            else:
                result = await prov.get_events(days=days, max_results=max_results)
            events = result.get("events", []) or []
            for ev in events:
                ev = dict(ev)
                ev.setdefault("account", acc)
                merged.append(ev)
            per_account.append({
                "account": acc,
                "total": len(events),
                "status": result.get("status", "unknown"),
            })
        # Sort by start datetime string when present
        merged.sort(key=lambda e: e.get("start") or "")
        trimmed = merged[:max_results] if max_results > 0 else merged
        return {
            "status": "success",
            "action": action,
            "account": "all",
            "events": trimmed,
            "total": len(merged),
            "returned": len(trimmed),
            "per_account": per_account,
            "days": days if action == "upcoming" else None,
        }

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "today")
        days = int(ctx.get("days", 7))
        max_results = int(ctx.get("max_results", 10))
        provider = self._resolve_provider(ctx)

        if action in ("today", "upcoming") and self._providers and not self._specific_account(ctx):
            return await self._aggregate_events(action=action, days=days, max_results=max_results)

        if action == "today":
            result = await provider.get_today_events()
            if getattr(provider, "account_email", None):
                result["account"] = provider.account_email
            return result

        if action == "upcoming":
            result = await provider.get_events(days=days, max_results=max_results)
            if getattr(provider, "account_email", None):
                result["account"] = provider.account_email
            return result

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
            result = await provider.create_event(summary, start, end, description)
            if getattr(provider, "account_email", None):
                result.setdefault("account", provider.account_email)
            return result

        if action == "update":
            summary = ctx.get("summary", "")
            date = ctx.get("date", "")
            new_start = ctx.get("start", "")
            new_end = ctx.get("end", "")
            old_time = ctx.get("old_time", "")

            # If missing key identifiers, list events on that date and ask for confirmation
            if not summary or not date:
                if date:
                    events_result = await provider.get_events_on_date(date)
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

            return await provider.update_event(summary, date, old_time, new_start, new_end)

        if action == "delete":
            date = ctx.get("date", "")
            event_id = ctx.get("event_id", "")
            if event_id:
                return await provider.delete_event(event_id)
            if date:
                # Show events first and ask for confirmation if no specific name given
                summary = ctx.get("summary", "")
                if not summary:
                    # List what will be deleted
                    events_result = await provider.get_events(days=1, max_results=20)
                    events = events_result.get("events", [])
                    if not events:
                        return {"status": "error", "reply": f"V {date} neboli nájdené žiadne udalosti."}
                    if len(events) > 1:
                        event_list = "\n".join([f"• {e['start_time']} — {e['summary']}" for e in events])
                        return {
                            "status": "clarify",
                            "reply": f"Našiel som {len(events)} udalostí v {date}. Ktorú chceš vymazať?\n{event_list}\n\nNapiš presný názov, alebo 'všetky' pre vymazanie všetkých.",
                        }
                return await provider.delete_events_on_date(date)
            return {"status": "error", "reply": "Pre vymazanie potrebujem dátum (napr. 'vymaž udalosti z 3.7.2026')."}

        return {"status": "error", "error": f"Neznáma akcia: {action}"}
