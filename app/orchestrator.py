from __future__ import annotations

import logging

from app.router import llm_route
from app.schemas import PromptResponse, ToolExecution
from app.tools.registry import build_tool_registry

LOGGER = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self) -> None:
        self.tools = build_tool_registry()

    async def handle_prompt(self, prompt: str, history: list[dict[str, str]] | None = None) -> PromptResponse:
        routing = await llm_route(prompt, history=history)

        tool_name = routing.get("tool", "chat")
        params = routing.get("params", {})
        reason = routing.get("reason", "")

        if tool_name not in self.tools:
            LOGGER.warning("LLM routed to unknown tool '%s', falling back to chat", tool_name)
            tool_name = "chat"
            params = {}

        LOGGER.info("Routing to '%s' with params %s — %s", tool_name, params, reason)

        tool = self.tools[tool_name]

        # Pass conversation history to chat tool
        context = params if params else None
        if tool_name == "chat" and history:
            context = context or {}
            context["history"] = history

        result = await tool.run(prompt, context=context)

        execution = ToolExecution(
            tool=tool.name,
            reason=reason,
            result=result,
        )

        summary = f"{tool.name}:run"
        return PromptResponse(route=tool_name, summary=summary, executions=[execution])
