from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.gmail_provider import MockGmailProvider, RealGmailProvider
from app.tools.discord_notifier import DiscordNotifier

class GmailTool(Tool):
    name = "gmail"
    description = "Manages Gmail emails - fetch, send, label emails."

    _EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    _SUBJECT_PATTERN = re.compile(r"(?:subject|predmet)\s*[:=-]\s*([^\n.;]+)", re.IGNORECASE)
    _SENDER_PATTERN = re.compile(r"(?:from|od)\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
    _TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
    _DATE_PATTERN = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")

    def __init__(self):
        self.provider = self._create_provider()
        self.discord = DiscordNotifier()

    def _create_provider(self):
        """Create appropriate Gmail provider based on config."""
        if settings.gmail_provider == "mock":
            return MockGmailProvider()

        if settings.gmail_provider == "oauth":
            return RealGmailProvider(
                credentials_path=settings.gmail_credentials_json,
                token_path=settings.gmail_token_pickle,
                user_email=settings.gmail_user_email,
            )

        # Default to mock if provider not recognized
        return MockGmailProvider()

    def _extract_subject(self, prompt: str) -> str | None:
        match = self._SUBJECT_PATTERN.search(prompt)
        if not match:
            return None
        return match.group(1).strip()

    def _extract_sender(self, prompt: str) -> str | None:
        sender_match = self._SENDER_PATTERN.search(prompt)
        if sender_match:
            return sender_match.group(1).strip()
        generic_match = self._EMAIL_PATTERN.search(prompt)
        if generic_match:
            return generic_match.group(0).strip()
        return None

    def _extract_recipient(self, prompt: str) -> str | None:
        """Extract recipient email from prompt."""
        emails = self._EMAIL_PATTERN.findall(prompt)
        if emails:
            return emails[0]
        return None

    def _extract_meeting_details(self, prompt: str) -> dict[str, Any]:
        attendees = self._EMAIL_PATTERN.findall(prompt)
        time_match = self._TIME_PATTERN.search(prompt)
        date_match = self._DATE_PATTERN.search(prompt)

        proposed_time = None
        if time_match:
            proposed_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}"

        proposed_date = date_match.group(1) if date_match else None

        return {
            "attendees": attendees,
            "proposed_date": proposed_date,
            "proposed_time": proposed_time,
        }

    def _detect_action(self, lowered: str) -> str:
        # Send email
        if any(token in lowered for token in [
            "send", "posli", "pošli", "napíš", "napís", "napí", "odošli", "odosli",
        ]):
            return "send_email"
        # Fetch unread
        if any(token in lowered for token in [
            "unread", "neprečítan", "neprecitan", "neprečitan",
            "check", "skontrol", "skontroluj",
        ]):
            return "fetch_unread"
        # Fetch latest / show email
        if any(token in lowered for token in [
            "zobraz", "ukáž", "ukaz", "posledn", "latest", "recent",
            "inbox", "doručen", "prečítaj", "precitaj", "prečitaj",
            "otvor", "read",
        ]):
            return "fetch_latest"
        # Meeting
        if any(token in lowered for token in [
            "meeting", "schodz", "schôdz", "stretnut", "stretk",
            "kalendar", "calendar", "call", "hovor",
        ]):
            return "suggest_meeting"
        # Importance
        if any(token in lowered for token in [
            "dôležit", "dolezit", "important", "priority", "priorit", "urgentné", "urgentne",
        ]):
            return "importance_check"
        # Summarize
        if any(token in lowered for token in [
            "zhrň", "zhrn", "summary", "summarize", "sumariz", "sumár", "sumar",
        ]):
            return "summarize_email"
        # Reply / draft
        if any(token in lowered for token in [
            "odpoved", "reply", "draft", "koncept",
        ]):
            return "draft_reply"
        # Count / how many emails
        if any(token in lowered for token in [
            "kolko", "koľko", "pocet", "počet", "count", "how many", "dnes", "today",
        ]):
            return "fetch_count"
        # Default: show latest email (safest fallback for gmail route)
        return "fetch_latest"

    def _importance_from_prompt(self, lowered: str) -> str:
        if any(token in lowered for token in ["urgent", "asap", "incident", "critical", "kritic"]):
            return "high"
        if any(token in lowered for token in ["later", "ked budes", "nizka", "low"]):
            return "low"
        return "medium"

    def _summarize_email(self, email_data: dict[str, Any]) -> str:
        """Summarize email into one sentence for Discord."""
        sender = email_data.get("from", "Unknown")
        subject = email_data.get("subject", "No Subject")
        body = email_data.get("body", "")[:100]  # First 100 chars
        return f"📧 **New Email** from {sender}: *{subject}* | {body}..."

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "fetch")
        query = ctx.get("query", "")
        max_results = int(ctx.get("max_results", 10))
        recipient = ctx.get("recipient") or self._extract_recipient(prompt)
        subject = ctx.get("subject") or self._extract_subject(prompt)

        base: dict[str, Any] = {
            "status": "success" if settings.gmail_provider != "mock" else "mock",
            "action": action,
            "provider": settings.gmail_provider,
        }

        if action == "send":
            if not recipient:
                return {**base, "status": "error", "error": "No recipient email found in prompt"}
            body = ctx.get("body", prompt)
            response = await self.provider.send_email(recipient, subject or "Message", body)
            return {**base, **response, "recipient": recipient, "subject": subject or "Message"}

        if action == "count":
            response = await self.provider.get_emails(query=query, max_results=50)
            count = len(response.get("emails", []))
            return {**base, "count": count, "query": query}

        # Default: fetch
        response = await self.provider.get_emails(query=query, max_results=max_results)
        emails = response.get("emails", [])
        if not emails:
            return {**base, "emails": [], "query": query}
        if max_results == 1:
            latest = emails[0]
            return {
                **base,
                "from": latest.get("from", "Neznamy"),
                "subject": latest.get("subject", "Bez predmetu"),
                "date": latest.get("date", ""),
                "body_preview": latest.get("body", "")[:500],
            }
        return {**base, "emails": emails, "total": len(emails), "query": query}

