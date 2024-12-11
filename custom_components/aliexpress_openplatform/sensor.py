"""Create and add Aliexpress sensors to Home Assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any, Mapping

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CURRENCY_EURO
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .aliexpress_api_handler import get_order_list
from .const import CONF_APP_KEY, CONF_APP_SECRET, DOMAIN

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
        self.config_entry = config_entry

    async def _async_update_data(self) -> dict:
        """Fetch order data from Aliexpress API and process it."""
        try:
            now = datetime.now(tz=timezone.utc)
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            app_key = self.config_entry.data[CONF_APP_KEY]
            app_secret = self.config_entry.data[CONF_APP_SECRET]

            response = await self._get_data(app_key, app_secret, start_time, 1)

            orders = response.get("orders", {}).get("order", [])

            if not isinstance(orders, list):
                _LOGGER.error(
                    "Se esperaba una lista en 'orders.order', pero se recibió: %s",
                    type(orders),
                )
                orders = []

            total_paid = sum(int(order.get("paid_amount", 0)) for order in orders)
            total_commissions = sum(
                int(order.get("estimated_paid_commission", 0)) for order in orders
            )

            while int(response.get("current_page_no", 0)) < int(
                response.get("total_page_no", 0)
            ):
                response = await self._get_data(
                    app_key,
                    app_secret,
                    start_time,
                    int(response.get("current_page_no", 0)) + 1,
                )

                orders = response.get("orders", {}).get("order", [])

                if not isinstance(orders, list):
                    _LOGGER.error(
                        "Se esperaba una lista en 'orders.order', pero se recibió: %s",
                        type(orders),
                    )
                    orders = []

                total_paid += sum(order.get("paid_amount", 0) for order in orders)
                total_commissions += sum(
                    order.get("estimated_paid_commission", 0) for order in orders
                )

        except Exception as err:
            error_message = "An unexpected error occurred"
            _LOGGER.exception("%s. Respuesta completa: %s", error_message, response)
            raise UpdateFailed(error_message) from err

        return {
            "total_paid": total_paid / 100.0,
            "total_commissions": total_commissions / 100.0,
            "total_orders": response.get("total_record_count", 0),
            "last_reset": start_time,
        }

    async def _get_data(
        self, app_key: str, app_secret: str, start_time: datetime, page: int
    ) -> dict[str, Any]:
        """Fetch data from AliExpress API."""
        now = datetime.now(tz=timezone.utc)

        query_params = {
            "status": "Payment Completed",
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        pagination = {"page_no": page, "page_size": 50}

        return await self.hass.async_add_executor_job(
            get_order_list,
            app_key,
            app_secret,
            query_params,
            pagination,
        )


class AliexpressCommissionsSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the Total commissions' sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_total_commissions"
        self.entity_description = SensorEntityDescription(
            name="Total Commissions",
            key="aliexpress_total_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=CURRENCY_EURO,
        )

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the total commissions if data is available."""
        return (
            self.coordinator.data.get("total_commissions")
            if self.coordinator.data
            else None
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "last_reset": self.coordinator.data.get("last_reset")
            if self.coordinator.data
            else None,
        }


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
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the total number of orders if data is available."""
        return (
            self.coordinator.data.get("total_orders") if self.coordinator.data else None
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "last_reset": self.coordinator.data.get("last_reset")
            if self.coordinator.data
            else None,
        }


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
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=CURRENCY_EURO,
        )

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the total amount paid by customers if data is available."""
        return (
            self.coordinator.data.get("total_paid") if self.coordinator.data else None
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "last_reset": self.coordinator.data.get("last_reset")
            if self.coordinator.data
            else None,
        }
