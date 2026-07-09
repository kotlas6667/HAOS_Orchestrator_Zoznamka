from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any

from app.config import settings
from app.tools.base import Tool
from app.tools.homeassistant_provider import (
    MockHomeAssistantProvider,
    RealHomeAssistantProvider,
)

# Domains eligible for each control action — used to narrow entity resolution.
_DOMAINS_BY_ACTION: dict[str, list[str]] = {
    "turn_on": ["light", "switch", "fan", "cover", "climate", "media_player", "input_boolean", "humidifier", "lock"],
    "turn_off": ["light", "switch", "fan", "cover", "climate", "media_player", "input_boolean", "humidifier", "lock"],
    "toggle": ["light", "switch", "fan", "cover", "input_boolean"],
    "trigger_automation": ["automation"],
}

_ACTION_VERBS: dict[str, str] = {
    "turn_on": "Zapol som",
    "turn_off": "Vypol som",
    "toggle": "Prepol som",
}


def _normalize(text: str) -> str:
    """Lowercase, strip diacritics and non-alphanumerics for fuzzy matching."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


class HomeAssistantTool(Tool):
    name = "homeassistant"
    description = "Controls Home Assistant — read entity states, call services, manage automations."

    def __init__(self) -> None:
        self.provider = self._create_provider()

    def _create_provider(self):
        if (
            getattr(settings, "ha_provider", "mock") == "real"
            and getattr(settings, "ha_url", None)
            and getattr(settings, "ha_token", None)
        ):
            return RealHomeAssistantProvider(
                base_url=settings.ha_url,
                token=settings.ha_token,
                timeout_sec=getattr(settings, "ha_timeout_sec", 10.0),
            )
        return MockHomeAssistantProvider()

    async def _resolve_entity(self, search: str, action: str) -> dict[str, Any]:
        """Find the real entity_id matching a free-text room/device description.

        Returns {"status": "resolved", "entity_id": ...} on a confident match,
        {"status": "clarify", "reply": ...} when several devices could match,
        or {"status": "error", "error": ...} when nothing matches.
        """
        states = await self.provider.get_states()
        if not states:
            return {
                "status": "error",
                "error": "Nepodarilo sa načítať zoznam zariadení z Home Assistant.",
            }

        try:
            aliases_by_entity = await self.provider.get_aliases()
        except AttributeError:
            aliases_by_entity = {}

        allowed_domains = _DOMAINS_BY_ACTION.get(action)
        candidates = (
            [s for s in states if s["entity_id"].split(".", 1)[0] in allowed_domains]
            if allowed_domains
            else states
        )

        q_norm = _normalize(search)
        q_tokens = set(q_norm.split())
        if not q_tokens:
            return {"status": "error", "error": "Nezadal si, ktoré zariadenie myslíš."}

        scored: list[tuple[float, dict]] = []
        for s in candidates:
            local = s["entity_id"].split(".", 1)[1] if "." in s["entity_id"] else s["entity_id"]
            entity_aliases = aliases_by_entity.get(s["entity_id"], [])
            text_norm = _normalize(
                f"{s.get('friendly_name', '')} {local.replace('_', ' ')} {' '.join(entity_aliases)}"
            )
            text_tokens = set(text_norm.split())
            overlap = len(q_tokens & text_tokens)
            ratio = difflib.SequenceMatcher(None, q_norm, text_norm).ratio()
            if overlap == 0 and ratio < 0.4:
                continue
            scored.append((overlap + ratio, s))

        if not scored:
            return {
                "status": "error",
                "error": f"Nenašiel som zariadenie zodpovedajúce '{search}'. Skús 'ukáž zariadenia' pre zoznam.",
            }

        scored.sort(key=lambda item: item[0], reverse=True)
        top_score, top = scored[0]
        runner_up_score = scored[1][0] if len(scored) > 1 else 0.0

        if len(scored) == 1 or (top_score - runner_up_score) >= 0.75:
            return {
                "status": "resolved",
                "entity_id": top["entity_id"],
                "friendly_name": top.get("friendly_name") or "",
            }

        top_candidates = scored[:5]
        lines = "\n".join(
            f"• {c.get('friendly_name') or c['entity_id']} ({c['entity_id']})"
            for _, c in top_candidates
        )
        return {
            "status": "clarify",
            "reply": f"Našiel som viacero zariadení zodpovedajúcich '{search}'. Ktoré myslíš?\n{lines}",
        }

    async def _resolve_if_needed(
        self, action: str, entity_id: str, search: str, prompt: str
    ) -> dict[str, Any]:
        """Ensure entity_id refers to a real entity, resolving from free text if not."""
        known = await self.provider.get_states()

        if not known:
            # No real entities to match against (e.g. mock provider) — pass through as-is.
            if not entity_id and search:
                entity_id = search
            return {"status": "resolved", "entity_id": entity_id, "friendly_name": ""}

        match = next((s for s in known if s["entity_id"] == entity_id), None) if entity_id else None
        if match:
            return {
                "status": "resolved",
                "entity_id": entity_id,
                "friendly_name": match.get("friendly_name") or "",
            }

        fallback_search = search or (entity_id.split(".", 1)[-1].replace("_", " ") if entity_id else prompt)
        return await self._resolve_entity(fallback_search, action)

    async def run(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "get_state")
        entity_id = ctx.get("entity_id", "")
        domain = ctx.get("domain", "")
        service = ctx.get("service", "")
        search = ctx.get("search", "")

        if action == "get_state":
            resolution = await self._resolve_if_needed(action, entity_id, search, prompt)
            if resolution["status"] != "resolved":
                return resolution
            entity_id = resolution["entity_id"]
            if not entity_id:
                return {"status": "error", "error": "Nezadal si, ktorý stav chceš zistiť."}
            return await self.provider.get_state(entity_id)

        if action == "list_entities":
            # Optional filter by domain or search term
            search = ctx.get("search", "")
            states = await self.provider.get_states()
            if search:
                search_lower = search.lower()
                states = [
                    s for s in states
                    if search_lower in s["entity_id"].lower()
                    or search_lower in s.get("friendly_name", "").lower()
                ]
            # Limit to 20 results to avoid flooding Discord
            return {
                "status": "success",
                "action": "list_entities",
                "entities": states[:20],
                "total": len(states),
            }

        if action == "call_service" and domain and service and entity_id:
            # Extract optional service data (e.g. brightness, temperature)
            service_data = {k: v for k, v in ctx.items() if k not in ("action", "domain", "service", "entity_id")}
            return await self.provider.call_service(domain, service, entity_id, **service_data)

        if action in ("turn_on", "turn_off", "toggle"):
            resolution = await self._resolve_if_needed(action, entity_id, search, prompt)
            if resolution["status"] != "resolved":
                return resolution
            entity_id = resolution["entity_id"]
            if not entity_id:
                return {"status": "error", "error": "Nezadal si, ktoré zariadenie myslíš."}
            domain = entity_id.split(".")[0] if "." in entity_id else "light"
            result = await self.provider.call_service(domain, action, entity_id)
            friendly_name = resolution.get("friendly_name")
            if friendly_name and result.get("status") == "success":
                verb = _ACTION_VERBS.get(action, "Vykonal som akciu na")
                result["message"] = f"{verb} {friendly_name}."
            return result

        if action == "list_automations":
            automations = await self.provider.get_automations()
            return {
                "status": "success",
                "action": "list_automations",
                "automations": automations,
                "total": len(automations),
            }

        if action == "trigger_automation":
            resolution = await self._resolve_if_needed(action, entity_id, search, prompt)
            if resolution["status"] != "resolved":
                return resolution
            entity_id = resolution["entity_id"]
            if not entity_id:
                return {"status": "error", "error": "Nezadal si, ktorú automatizáciu chceš spustiť."}
            return await self.provider.trigger_automation(entity_id)

        return {
            "status": "error",
            "error": f"Neznáma akcia '{action}' alebo chýbajúce parametre.",
            "available_actions": [
                "get_state", "list_entities", "call_service",
                "turn_on", "turn_off", "toggle",
                "list_automations", "trigger_automation",
            ],
        }
