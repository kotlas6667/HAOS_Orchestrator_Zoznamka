from __future__ import annotations

import asyncio
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class CalendarProvider(Protocol):
    async def get_events(self, days: int = 7, max_results: int = 10) -> dict[str, Any]:
        """Get upcoming events."""

    async def get_today_events(self) -> dict[str, Any]:
        """Get today's events."""

    async def create_event(self, summary: str, start: str, end: str, description: str = "") -> dict[str, Any]:
        """Create a new event."""


class MockCalendarProvider:
    async def get_events(self, days: int = 7, max_results: int = 10) -> dict[str, Any]:
        return {
            "status": "mock",
            "events": [],
            "next_step": "Set CALENDAR_PROVIDER=oauth in .env",
        }

    async def get_today_events(self) -> dict[str, Any]:
        return {"status": "mock", "events": [], "next_step": "Set CALENDAR_PROVIDER=oauth in .env"}

    async def create_event(self, summary: str, start: str, end: str, description: str = "") -> dict[str, Any]:
        return {"status": "mock", "action": "create", "next_step": "Set CALENDAR_PROVIDER=oauth in .env"}


class RealCalendarProvider:
    SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def __init__(
        self,
        *,
        credentials_path: str | None = None,
        token_path: str | None = None,
        account_id: str | None = None,
        account_email: str | None = None,
        allow_interactive_oauth: bool = False,
    ) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path or "token_calendar.pickle"
        self._account_id = account_id
        self._account_email = account_email
        self._allow_interactive_oauth = allow_interactive_oauth
        self._service = None
        self._initialize_service()

    @property
    def account_id(self) -> str | None:
        return self._account_id

    @property
    def account_email(self) -> str | None:
        return self._account_email

    def _initialize_service(self) -> None:
        try:
            creds = self._load_credentials()
            from google_auth_httplib2 import AuthorizedHttp
            import httplib2

            http = httplib2.Http(disable_ssl_certificate_validation=True)
            authorized_http = AuthorizedHttp(creds, http)

            self._service = build(
                "calendar", "v3",
                http=authorized_http,
                static_discovery=False,
                cache_discovery=False,
            )
        except Exception as e:
            print(f"Warning: Could not initialize Calendar service: {e}")
            import traceback
            traceback.print_exc()

    def _load_credentials(self) -> OAuth2Credentials:
        """Load credentials from pickle; refresh if needed. No browser OAuth by default."""
        if os.path.exists(self._token_path):
            try:
                from app.tools.google_accounts import load_credentials as _ga_load
                return _ga_load(self._token_path)
            except Exception as e:
                print(f"Calendar token load via google_accounts failed ({e})")

        creds = None
        if os.path.exists(self._token_path):
            with open(self._token_path, "rb") as token_file:
                creds = pickle.load(token_file)

            if creds and creds.valid:
                return creds

            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self._token_path, "wb") as tf:
                        pickle.dump(creds, tf)
                    return creds
                except Exception as e:
                    print(f"Calendar token refresh failed ({e})")

        if not self._allow_interactive_oauth:
            raise RuntimeError(
                f"Chýba platný Calendar token ({self._token_path}). "
                "Pripoj účet cez dashboard → Google účty (jeden login = Gmail + Kalendár)."
            )

        if not self._credentials_path or not os.path.exists(self._credentials_path):
            raise FileNotFoundError(
                f"Credentials file not found: {self._credentials_path}. "
                "Use the same gmailSecret.json from Gmail setup."
            )

        flow = InstalledAppFlow.from_client_secrets_file(self._credentials_path, self.SCOPES)
        creds = flow.run_local_server(port=0)

        with open(self._token_path, "wb") as token_file:
            pickle.dump(creds, token_file)

        return creds

    def _get_service(self):
        if self._service is None:
            self._initialize_service()
        if self._service is None:
            raise RuntimeError(
                "Kalendár nie je pripojený. Zapni Google účty v nastaveniach a prihlás sa."
            )
        return self._service

    async def get_events(self, days: int = 7, max_results: int = 10) -> dict[str, Any]:
        """Get upcoming events for next N days."""
        try:
            def _fetch():
                service = self._get_service()
                now = datetime.utcnow()
                time_min = now.isoformat() + "Z"
                time_max = (now + timedelta(days=days)).isoformat() + "Z"

                result = service.events().list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone="Europe/Bratislava",
                ).execute()
                return result.get("items", [])

            events = await asyncio.to_thread(_fetch)
            return {
                "status": "success",
                "action": "list",
                "events": [self._format_event(e) for e in events],
                "total": len(events),
                "days": days,
            }
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    async def get_today_events(self) -> dict[str, Any]:
        """Get today's events."""
        try:
            def _fetch():
                service = self._get_service()
                now = datetime.utcnow()
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = start_of_day + timedelta(days=1)

                result = service.events().list(
                    calendarId="primary",
                    timeMin=start_of_day.isoformat() + "Z",
                    timeMax=end_of_day.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone="Europe/Bratislava",
                ).execute()
                return result.get("items", [])

            events = await asyncio.to_thread(_fetch)
            return {
                "status": "success",
                "action": "today",
                "events": [self._format_event(e) for e in events],
                "total": len(events),
            }
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    async def create_event(self, summary: str, start: str, end: str, description: str = "") -> dict[str, Any]:
        """Create a calendar event."""
        try:
            def _create():
                service = self._get_service()
                event = {
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": start, "timeZone": "Europe/Bratislava"},
                    "end": {"dateTime": end, "timeZone": "Europe/Bratislava"},
                }
                return service.events().insert(calendarId="primary", body=event).execute()

            result = await asyncio.to_thread(_create)
            return {
                "status": "success",
                "action": "create",
                "event_id": result.get("id"),
                "summary": summary,
                "start": start,
                "end": end,
                "link": result.get("htmlLink", ""),
            }
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    async def get_events_on_date(self, date_str: str) -> dict[str, Any]:
        """Get events for a specific date (YYYY-MM-DD)."""
        try:
            def _fetch():
                service = self._get_service()
                time_min = f"{date_str}T00:00:00"
                time_max = f"{date_str}T23:59:59"

                result = service.events().list(
                    calendarId="primary",
                    timeMin=time_min + "+02:00",
                    timeMax=time_max + "+02:00",
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone="Europe/Bratislava",
                ).execute()
                return result.get("items", [])

            events = await asyncio.to_thread(_fetch)
            return {
                "status": "success",
                "events": [self._format_event(e) for e in events],
                "total": len(events),
            }
        except HttpError as e:
            return {"status": "error", "error": str(e), "events": []}

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        """Delete a calendar event by ID."""
        try:
            def _delete():
                service = self._get_service()
                service.events().delete(calendarId="primary", eventId=event_id).execute()

            await asyncio.to_thread(_delete)
            return {"status": "success", "action": "delete", "event_id": event_id}
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    async def delete_events_on_date(self, date_str: str) -> dict[str, Any]:
        """Delete all events on a specific date."""
        try:
            def _fetch_and_delete():
                service = self._get_service()
                time_min = f"{date_str}T00:00:00Z"
                time_max = f"{date_str}T23:59:59Z"

                result = service.events().list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    timeZone="Europe/Bratislava",
                ).execute()
                events = result.get("items", [])
                deleted = []
                for event in events:
                    eid = event.get("id")
                    if eid:
                        service.events().delete(calendarId="primary", eventId=eid).execute()
                        deleted.append(event.get("summary", "(bez názvu)"))
                return deleted

            deleted = await asyncio.to_thread(_fetch_and_delete)
            return {
                "status": "success",
                "action": "delete",
                "deleted": deleted,
                "count": len(deleted),
                "message": f"Vymazaných {len(deleted)} udalostí z {date_str}.",
            }
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    async def update_event(self, summary: str, date_str: str, old_time: str, new_start: str, new_end: str) -> dict[str, Any]:
        """Find event by name+date and update its time."""
        try:
            def _find_and_update():
                service = self._get_service()
                time_min = f"{date_str}T00:00:00Z"
                time_max = f"{date_str}T23:59:59Z"

                result = service.events().list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    timeZone="Europe/Bratislava",
                ).execute()
                events = result.get("items", [])

                # Find event by summary (case-insensitive)
                target = None
                for e in events:
                    if e.get("summary", "").lower() == summary.lower():
                        target = e
                        break

                if not target:
                    return None

                # Update times
                target["start"] = {"dateTime": new_start, "timeZone": "Europe/Bratislava"}
                target["end"] = {"dateTime": new_end, "timeZone": "Europe/Bratislava"}
                updated = service.events().update(
                    calendarId="primary",
                    eventId=target["id"],
                    body=target,
                ).execute()
                return updated

            result = await asyncio.to_thread(_find_and_update)
            if result is None:
                return {
                    "status": "error",
                    "error": f"Udalosť '{summary}' sa nenašla v {date_str}.",
                }

            return {
                "status": "success",
                "action": "update",
                "summary": summary,
                "new_start": new_start,
                "new_end": new_end,
                "message": f"Udalosť '{summary}' aktualizovaná na {new_start[:16].replace('T', ' o ')}.",
            }
        except HttpError as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _format_event(event: dict) -> dict[str, Any]:
        """Format a single event for display."""
        start = event.get("start", {})
        end = event.get("end", {})

        # All-day events use "date", timed events use "dateTime"
        start_str = start.get("dateTime", start.get("date", ""))
        end_str = end.get("dateTime", end.get("date", ""))

        # Extract local time — convert to Europe/Bratislava if needed
        start_time = ""
        if "T" in start_str:
            try:
                from datetime import datetime
                import zoneinfo
                dt = datetime.fromisoformat(start_str)
                local_tz = zoneinfo.ZoneInfo("Europe/Bratislava")
                local_dt = dt.astimezone(local_tz)
                start_time = local_dt.strftime("%H:%M")
                # Also fix start_str for date header
                start_str = local_dt.isoformat()
            except (ValueError, KeyError):
                # Fallback: just extract time as-is
                time_part = start_str.split("T")[1][:5]
                start_time = time_part

        return {
            "summary": event.get("summary", "(bez názvu)"),
            "start": start_str,
            "start_time": start_time,
            "end": end_str,
            "location": event.get("location", ""),
            "description": (event.get("description") or "")[:100],
            "all_day": "date" in start and "dateTime" not in start,
        }
