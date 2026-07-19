from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.gmail_provider import MockGmailProvider, RealGmailProvider
from app.tools.discord_notifier import DiscordNotifier
from app.tools import google_accounts

class GmailTool(Tool):
    name = "gmail"
    description = "Manages Gmail emails - fetch, send, label emails."

    _EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    _SUBJECT_PATTERN = re.compile(r"(?:subject|predmet)\s*[:=-]\s*([^\n.;]+)", re.IGNORECASE)
    _SENDER_PATTERN = re.compile(r"(?:from|od)\s+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
    _TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
    _DATE_PATTERN = re.compile(r"\b(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b")

    def __init__(self):
        self._providers: dict[str, RealGmailProvider] = {}
        self.provider = self._create_provider()
        self.discord = DiscordNotifier()

    def reload_providers(self) -> None:
        """Rebuild providers after OAuth connect/disconnect."""
        self._providers.clear()
        self.provider = self._create_provider()

    def _oauth_active(self) -> bool:
        if google_accounts.list_accounts():
            return google_accounts.is_enabled() or (settings.gmail_provider or "").lower() == "oauth"
        # Legacy: single token + provider=oauth
        if (settings.gmail_provider or "").lower() != "oauth":
            return False
        from pathlib import Path
        token = settings.gmail_token_pickle or "token.pickle"
        return Path(token).is_file()

    def _create_provider(self):
        """Create default provider (default account or legacy single token)."""
        accounts = google_accounts.list_accounts()
        if accounts and (
            google_accounts.is_enabled() or (settings.gmail_provider or "").lower() == "oauth"
        ):
            for acc in accounts:
                self._providers[acc["id"]] = RealGmailProvider(
                    credentials_path=str(google_accounts.find_credentials_path() or ""),
                    token_path=acc.get("token_path"),
                    user_email="me",
                    account_id=acc.get("id"),
                    allow_interactive_oauth=False,
                )
                # stash email on provider for tagging
                self._providers[acc["id"]]._account_email = acc.get("email")
            default = google_accounts.get_account()
            if default and default["id"] in self._providers:
                return self._providers[default["id"]]
            return next(iter(self._providers.values()))

        if self._oauth_active():
            # Legacy single-account token.pickle
            return RealGmailProvider(
                credentials_path=settings.gmail_credentials_json,
                token_path=settings.gmail_token_pickle,
                user_email=settings.gmail_user_email,
                allow_interactive_oauth=False,
            )

        return MockGmailProvider()

    def _resolve_provider(self, context: dict[str, Any]) -> Any:
        """Pick provider by account / email param, else default."""
        if not self._providers:
            return self.provider
        account_id = (context.get("account_id") or context.get("account") or "").strip()
        email = (context.get("email") or context.get("account_email") or "").strip()
        if account_id and account_id in self._providers:
            return self._providers[account_id]
        if email:
            acc = google_accounts.get_account(email=email)
            if acc and acc["id"] in self._providers:
                return self._providers[acc["id"]]
            # fuzzy: match local-part or full email in prompt param
            needle = email.lower()
            for acc in google_accounts.list_accounts():
                if needle in (acc.get("email") or "").lower() or needle in (acc.get("label") or "").lower():
                    if acc["id"] in self._providers:
                        return self._providers[acc["id"]]
        return self.provider

    def all_real_providers(self) -> list[RealGmailProvider]:
        if self._providers:
            return list(self._providers.values())
        if isinstance(self.provider, RealGmailProvider):
            return [self.provider]
        return []

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
        provider = self._resolve_provider(ctx)
        account_email = getattr(provider, "account_email", None) or getattr(provider, "_account_email", None)

        oauth_on = self._oauth_active() and not isinstance(provider, MockGmailProvider)
        base: dict[str, Any] = {
            "status": "success" if oauth_on else "mock",
            "action": action,
            "provider": "oauth" if oauth_on else "mock",
            "account": account_email,
        }

        if action == "accounts":
            accounts = google_accounts.list_accounts()
            return {
                **base,
                "status": "success",
                "accounts": [
                    {"email": a.get("email"), "label": a.get("label"), "is_default": a.get("is_default")}
                    for a in accounts
                ],
                "total": len(accounts),
            }

        if action == "send":
            if not recipient:
                return {**base, "status": "error", "error": "No recipient email found in prompt"}
            body = ctx.get("body", prompt)
            response = await provider.send_email(recipient, subject or "Message", body)
            return {**base, **response, "recipient": recipient, "subject": subject or "Message"}

        if action == "count":
            # Across all accounts when no specific account requested
            if self._providers and not (ctx.get("account") or ctx.get("account_id") or ctx.get("email")):
                total = 0
                per_account = []
                for pid, prov in self._providers.items():
                    response = await prov.get_emails(query=query, max_results=50)
                    n = len(response.get("emails", []))
                    total += n
                    per_account.append({
                        "account": getattr(prov, "_account_email", pid),
                        "count": n,
                    })
                return {**base, "count": total, "query": query, "per_account": per_account}
            response = await provider.get_emails(query=query, max_results=50)
            count = len(response.get("emails", []))
            return {**base, "count": count, "query": query}

        # Default: fetch
        response = await provider.get_emails(query=query, max_results=max_results)
        emails = response.get("emails", [])
        if account_email:
            for mail in emails:
                mail.setdefault("account", account_email)
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

