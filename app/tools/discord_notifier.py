from __future__ import annotations

import httpx
import os
from typing import Any
from dotenv import load_dotenv

load_dotenv()  # Načíta .env súbor

class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL not set in .env")

        # OpenAI API configuration
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_api_url = "https://api.openai.com/v1/chat/completions"
    async def send_message(self, content: str) -> dict[str, Any]:
        """Send a message to Discord via webhook."""
        payload = {"content": content}
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.webhook_url}?wait=true",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "message": "Notification sent to Discord",
                "message_id": data.get("id"),
            }

    async def send_email_summary(self, email_data: dict[str, Any]) -> dict[str, Any]:
        """Send a summarized email notification to Discord using GPT (in Slovak)."""
        summary = await self._summarize_email_with_ai(email_data)
        return await self.send_message(summary)

    async def _summarize_email_with_ai(self, email_data: dict[str, Any]) -> str:
        """Summarize email briefly - just sender and a few words about the content."""
        sender = email_data.get("from", "Unknown")
        subject = email_data.get("subject", "No Subject")
        body = email_data.get("body", "")

        # OpenAI API request
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Si asistent na stručné zhrnutie emailov. "
                        "Odpovedaj MAXIMÁLNE 5-8 slovami po slovensky o čom email je. "
                        "Žiadne formátovanie, žiadne úvody, len pár slov o obsahu. "
                        "Príklady: 'pozvánka na meeting zajtra o 10:00', 'faktúra za jún', "
                        "'potvrdenie objednávky', 'bezpečnostné upozornenie Google'."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Predmet: {subject}\n"
                        f"Obsah: {body[:500]}\n"
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            response = await client.post(self.openai_api_url, headers=headers, json=payload)
            response.raise_for_status()
            ai_summary = response.json()["choices"][0]["message"]["content"]

        # Extract just the sender name (before email in angle brackets)
        sender_name = sender.split("<")[0].strip().strip('"') or sender
        return f"📧 **{sender_name}** — {ai_summary.strip()}"


