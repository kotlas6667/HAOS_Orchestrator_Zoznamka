from __future__ import annotations

import asyncio

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_URL, DEFAULT_URL, DOMAIN


async def _validate_url(hass, url: str) -> str | None:
    """Return an error code if the URL is unreachable, else None."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"{url}/health", timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status != 200:
                return "cannot_connect"
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return "cannot_connect"
    return None


class HaosOrchestratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the HAOS Orchestrator conversation agent."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            error = await _validate_url(self.hass, url)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="HAOS Orchestrator", data={CONF_URL: url})

        schema = vol.Schema({vol.Required(CONF_URL, default=DEFAULT_URL): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HaosOrchestratorOptionsFlow:
        return HaosOrchestratorOptionsFlow(config_entry)


class HaosOrchestratorOptionsFlow(config_entries.OptionsFlow):
    """Lets the user change the Orchestrator URL without deleting the integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            error = await _validate_url(self.hass, url)
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data={**self.config_entry.data, CONF_URL: url}
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_URL, default=self.config_entry.data.get(CONF_URL, DEFAULT_URL)
                ): str
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
