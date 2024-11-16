"""Create and add Aliexpress sensors to Home Assistant."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any, Mapping

from aliexpress_api import AliexpressApi, models

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
        app_key = config_entry.data[CONF_APP_KEY]
        app_secret = config_entry.data[CONF_APP_SECRET]
        self._client = AliexpressApi(
            app_key, app_secret, models.Language.ES, models.Currency.EUR
        )

    async def _async_update_data(self) -> dict:
        """Fetch order data from Aliexpress API and process it."""
        try:
            # Define date range for orders (last 180 days)
            # Fetch orders via Aliexpress API

            now = datetime.now(tz=timezone.utc)
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            response = await self._get_data(start_time, 0)
            orders = response.orders.order

            total_paid = sum(order.paid_amount for order in orders)
            total_commissions = sum(order.estimated_paid_commission for order in orders)

            while response.current_page_no < response.total_page_no - 1:
                response = await self._get_data(
                    start_time, response.current_page_no + 1
                )
                orders = response.orders.order
                total_paid += sum(order.paid_amount for order in orders)
                total_commissions += sum(
                    order.estimated_paid_commission for order in orders
                )

        except Exception as err:
            error_message = "An unexpected error occurred"
            _LOGGER.exception(error_message)
            raise UpdateFailed(error_message) from err

        return {
            "total_paid": total_paid / 100.0,
            "total_commissions": total_commissions / 100.0,
            "total_orders": response.total_record_count,
            "last_reset": start_time,
        }

    async def _get_data(
        self, start_time: datetime, page: int
    ) -> models.OrderListResponse:
        now = datetime.now(tz=timezone.utc)
        return await self.hass.async_add_executor_job(
            self._client.get_order_list,  # pylint: disable=no-member
            "Payment Completed",
            start_time.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            [
                "order_number",
                "paid_amount",
                "estimated_paid_commission",
                "created_time",
            ],
            "global",
            page,
            50,
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
