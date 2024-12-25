"""Create and add Aliexpress sensors to Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .aliexpress_coordinator import AliexpressOpenPlatformCoordinator
from .const import DOMAIN

if TYPE_CHECKING:
    from datetime import date, datetime
    from decimal import Decimal

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType


_LOGGER = logging.getLogger(__name__)
CURRENCY_USD = "$"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Aliexpress sensors from a configuration entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AliexpressTotalCommissionsSensor(coordinator),
            AliexpressOrderCountSensor(coordinator),
            AliexpressTotalPaidSensor(coordinator),
            AliexpressAffiliateCommissionsSensor(coordinator),
            AliexpressInfluencerCommissionsSensor(coordinator),
            AliexpressLastOrderSensor(coordinator),
        ]
    )


class AliexpressSensor(
    SensorEntity, CoordinatorEntity[AliexpressOpenPlatformCoordinator]
):
    """Aliexpress Base sensor class."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the values."""
        self._coordinator = None
        super().__init__(coordinator)
        self._state = None
        self._last_reset = None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information for this sensor."""
        return {
            "identifiers": {(DOMAIN, "aliexpress_device")},
            "name": "Aliexpress OpenPlatform",
            "manufacturer": "Aliexpress",
            "model": "OpenPlatform API",
            "configuration_url": "https://portals.aliexpress.com",
        }

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the sensor's state."""
        return self._state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        self._last_reset = self.coordinator.get_value("last_reset")

    @property
    def last_reset(self) -> datetime | None:
        """Return the last reset sensor's date."""
        return self._last_reset


class AliexpressTotalCommissionsSensor(AliexpressSensor):
    """Sensor for tracking total commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total commissions' sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_commissions"
        self.entity_description = SensorEntityDescription(
            name="Total Commissions",
            key="aliexpress_total_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=CURRENCY_USD,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._state = self.coordinator.data["total_commissions"]
        self.async_write_ha_state()


class AliexpressAffiliateCommissionsSensor(AliexpressSensor):
    """Sensor for tracking total affiliate commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the affiliate commissions sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_affiliate_commissions"
        self.entity_description = SensorEntityDescription(
            name="Affiliate Commissions",
            key="aliexpress_affiliate_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=CURRENCY_USD,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._state = self.coordinator.data["affiliate_commissions"]
        self.async_write_ha_state()


class AliexpressInfluencerCommissionsSensor(AliexpressSensor):
    """Sensor for tracking total influencer commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the influencer commissions sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_influencer_commissions"
        self.entity_description = SensorEntityDescription(
            name="Influencer Commissions",
            key="aliexpress_influencer_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=CURRENCY_USD,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._state = self.coordinator.data["influencer_commissions"]
        self.async_write_ha_state()


class AliexpressOrderCountSensor(AliexpressSensor):
    """Sensor for tracking total number of orders."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total orders' sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_orders"
        self.entity_description = SensorEntityDescription(
            name="Total Order Count",
            key="aliexpress_total_orders",
            icon="mdi:package-variant-closed",
            state_class=SensorStateClass.TOTAL,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Get the update from coordinator."""
        super()._handle_coordinator_update()
        self._state = self.coordinator.data["total_orders"]
        self.async_write_ha_state()


class AliexpressTotalPaidSensor(AliexpressSensor):
    """Sensor for tracking total amount paid by customers."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total paid sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_paid"
        self.entity_description = SensorEntityDescription(
            name="Total Paid by Customers",
            key="aliexpress_total_paid",
            icon="mdi:currency-usd",
            state_class=SensorStateClass.TOTAL,
            native_unit_of_measurement=CURRENCY_USD,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()
        self._state = self.coordinator.data["total_paid"]
        self.async_write_ha_state()


class AliexpressLastOrderSensor(AliexpressSensor):
    """Sensor for tracking the last processed order."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Last Order sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_last_order"
        self.entity_description = SensorEntityDescription(
            name="Last Order",
            key="aliexpress_last_order",
            icon="mdi:history",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=CURRENCY_USD,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._state = self.coordinator.data["last_order"]["total_commission"]
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes for the last order."""
        if not self.coordinator.data:
            return None

        last_order_data = self.coordinator.get_value("last_order")
        if not last_order_data:
            return None

        return {
            "order_platform": last_order_data.get("order_platform"),
            "paid_time": last_order_data.get("paid_time"),
            "total_paid_amount": last_order_data.get("total_paid_amount"),
        }
