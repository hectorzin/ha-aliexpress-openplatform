"""Aliexpress Coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any

from aliexpress_api import AliexpressApi

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import CONF_APP_KEY, CONF_APP_SECRET

if TYPE_CHECKING:
    from aliexpress_api.models import Order, OrderListResponse

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


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
        api_credentials = self._get_api_credentials()
        self.client = AliexpressApi(
            api_credentials["app_key"],
            api_credentials["app_secret"],
            language="en",
            currency="USD",
        )

    def get_value(self, name: str) -> Any | None:
        """Return the value from coordinator data or none."""
        if name in self.data:
            return self.data[name]

        return None

    def _calculate_last_order(self, orders: list[Order]) -> dict[str, Any] | None:
        """Calculate the details for the last order group."""
        if not orders:
            return None

        # getting `paid_time` of first order (it's the last order arrived)
        last_paid_time = orders[0].paid_time
        order_platform = orders[0].order_platform

        # filtering others that share same `paid_time`
        last_orders = [order for order in orders if order.paid_time == last_paid_time]

        total_commission = sum(
            int(order.estimated_paid_commission) + int(order.new_buyer_bonus_commission)
            for order in last_orders
        )
        total_paid_amount = sum(int(order.paid_amount) for order in last_orders)

        platforms = {order.order_platform for order in last_orders}
        order_platform = "mixed" if len(platforms) > 1 else platforms.pop()

        return {
            "total_commission": total_commission / 100.0,
            "total_paid_amount": total_paid_amount / 100.0,
            "order_platform": order_platform,
            "paid_time": last_paid_time,
        }

    def _calculate_totals(
        self, orders: list[Order]
    ) -> tuple[dict[str, float], int | None]:
        """Calculate totals for a list of orders."""
        affiliate_commissions = 0
        influencer_commissions = 0
        total_paid = 0
        last_processed_order = None

        for order in orders:
            order_id = int(order.order_id)

            # if finding last processed order, then stop processing
            if self._last_order_id and order_id == self._last_order_id:
                break

            platform = order.order_platform
            commission = int(order.estimated_paid_commission)
            commission += int(order.new_buyer_bonus_commission)
            paid_amount = int(order.paid_amount)
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

    async def _get_data(self, params: dict[str, Any]) -> OrderListResponse:
        """Fetch data from AliExpress API."""
        query_params = {
            "status": "",
            "start_time": params["start_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": params["end_time"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        pagination = {"page_no": params["page"], "page_size": 50}

        return await self.hass.async_add_executor_job(
            self.client.get_order_list,
            query_params["status"],
            query_params["start_time"],
            query_params["end_time"],
            [
                "order_id",
                "order_number",
                "paid_amount",
                "estimated_paid_commission",
                "new_buyer_bonus_commission",
                "created_time",
                "paid_time",
                "order_platform",
            ],
            "global",
            pagination["page_no"],
            pagination["page_size"],
        )

    async def _async_update_data(self) -> dict:
        """Fetch order data from Aliexpress API and process it."""
        try:
            now = datetime.now(tz=timezone.utc)
            start_time, end_time = self._determine_time_range(now)

            params = self._initialize_params(start_time, end_time)

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

    def _initialize_params(self, start_time: datetime, end_time: datetime) -> dict:
        """Initialize the query parameters for the API call."""
        return {
            "start_time": start_time,
            "end_time": end_time,
            "page": 1,
        }

    async def _fetch_all_orders(self, params: dict) -> list:
        """Fetch all orders from the API across all pages."""
        all_orders = []
        response = await self._get_data(params)
        all_orders.extend(self._validate_orders(response))

        while int(response.current_page_no) < int(response.total_page_no):
            params["page"] = int(response.current_page_no) + 1
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

    def _validate_orders(self, response: list) -> list:
        """Validate and extract orders from the API response."""
        orders = response
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
