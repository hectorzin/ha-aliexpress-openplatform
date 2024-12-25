"""Constants for Aliexpress Openplatform."""

DOMAIN = "aliexpress_openplatform"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"  # noqa: S105

DEVICE_INFO = {
    "identifiers": {(DOMAIN, "aliexpress_device")},
    "name": "Aliexpress OpenPlatform",
    "manufacturer": "Aliexpress",
    "model": "OpenPlatform API",
    "configuration_url": "https://portals.aliexpress.com",
}
