from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import ChatProvider


class OpenAIChatProvider(ChatProvider):
    name = "openai"
    description = "OpenAI GPT chat provider"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", system_prompt: str = ""):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt

    async def complete(self, prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model,
            "messages": messages,
        }

        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
            )
            response.raise_for_status()
            result = response.json()

        return {
            "status": "live",
            "action": "chat_completion",
            "provider": "openai",
            "model": self.model,
            "reply": result["choices"][0]["message"]["content"],
        }


class MockChatProvider:
    async def complete(self, prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {
            "status": "mock",
            "action": "chat_completion",
            "provider": "mock",
            "reply": "Chat provider nie je nakonfigurovaný. Nastav CHAT_PROVIDER=openai a OPENAI_API_KEY v .env.",
            "echo": prompt,
        }
