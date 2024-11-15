"""Config flow for Aliexpress OpenPlatform integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_APIKEY, DOMAIN

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Aliexpress OpenPlatform."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize values."""
        self._errors = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Config flow for Aliexpress Openplatform."""
        self._errors = {}

        if user_input is not None:
            await self.async_set_unique_id("aliexpress")
            return self.async_create_entry(title="Aliexpress Test", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APIKEY): str,
                }
            ),
            errors=self._errors,
        )
