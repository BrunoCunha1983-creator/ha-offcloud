"""Constants for the Offcloud integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "offcloud"
NAME: Final = "Offcloud"
API_BASE_URL: Final = "https://offcloud.com/api"
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"

SERVICE_ADD_URL: Final = "add_url"
SERVICE_REMOVE: Final = "remove"
SERVICE_REFRESH: Final = "refresh"
SERVICE_CHECK_CACHE: Final = "check_cache"
SERVICE_EXPLORE: Final = "explore"

ATTR_URL: Final = "url"
ATTR_URLS: Final = "urls"
ATTR_REQUEST_ID: Final = "request_id"
ATTR_REQUEST_IDS: Final = "request_ids"
ATTR_INCLUDE_FILES: Final = "include_files"
