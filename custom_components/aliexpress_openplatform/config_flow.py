"""Config flow for Aliexpress OpenPlatform integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_APPKEY, CONF_APPSECRET

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow):
    """Config flow for Aliexpress OpenPlatform."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize values."""
        self._errors: Dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        self._errors = {}

        if user_input is not None:
            await self.async_set_unique_id("aliexpress")
            return self.async_create_entry(
                title="Aliexpress OpenPlatform", data=user_input
            )

        # Request api_key and api_secret in the form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APPKEY): str,
                    vol.Required(CONF_APPSECRET): str,
                }
            ),
            errors=self._errors,
        )
