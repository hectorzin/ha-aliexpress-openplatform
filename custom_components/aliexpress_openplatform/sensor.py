"""Create and add sensors to Home Assistant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING

from aliexpress_api import AliexpressApi, models

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_APPKEY, CONF_APPSECRET, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Aliexpress sensors from a configuration entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AliexpressCommissionsSensor(coordinator),
            AliexpressOrderCountSensor(coordinator),
            AliexpressTotalPaidSensor(coordinator),
        ]
    )


class AliexpressOpenPlatformCoordinator(DataUpdateCoordinator):
    """Coordinator for managing Aliexpress order data updates."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator with Aliexpress API credentials and settings."""
        super().__init__(
            hass,
            _LOGGER,
            name="Aliexpress OpenPlatform",
            update_interval=timedelta(minutes=5),
        )
        app_key = config_entry.data[CONF_APPKEY]
        app_secret = config_entry.data[CONF_APPSECRET]
        self._client = AliexpressApi(
            app_key, app_secret, models.Language.ES, models.Currency.EUR
        )
        self._last_orders = (
            set()
        )  # Track unique processed order IDs to prevent duplicates

    async def _async_update_data(self) -> dict:
        """Fetch order data from Aliexpress API and process it."""
        try:
            # Define date range for orders (last 180 days)
            now = datetime.now(tz=timezone.utc)
            start_time = (now - timedelta(days=180)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")

            # Fetch orders via Aliexpress API
            response = await self.hass.async_add_executor_job(
                self._client.get_order_list,  # pylint: disable=no-member
                "Payment Completed",
                start_time,
                end_time,
                [
                    "order_number",
                    "paid_amount",
                    "estimated_paid_commission",
                    "created_time",
                ],
                "global",
                None,
                50,
            )
            _LOGGER.debug("Response from Aliexpress API: %s", response)

        except KeyError as key_err:
            error_message = f"Unexpected data structure: {key_err}"
            _LOGGER.exception(error_message)
            raise UpdateFailed(error_message) from key_err

        except ValueError as val_err:
            error_message = f"Data parsing error: {val_err}"
            _LOGGER.exception(error_message)
            raise UpdateFailed(error_message) from val_err

        except Exception as err:
            error_message = "An unexpected error occurred"
            _LOGGER.exception(error_message)
            raise UpdateFailed(error_message) from err
        # Process new orders that have not been seen before
        new_orders = [
            order
            for order in response.orders.order
            if order.order_number not in self._last_orders
        ]
        self._last_orders.update(order.order_number for order in new_orders)

        # Calculate total values for the fetched orders
        total_commissions = sum(
            float(order.estimated_paid_commission) for order in new_orders
        )
        total_paid = sum(float(order.paid_amount) for order in new_orders)
        total_orders = len(new_orders)

        return {
            "total_orders": total_orders,
            "total_paid": total_paid,
            "total_commissions": total_commissions,
        }


class AliexpressCommissionsSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total commissions sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_commissions"
        self.entity_description = SensorEntityDescription(
            name="Total Commissions",
            key="aliexpress_total_commissions",
            icon="mdi:cash-multiple",
        )

    @property
    def native_value(self) -> float:
        """Return the total commissions if data is available."""
        return (
            self.coordinator.data.get("total_commissions")
            if self.coordinator.data
            else None
        )


class AliexpressOrderCountSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total number of orders."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total orders sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_orders"
        self.entity_description = SensorEntityDescription(
            name="Total Order Count",
            key="aliexpress_total_orders",
            icon="mdi:package-variant-closed",
        )

    @property
    def native_value(self) -> float:
        """Return the total number of orders if data is available."""
        return (
            self.coordinator.data.get("total_orders") if self.coordinator.data else None
        )


class AliexpressTotalPaidSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total amount paid by customers."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total paid sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_paid"
        self.entity_description = SensorEntityDescription(
            name="Total Paid by Customers",
            key="aliexpress_total_paid",
            icon="mdi:currency-usd",
        )

    @property
    def native_value(self) -> float:
        """Return the total amount paid by customers if data is available."""
        return (
            self.coordinator.data.get("total_paid") if self.coordinator.data else None
        )
