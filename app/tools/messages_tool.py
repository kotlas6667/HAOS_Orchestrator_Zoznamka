from __future__ import annotations

from typing import Any

from app.config import Settings
from app.tools.base import Tool
from app.tools.messages_provider import DiscordWebhookProvider, MessagesProvider, MockMessagesProvider


class MessagesTool(Tool):
    name = "messages"
    description = "Prepares or sends message actions for chat platforms."

    def _build_provider(self) -> MessagesProvider:
        settings = Settings()
        provider_name = settings.discord_provider.strip().lower().replace(" ", "_")
        if provider_name in {"discord_webhook", "captain_hook", "webhook"} and settings.discord_webhook_url:
            return DiscordWebhookProvider(
                webhook_url=settings.discord_webhook_url,
                username=settings.discord_username,
                timeout_sec=settings.discord_timeout_sec,
            )
        return MockMessagesProvider()

    def _extract_destination(self, lowered_prompt: str, context: dict[str, Any] | None) -> str:
        if context and context.get("destination"):
            return str(context["destination"])
        if "discord" in lowered_prompt:
            return "discord"
        if "whatsapp" in lowered_prompt or "whatsup" in lowered_prompt:
            return "whatsapp"
        return "generic-chat"

    def _extract_content(self, prompt: str, context: dict[str, Any] | None) -> str:
        if context and context.get("message"):
            return str(context["message"])

        stripped_prompt = prompt.strip()
        separators = [":", "-", ";"]
        for separator in separators:
            if separator in stripped_prompt:
                _, candidate = stripped_prompt.split(separator, 1)
                candidate = candidate.strip()
                if candidate:
                    return candidate

        command_prefixes = [
            "posli spravu na discord",
            "send message to discord",
            "posli na discord",
            "discord",
        ]
        lowered_prompt = stripped_prompt.lower()
        for prefix in command_prefixes:
            if lowered_prompt.startswith(prefix):
                candidate = stripped_prompt[len(prefix):].strip(" .,!?")
                if candidate:
                    return candidate

        return stripped_prompt

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        lowered = prompt.lower()
        destination = self._extract_destination(lowered, context)
        content = self._extract_content(prompt, context)

        if destination != "discord":
            mock_result = await MockMessagesProvider().send_message(destination, content)
            mock_result["next_step"] = "Discord webhook is implemented. WhatsApp can be added as the next provider."
            return mock_result

        provider = self._build_provider()
        return await provider.send_message(destination, content)
