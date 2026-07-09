from __future__ import annotations

import asyncio
import logging

import aiohttp

from homeassistant.components import conversation
from homeassistant.components.conversation import ConversationInput, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import ulid as ulid_util

from .const import CONF_URL

LOGGER = logging.getLogger(__name__)

_HISTORY_MAX_PAIRS = 10


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HaosOrchestratorConversationEntity(entry)])


class HaosOrchestratorConversationEntity(conversation.ConversationEntity):
    """Forwards Assist pipeline text to the HAOS Orchestrator and speaks its reply."""

    _attr_has_entity_name = True
    _attr_name = "HAOS Orchestrator"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._histories: dict[str, list[dict[str, str]]] = {}

    @property
    def supported_languages(self) -> list[str] | str:
        return MATCH_ALL

    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        base_url = self._entry.data[CONF_URL]
        conversation_id = user_input.conversation_id or ulid_util.ulid_now()
        history = self._histories.get(conversation_id, [])

        session = async_get_clientsession(self.hass)
        reply_text: str
        try:
            async with session.post(
                f"{base_url}/api/voice",
                json={"prompt": user_input.text, "history": history},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            LOGGER.error("HAOS Orchestrator request failed: %s", err)
            reply_text = "Orchestrátor momentálne neodpovedá."
        else:
            reply_text = data.get("reply") or "Neviem odpovedať."
            history.append({"role": "user", "content": user_input.text})
            history.append({"role": "assistant", "content": reply_text})
            self._histories[conversation_id] = history[-(_HISTORY_MAX_PAIRS * 2):]

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(reply_text)
        return ConversationResult(response=response, conversation_id=conversation_id)
