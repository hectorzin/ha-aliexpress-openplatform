"""Module to handle interactions with the AliExpress API."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import requests

# Base URL for the AliExpress API
ALIEXPRESS_API_URL = "https://api-sg.aliexpress.com/sync"
_LOGGER = logging.getLogger(__name__)


def generate_signature(secret: str, params: dict[str, Any]) -> str:
    """Generate the HMAC-SHA256 signature for API authentication.

    Args:
    ----
        secret (str): API secret key provided by AliExpress.
        params (dict): Parameters to be signed.

    Returns:
    -------
        str: HMAC-SHA256 signature in hexadecimal format.

    """
    sorted_params = sorted((k, v) for k, v in params.items() if k != "sign")
    concatenated_params = "".join(f"{k}{v}" for k, v in sorted_params)
    return (
        hmac.new(
            secret.encode("utf-8"),
            concatenated_params.encode("utf-8"),
            hashlib.sha256,
        )
        .hexdigest()
        .upper()
    )


def get_order_list(
    app_key: str,
    app_secret: str,
    query_params: dict[str, Any],
    pagination: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Make an API call to `aliexpress.affiliate.order.list` to fetch orders.

    Args:
    ----
        app_key (str): API key provided by AliExpress.
        app_secret (str): API secret key provided by AliExpress.
        query_params (dict): Query parameters for the API request.
        pagination (dict | None): Dictionary with `page_no` and `page_size`.

    Returns:
    -------
        dict: Processed data from the API response.

    Raises:
    ------
        ValueError: If the API response has an unexpected format.
        requests.RequestException: If an HTTP request error occurs.

    """
    pagination = pagination or {"page_no": 1, "page_size": 50}

    # Build the query parameters
    params = {
        "app_key": app_key,
        "timestamp": str(int(time.time() * 1000)),
        "sign_method": "hmac-sha256",
        "method": "aliexpress.affiliate.order.list",
        "time_type": "Payment Completed Time",
        **query_params,
        **pagination,
    }
    params["sign"] = generate_signature(app_secret, params)

    try:
        response = requests.get(ALIEXPRESS_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Locate the main key in the response
        main_key = next((key for key in data if key.endswith("_response")), None)
        if not main_key or "resp_result" not in data[main_key]:
            _LOGGER.error("Unexpected API response: %s", data)
            raise_format_error("The API response does not contain the expected data.")
        else:
            # Process results within `resp_result`
            return data[main_key]["resp_result"].get("result", {})

    except requests.RequestException as e:
        handle_request_exception(e)
    except ValueError as e:
        raise_format_error(str(e))
    return {}


def raise_format_error(message: str) -> None:
    """Raise a format error with a standard message."""
    raise ValueError(message)


def handle_request_exception(e: requests.RequestException) -> None:
    """Raise a request error with additional context."""
    error_message = f"HTTP request error to AliExpress API: {e}"
    raise requests.RequestException(error_message) from e
