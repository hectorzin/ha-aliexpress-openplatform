"""Create and add sensors to Home Assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import secrets
from typing import TYPE_CHECKING

from typing_extensions import override

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    _DataT,
)

from .const import COMMISSIONS, CONF_APIKEY

if TYPE_CHECKING:
    from decimal import Decimal

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Aliexpress OpenPlatform Component."""
    api_key = entry.data[CONF_APIKEY]
    coordinator = AliexpressOpenPlatformCoordinator(hass, api_key)
    await coordinator.async_config_entry_first_refresh()

    commission = AliexpressCommissionsSensor(coordinator)
    async_add_entities([commission])


class AliexpressOpenPlatformCoordinator(DataUpdateCoordinator):
    """Aliexpress OpenPlatform Coordinator."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize Coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Aliexpress OpenPlatform",
            update_interval=timedelta(minutes=5),
        )
        self._api_key = api_key
        self._user_data = {}
        self._global_data = {}
        self._need_update_entry = True

    @override
    async def _async_update_data(self) -> _DataT:
        # Add request to Server to get data.
        # For now, a simple random.
        return {
            COMMISSIONS: secrets.randbelow(10),
        }

    def _mark_need_update(self) -> None:
        self._need_update_entry = True


class AliexpressCommissionsSensor(SensorEntity, CoordinatorEntity):
    """Aliexpress Sensor."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize all values."""
        super().__init__(coordinator=coordinator)
        self._state = None
        self._attr_extra_state_attributes = {}
        self._attr_unique_id = "aliexpress_commissions"
        self.entity_description = SensorEntityDescription(
            name="Aliexpress Commissions",
            key="aliexpress_commissions",
            has_entity_name=True,
            icon="mdi:cash",
        )

    @property
    @override
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self._state

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        commission = self.coordinator.data[COMMISSIONS]
        self._state = commission
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        commission = self.coordinator.data[COMMISSIONS]
        self._state = commission
        self.async_write_ha_state()
