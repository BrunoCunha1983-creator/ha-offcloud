"""Offcloud integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OffcloudApiClient, OffcloudApiError
from .const import (
    ATTR_INCLUDE_FILES,
    ATTR_REQUEST_ID,
    ATTR_REQUEST_IDS,
    ATTR_URL,
    ATTR_URLS,
    CONF_API_KEY,
    DOMAIN,
    SERVICE_ADD_URL,
    SERVICE_CHECK_CACHE,
    SERVICE_EXPLORE,
    SERVICE_REFRESH,
    SERVICE_REMOVE,
)
from .coordinator import OffcloudDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass(slots=True)
class OffcloudRuntimeData:
    """Runtime objects for one Offcloud config entry."""

    client: OffcloudApiClient
    coordinator: OffcloudDataUpdateCoordinator


def _runtime(hass: HomeAssistant) -> OffcloudRuntimeData:
    entries: dict[str, OffcloudRuntimeData] = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("Offcloud is not configured or is not loaded")
    return next(iter(entries.values()))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Offcloud from a config entry."""
    session = async_get_clientsession(hass)
    client = OffcloudApiClient(session, entry.data[CONF_API_KEY])
    coordinator = OffcloudDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = OffcloudRuntimeData(
        client=client, coordinator=coordinator
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_URL):
        _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Offcloud config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.data.pop(DOMAIN, None)
            for service in (
                SERVICE_ADD_URL,
                SERVICE_REMOVE,
                SERVICE_REFRESH,
                SERVICE_CHECK_CACHE,
                SERVICE_EXPLORE,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    async def add_url(call: ServiceCall) -> dict[str, Any]:
        try:
            return await _runtime(hass).coordinator.async_add_url(call.data[ATTR_URL])
        except (OffcloudApiError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def remove(call: ServiceCall) -> dict[str, Any]:
        try:
            return await _runtime(hass).coordinator.async_remove(
                list(call.data[ATTR_REQUEST_IDS])
            )
        except (OffcloudApiError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def refresh(call: ServiceCall) -> dict[str, Any]:
        await _runtime(hass).coordinator.async_request_refresh()
        return {"success": True}

    async def check_cache(call: ServiceCall) -> dict[str, Any]:
        try:
            result = await _runtime(hass).client.cache_info(
                call.data[ATTR_URLS],
                include_files=call.data.get(ATTR_INCLUDE_FILES, False),
            )
            return {"results": result}
        except (OffcloudApiError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def explore(call: ServiceCall) -> dict[str, Any]:
        try:
            result = await _runtime(hass).client.cloud_explore(
                call.data[ATTR_REQUEST_ID], detailed=True
            )
            return result if isinstance(result, dict) else {"urls": result}
        except (OffcloudApiError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_URL,
        add_url,
        schema=vol.Schema({vol.Required(ATTR_URL): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE,
        remove,
        schema=vol.Schema(
            {vol.Required(ATTR_REQUEST_IDS): vol.All(cv.ensure_list, [cv.string])}
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        refresh,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_CACHE,
        check_cache,
        schema=vol.Schema(
            {
                vol.Required(ATTR_URLS): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(ATTR_INCLUDE_FILES, default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPLORE,
        explore,
        schema=vol.Schema({vol.Required(ATTR_REQUEST_ID): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
