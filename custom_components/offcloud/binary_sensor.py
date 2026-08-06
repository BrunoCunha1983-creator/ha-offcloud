"""Binary sensors for Offcloud."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import OffcloudCoordinatorEntity

DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="premium", translation_key="premium", icon="mdi:crown"
    ),
    BinarySensorEntityDescription(
        key="can_download", translation_key="can_download", icon="mdi:download-network"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
    async_add_entities(
        [OffcloudAccountBinarySensor(coordinator, description) for description in DESCRIPTIONS]
    )


class OffcloudAccountBinarySensor(OffcloudCoordinatorEntity, BinarySensorEntity):
    """An Offcloud account binary sensor."""

    def __init__(self, coordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        account = self.coordinator.data.get("account", {})
        if self.entity_description.key == "premium":
            return bool(account.get("is_premium"))
        return bool(account.get("can_download"))
