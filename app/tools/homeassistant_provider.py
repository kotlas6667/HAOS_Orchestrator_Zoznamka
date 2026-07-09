from __future__ import annotations

import time
from typing import Any, Protocol

import aiohttp
import httpx


class HomeAssistantProvider(Protocol):
    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Get current state of an entity."""

    async def get_states(self) -> list[dict[str, Any]]:
        """Get all entity states."""

    async def get_aliases(self) -> dict[str, list[str]]:
        """Get entity_id -> voice aliases (from the HA entity registry)."""

    async def call_service(self, domain: str, service: str, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Call a HA service (e.g. turn_on, turn_off, toggle)."""

    async def get_automations(self) -> list[dict[str, Any]]:
        """List all automations."""

    async def trigger_automation(self, entity_id: str) -> dict[str, Any]:
        """Manually trigger an automation."""


class MockHomeAssistantProvider:
    async def get_state(self, entity_id: str) -> dict[str, Any]:
        return {
            "status": "mock",
            "entity_id": entity_id,
            "state": "unavailable",
            "next_step": "Set HA_PROVIDER=real and configure HA_URL + HA_TOKEN in .env",
        }

    async def get_states(self) -> list[dict[str, Any]]:
        return []

    async def get_aliases(self) -> dict[str, list[str]]:
        return {}

    async def call_service(self, domain: str, service: str, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "mock",
            "action": f"{domain}.{service}",
            "entity_id": entity_id,
            "next_step": "Set HA_PROVIDER=real and configure HA_URL + HA_TOKEN in .env",
        }

    async def get_automations(self) -> list[dict[str, Any]]:
        return []

    async def trigger_automation(self, entity_id: str) -> dict[str, Any]:
        return {"status": "mock", "entity_id": entity_id}


class RealHomeAssistantProvider:
    """Communicates with Home Assistant REST API."""

    _ALIASES_CACHE_TTL_SEC = 300.0

    def __init__(self, *, base_url: str, token: str, timeout_sec: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout_sec
        self._aliases_cache: dict[str, list[str]] | None = None
        self._aliases_cache_at: float = 0.0

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """Get state of a single entity."""
        url = f"{self._base_url}/api/states/{entity_id}"
        async with httpx.AsyncClient(verify=False, timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers)
            if response.status_code == 404:
                return {
                    "status": "error",
                    "entity_id": entity_id,
                    "error": f"Entita '{entity_id}' neexistuje v Home Assistant.",
                }
            response.raise_for_status()
            data = response.json()

        return {
            "status": "success",
            "entity_id": data.get("entity_id"),
            "state": data.get("state"),
            "friendly_name": data.get("attributes", {}).get("friendly_name", entity_id),
            "attributes": data.get("attributes", {}),
            "last_changed": data.get("last_changed"),
        }

    async def get_states(self) -> list[dict[str, Any]]:
        """Get all entity states (for search/listing)."""
        url = f"{self._base_url}/api/states"
        async with httpx.AsyncClient(verify=False, timeout=self._timeout) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            data = response.json()

        return [
            {
                "entity_id": entity.get("entity_id"),
                "state": entity.get("state"),
                "friendly_name": entity.get("attributes", {}).get("friendly_name", ""),
            }
            for entity in data
        ]

    async def get_aliases(self) -> dict[str, list[str]]:
        """Get entity_id -> voice aliases from the HA entity registry (WebSocket API only)."""
        now = time.monotonic()
        if self._aliases_cache is not None and (now - self._aliases_cache_at) < self._ALIASES_CACHE_TTL_SEC:
            return self._aliases_cache

        ws_url = self._base_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"
        aliases: dict[str, list[str]] = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    ws_url, timeout=self._timeout, ssl=False
                ) as ws:
                    await ws.receive_json()  # auth_required
                    await ws.send_json({"type": "auth", "access_token": self._token})
                    auth_result = await ws.receive_json()
                    if auth_result.get("type") != "auth_ok":
                        return self._aliases_cache or {}

                    await ws.send_json({"id": 1, "type": "config/entity_registry/list"})
                    while True:
                        result = await ws.receive_json()
                        if result.get("id") == 1:
                            if result.get("success"):
                                for entry in result.get("result", []):
                                    entity_aliases = entry.get("aliases") or []
                                    if entity_aliases:
                                        aliases[entry["entity_id"]] = entity_aliases
                            break
        except (aiohttp.ClientError, TimeoutError, OSError):
            return self._aliases_cache or {}

        self._aliases_cache = aliases
        self._aliases_cache_at = now
        return aliases

    async def call_service(self, domain: str, service: str, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        """Call a Home Assistant service."""
        url = f"{self._base_url}/api/services/{domain}/{service}"
        payload: dict[str, Any] = {"entity_id": entity_id}
        payload.update(kwargs)

        async with httpx.AsyncClient(verify=False, timeout=self._timeout) as client:
            response = await client.post(url, headers=self._headers, json=payload)
            response.raise_for_status()

        # NOTE: HA's "changed states" response body is not a reliable success signal —
        # many integrations return an empty list even when the action genuinely took
        # effect (e.g. state updates arriving slightly after the service call returns).
        # A 2xx HTTP status is HA's actual acknowledgement that the service was called.
        local_name = entity_id.split(".", 1)[-1].replace("_", " ") if "." in entity_id else entity_id
        return {
            "status": "success",
            "action": f"{domain}.{service}",
            "entity_id": entity_id,
            "message": f"Služba {domain}.{service} bola zavolaná na {local_name}.",
        }

    async def get_automations(self) -> list[dict[str, Any]]:
        """List all automations."""
        states = await self.get_states()
        return [
            s for s in states
            if s["entity_id"].startswith("automation.")
        ]

    async def trigger_automation(self, entity_id: str) -> dict[str, Any]:
        """Trigger an automation manually."""
        return await self.call_service("automation", "trigger", entity_id)
