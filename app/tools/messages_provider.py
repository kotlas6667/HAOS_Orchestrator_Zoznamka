from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


class MessagesProvider(Protocol):
    async def send_message(self, destination: str, content: str) -> dict[str, Any]:
        """Send or simulate a message and return normalized delivery output."""


class MockMessagesProvider:
    async def send_message(self, destination: str, content: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "destination": destination,
            "action": "compose_message",
            "provider": "mock",
            "delivered": False,
            "preview": content,
            "next_step": "Set DISCORD_PROVIDER=discord_webhook and add DISCORD_WEBHOOK_URL.",
        }


class DiscordWebhookProvider:
    def __init__(self, *, webhook_url: str, username: str, timeout_sec: float) -> None:
        self._webhook_url = webhook_url
        self._username = username
        self._timeout_sec = timeout_sec
        self._webhook_id = self._extract_webhook_id(webhook_url)

    @staticmethod
    def _extract_webhook_id(webhook_url: str) -> str | None:
        parsed = urlparse(webhook_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "webhooks":
            return parts[2]
        return None

    async def send_message(self, destination: str, content: str) -> dict[str, Any]:
        payload = {
            "content": content,
            "username": self._username,
        }

        async with httpx.AsyncClient(timeout=self._timeout_sec, verify=False) as client:
            response = await client.post(self._webhook_url, json=payload)
            response.raise_for_status()

        return {
            "status": "live",
            "destination": destination,
            "action": "send_message",
            "provider": "discord_webhook",
            "delivered": True,
            "preview": content,
            "target_webhook_id": self._webhook_id,
        }