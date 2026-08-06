"""Base entities for Offcloud."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OffcloudDataUpdateCoordinator


class OffcloudCoordinatorEntity(CoordinatorEntity[OffcloudDataUpdateCoordinator]):
    """Base class for Offcloud coordinator entities."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        account = self.coordinator.data.get("account", {})
        user_id = str(account.get("user_id") or self.coordinator.entry.entry_id)
        return DeviceInfo(
            identifiers={(DOMAIN, user_id)},
            name="Offcloud",
            manufacturer="Offcloud",
            model="Cloud account",
            configuration_url="https://offcloud.com",
        )
