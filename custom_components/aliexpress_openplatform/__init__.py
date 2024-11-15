"""Aliexpress OpenPlatform Integration.

This module sets up the integration and handles its configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.const import Platform

from .const import DOMAIN
from .sensor import AliexpressOpenPlatformCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Aliexpress OpenPlatform from a config entry."""
    # Check if the coordinator already exists to avoid double setup
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if config_entry.entry_id in hass.data[DOMAIN]:
        return False

    # Initialize the coordinator
    coordinator = AliexpressOpenPlatformCoordinator(hass, config_entry)
    hass.data[DOMAIN][config_entry.entry_id] = coordinator

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    await coordinator.async_config_entry_first_refresh()

    # Register the listener for option updates
    config_entry.async_on_unload(config_entry.add_update_listener(_async_update_options))

    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload an Aliexpress OpenPlatform config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)
    return unload_ok

async def _async_update_options(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    # Update entry replacing data with new options
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, **config_entry.options}
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
