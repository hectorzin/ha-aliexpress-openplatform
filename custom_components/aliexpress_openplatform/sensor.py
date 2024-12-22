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
            AliexpressCommissionsSensor(coordinator),
            AliexpressOrderCountSensor(coordinator),
            AliexpressTotalPaidSensor(coordinator),
            AliexpressAffiliateCommissionsSensor(coordinator),
            AliexpressInfluencerCommissionsSensor(coordinator),
            AliexpressLastOrderSensor(coordinator),
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
        self._last_order_id: int | None = None
        self._last_end_time: datetime | None = None
        self._last_order_data: dict[str, Any] | None = None
        self._accumulated_totals = {  # accumulated data until last reading
            "affiliate_commissions": 0.0,
            "influencer_commissions": 0.0,
            "total_paid": 0.0,
            "total_commissions": 0.0,
            "total_orders": 0.0,
        }

    def _calculate_last_order(self, orders: list[dict]) -> dict[str, Any] | None:
        """Calculate the details for the last order group."""
        if not orders:
            return None

        # getting `paid_time` of first order (it's the last order arrived)
        last_paid_time = orders[0].get("paid_time", "")
        order_platform = orders[0].get("order_platform", "unknown")

        # filtering orthers that share same `paid_time`
        last_orders = [
            order for order in orders if order.get("paid_time") == last_paid_time
        ]

        total_commission = sum(
            int(order.get("estimated_paid_commission", 0))
            + int(order.get("new_buyer_bonus_commission", 0))
            for order in last_orders
        )
        total_paid_amount = sum(
            int(order.get("paid_amount", 0)) for order in last_orders
        )

        platforms = {order.get("order_platform") for order in last_orders}
        order_platform = "mixed" if len(platforms) > 1 else platforms.pop()

        return {
            "total_commission": total_commission / 100.0,
            "total_paid_amount": total_paid_amount / 100.0,
            "order_platform": order_platform,
            "paid_time": last_paid_time,
        }

    def _calculate_totals(
        self, orders: list[dict]
    ) -> tuple[dict[str, float], int | None]:
        """Calculate totals for a list of orders."""
        affiliate_commissions = 0
        influencer_commissions = 0
        total_paid = 0
        last_processed_order = None

        for order in orders:
            order_id = int(order.get("order_id", 0))

            # if finding last processed order, then stop processing
            if self._last_order_id and order_id == self._last_order_id:
                break

            platform = order.get("order_platform")
            commission = int(order.get("estimated_paid_commission", 0))
            commission += int(order.get("new_buyer_bonus_commission", 0))
            paid_amount = int(order.get("paid_amount", 0))
            total_paid += paid_amount

            if platform == "affiliate_platform":
                affiliate_commissions += commission
            else:
                influencer_commissions += commission

            if last_processed_order is None:
                last_processed_order = order_id

        total_commissions = affiliate_commissions + influencer_commissions

        return {
            "affiliate_commissions": affiliate_commissions / 100.0,
            "influencer_commissions": influencer_commissions / 100.0,
            "total_paid": total_paid / 100.0,
            "total_commissions": total_commissions / 100.0,
            "total_orders": len(orders),
        }, last_processed_order

    async def _get_data(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch data from AliExpress API."""
        query_params = {
            "status": "",
            "start_time": params["start_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": params["end_time"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        pagination = {"page_no": params["page"], "page_size": 50}

        return await self.hass.async_add_executor_job(
            get_order_list,
            params["app_key"],
            params["app_secret"],
            query_params,
            pagination,
        )

    async def _async_update_data(self) -> dict:
        """Fetch order data from Aliexpress API and process it."""
        try:
            now = datetime.now(tz=timezone.utc)
            start_time, end_time = self._determine_time_range(now)

            if self.config_entry is not None:
                api_credentials = self._get_api_credentials()
            else:
                self._handle_config_entry_error()

            params = self._initialize_params(api_credentials, start_time, end_time)

            all_orders = await self._fetch_all_orders(params)
        except UpdateFailed as err:
            self._handle_update_exception(err, locals().get("response"))
            return {}
        return self._process_orders(all_orders, start_time, end_time)

    def _determine_time_range(self, now: datetime) -> tuple[datetime, datetime]:
        """Determine the start and end times for the API query."""
        if self._last_end_time:
            start_time = self._last_end_time
        else:
            # First day of the current bimonthly period
            current_month = now.month
            first_month_of_bimester = ((current_month - 1) // 2) * 2 + 1
            start_time = now.replace(
                month=first_month_of_bimester,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        return start_time, now

    def _get_api_credentials(self) -> dict[str, str]:
        """Extract API credentials from the configuration entry."""
        if self.config_entry is None:
            error_message = "Config entry is None. Cannot access configuration data."
            raise ValueError(error_message)

        return {
            "app_key": self.config_entry.data[CONF_APP_KEY],
            "app_secret": self.config_entry.data[CONF_APP_SECRET],
        }

    def _initialize_params(
        self, api_credentials: dict[str, str], start_time: datetime, end_time: datetime
    ) -> dict:
        """Initialize the query parameters for the API call."""
        return {
            **api_credentials,
            "start_time": start_time,
            "end_time": end_time,
            "page": 1,
        }

    async def _fetch_all_orders(self, params: dict) -> list:
        """Fetch all orders from the API across all pages."""
        all_orders = []
        response = await self._get_data(params)
        all_orders.extend(self._validate_orders(response))

        while int(response.get("current_page_no", 0)) < int(
            response.get("total_page_no", 0)
        ):
            params["page"] = int(response.get("current_page_no", 0)) + 1
            response = await self._get_data(params)
            all_orders.extend(self._validate_orders(response))

        return all_orders

    def _process_orders(
        self, all_orders: list, start_time: datetime, end_time: datetime
    ) -> dict:
        """Process fetched orders and update totals."""
        # Calculate new order totals
        new_totals, last_processed_order = self._calculate_totals(all_orders)

        # Add to accumulated totals
        for key in self._accumulated_totals:
            self._accumulated_totals[key] += new_totals[key]

        self._last_order_id = last_processed_order
        self._last_end_time = end_time
        if all_orders:
            self._last_order_data = self._calculate_last_order(all_orders)

        return {
            **self._accumulated_totals,
            "last_reset": start_time,
            "last_order": self._last_order_data,
        }

    def _handle_config_entry_error(self) -> None:
        """Handle errors related to missing configuration entry."""
        error_message = "Config entry is None. Cannot fetch app_key and app_secret."
        raise ValueError(error_message)

    def _validate_orders(self, response: dict) -> list:
        """Validate and extract orders from the API response."""
        orders = response.get("orders", {}).get("order", [])
        if not isinstance(orders, list):
            error_message = (
                f"Expected a list in 'orders.order', but received: {type(orders)}"
            )
            _LOGGER.error(error_message)
            orders = []
        return orders

    def _handle_update_exception(self, err: Exception, response: dict | None) -> None:
        """Handle exceptions that occur during the update process."""
        error_message = "An unexpected error occurred"
        if response:
            _LOGGER.exception("%s. Complete response: %s", error_message, response)
        else:
            _LOGGER.exception(error_message)
        raise UpdateFailed(error_message) from err


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
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=CURRENCY_USD,
        )

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


class AliexpressAffiliateCommissionsSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total affiliate commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the affiliate commissions sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_affiliate_commissions"
        self.entity_description = SensorEntityDescription(
            name="Affiliate Commissions",
            key="aliexpress_affiliate_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=CURRENCY_USD,
        )

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
        """Return the total affiliate commissions if data is available."""
        return (
            self.coordinator.data.get("affiliate_commissions")
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


class AliexpressInfluencerCommissionsSensor(SensorEntity, CoordinatorEntity):
    """Sensor for tracking total influencer commissions earned."""

    def __init__(self, coordinator: AliexpressOpenPlatformCoordinator) -> None:
        """Initialize the influencer commissions sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = "aliexpress_influencer_commissions"
        self.entity_description = SensorEntityDescription(
            name="Influencer Commissions",
            key="aliexpress_influencer_commissions",
            icon="mdi:cash-multiple",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=CURRENCY_USD,
        )

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
        """Return the total influencer commissions if data is available."""
        return (
            self.coordinator.data.get("influencer_commissions")
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
    def device_info(self) -> DeviceInfo | None:
        """Return device information for this sensor."""
        return {
            "identifiers": {(DOMAIN, "aliexpress_device")},
            "name": "Aliexpress OpenPlatform",
            "manufacturer": "Aliexpress",
            "model": "OpenPlatform API",
        }

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
            native_unit_of_measurement=CURRENCY_USD,
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information for this sensor."""
        return {
            "identifiers": {(DOMAIN, "aliexpress_device")},
            "name": "Aliexpress OpenPlatform",
            "manufacturer": "Aliexpress",
            "model": "OpenPlatform API",
        }

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


class AliexpressLastOrderSensor(SensorEntity, CoordinatorEntity):
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
    def native_value(self) -> StateType | None:
        """Return the total commission for the last order group if data is available."""
        if not self.coordinator.data:
            return None
        last_order_data = self.coordinator.data.get("last_order")
        if last_order_data:
            return last_order_data.get("total_commission")
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes for the last order."""
        if not self.coordinator.data:
            return None

        last_order_data = self.coordinator.data.get("last_order")
        if not last_order_data:
            return None

        return {
            "order_platform": last_order_data.get("order_platform"),
            "paid_time": last_order_data.get("paid_time"),
            "total_paid_amount": last_order_data.get("total_paid_amount"),
        }
