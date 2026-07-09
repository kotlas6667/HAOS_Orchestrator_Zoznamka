from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute tool logic and return structured data."""


class ChatProvider(Protocol):
    async def complete(self, prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Generate a chat response and return normalized output."""
