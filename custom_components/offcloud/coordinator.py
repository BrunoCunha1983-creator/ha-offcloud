"""Data coordinator for Offcloud."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OffcloudApiClient, OffcloudApiError, OffcloudAuthenticationError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN


class OffcloudDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate account and transfer updates from Offcloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: OffcloudApiClient,
    ) -> None:
        self.entry = entry
        self.client = client
        interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        )
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            account, transfers = await asyncio.gather(
                self.client.account_info(), self.client.cloud_history()
            )
        except OffcloudAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except OffcloudApiError as err:
            raise UpdateFailed(str(err)) from err

        return {
            "account": account,
            "transfers": transfers,
            "updated_at": dt_util.utcnow().isoformat(),
        }

    async def async_add_url(self, url: str) -> dict[str, Any]:
        result = await self.client.add_url(url)
        await self.async_request_refresh()
        return result

    async def async_remove(self, request_ids: list[str]) -> dict[str, Any]:
        result = await self.client.cloud_remove(request_ids)
        await self.async_request_refresh()
        return result
