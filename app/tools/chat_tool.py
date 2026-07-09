from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.chat_provider import OpenAIChatProvider, MockChatProvider


class ChatTool(Tool):
    name = "chat"
    description = "General conversational fallback powered by GPT."

    def _build_provider(self):
        if settings.chat_provider == "openai" and settings.openai_api_key:
            return OpenAIChatProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                system_prompt=settings.chat_system_prompt,
            )
        return MockChatProvider()

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        if re.fullmatch(r"\s*[123](?:[.)]|\uFE0F\u20E3|\u20E3|\uFE0F)?\s*", prompt or ""):
            return {"status": "ignored", "reply": ""}

        provider = self._build_provider()
        history = (context or {}).get("history")
        result = await provider.complete(prompt, history=history)
        return result
