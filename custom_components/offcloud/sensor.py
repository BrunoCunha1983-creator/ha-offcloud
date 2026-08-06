"""Sensors for the Offcloud integration."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import OffcloudCoordinatorEntity

_TRANSFER_UNIQUE_ID_SUFFIXES = ("_status", "_progress", "_download_speed")


def _transfers(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.get("transfers", [])


def _count_status(data: dict[str, Any], status: str) -> int:
    return sum(1 for item in _transfers(data) if item.get("status") == status)


def _rounded_unit(value: Any, divisor: float, digits: int = 2) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) / divisor, digits)


SUMMARY_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="transfer_count", translation_key="transfer_count", icon="mdi:cloud-download"
    ),
    SensorEntityDescription(
        key="active_transfers", translation_key="active_transfers", icon="mdi:progress-download"
    ),
    SensorEntityDescription(
        key="completed_transfers", translation_key="completed_transfers", icon="mdi:cloud-check"
    ),
    SensorEntityDescription(
        key="failed_transfers", translation_key="failed_transfers", icon="mdi:cloud-alert"
    ),
    SensorEntityDescription(
        key="premium_expiration",
        translation_key="premium_expiration",
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar-clock",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Offcloud sensors and remove stale transfer entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
    entity_registry = er.async_get(hass)

    async_add_entities(
        [OffcloudSummarySensor(coordinator, description) for description in SUMMARY_DESCRIPTIONS]
    )

    known_request_ids: set[str] = set()
    sync_lock = asyncio.Lock()

    async def async_sync_transfer_entities() -> None:
        """Add current transfers and delete entities for removed transfers."""
        async with sync_lock:
            current_request_ids = {
                str(transfer.get("requestId") or "").strip()
                for transfer in _transfers(coordinator.data)
                if str(transfer.get("requestId") or "").strip()
            }

            new_request_ids = current_request_ids - known_request_ids
            entities: list[SensorEntity] = []
            for transfer in _transfers(coordinator.data):
                request_id = str(transfer.get("requestId") or "").strip()
                if not request_id or request_id not in new_request_ids:
                    continue
                entities.extend(
                    [
                        OffcloudTransferStatusSensor(coordinator, request_id),
                        OffcloudTransferProgressSensor(coordinator, request_id),
                        OffcloudTransferSpeedSensor(coordinator, request_id),
                    ]
                )

            if entities:
                async_add_entities(entities)

            # A successful refresh which no longer contains a transfer means it
            # was removed from Offcloud. Delete its three registry entries so
            # Home Assistant does not retain unavailable/orphaned entities.
            for registry_entry in er.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            ):
                if registry_entry.domain != "sensor" or registry_entry.platform != DOMAIN:
                    continue

                request_id: str | None = None
                for suffix in _TRANSFER_UNIQUE_ID_SUFFIXES:
                    if registry_entry.unique_id.endswith(suffix):
                        request_id = registry_entry.unique_id[: -len(suffix)]
                        break

                if request_id and request_id not in current_request_ids:
                    entity_registry.async_remove(registry_entry.entity_id)

            known_request_ids.clear()
            known_request_ids.update(current_request_ids)

    def schedule_sync() -> None:
        hass.async_create_task(async_sync_transfer_entities())

    await async_sync_transfer_entities()
    entry.async_on_unload(coordinator.async_add_listener(schedule_sync))


class OffcloudSummarySensor(OffcloudCoordinatorEntity, SensorEntity):
    """An Offcloud account summary sensor."""

    def __init__(self, coordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        key = self.entity_description.key
        if key == "transfer_count":
            return len(_transfers(data))
        if key == "active_transfers":
            return _count_status(data, "created")
        if key == "completed_transfers":
            return _count_status(data, "downloaded")
        if key == "failed_transfers":
            return _count_status(data, "error")
        if key == "premium_expiration":
            value = data.get("account", {}).get("expiration_date")
            if value:
                try:
                    return date.fromisoformat(value)
                except ValueError:
                    return None
        return None


class _OffcloudTransferSensor(OffcloudCoordinatorEntity, SensorEntity):
    """Base sensor for one cloud transfer."""

    def __init__(self, coordinator, request_id: str) -> None:
        super().__init__(coordinator)
        self.request_id = request_id

    @property
    def _transfer(self) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in _transfers(self.coordinator.data)
                if str(item.get("requestId")) == self.request_id
            ),
            None,
        )

    @property
    def available(self) -> bool:
        return super().available and self._transfer is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        transfer = self._transfer or {}
        eta_seconds = transfer.get("etaSeconds")
        return {
            "request_id": self.request_id,
            "file_name": transfer.get("fileName"),
            "message": transfer.get("message"),
            "created_on": transfer.get("createdOn"),
            "progress_percent": transfer.get("progressPercent"),
            "progress_source": transfer.get("progressSource"),
            "download_speed_mb_s": _rounded_unit(
                transfer.get("downloadSpeedBps"), 1_000_000
            ),
            "speed_source": transfer.get("speedSource"),
            "downloaded_gb": _rounded_unit(
                transfer.get("downloadedBytes"), 1_000_000_000
            ),
            "total_gb": _rounded_unit(transfer.get("totalBytes"), 1_000_000_000),
            "downloaded_bytes": transfer.get("downloadedBytes"),
            "total_bytes": transfer.get("totalBytes"),
            "peers": transfer.get("peers"),
            "eta_minutes": (
                round(float(eta_seconds) / 60, 1)
                if isinstance(eta_seconds, (int, float))
                else None
            ),
            "eta_seconds": eta_seconds,
        }


class OffcloudTransferStatusSensor(_OffcloudTransferSensor):
    """Status sensor for one Offcloud transfer."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["created", "downloaded", "error"]
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, coordinator, request_id: str) -> None:
        super().__init__(coordinator, request_id)
        transfer = self._transfer or {}
        name = transfer.get("fileName") or request_id
        self._attr_name = f"{name} estado"
        self._attr_unique_id = f"{request_id}_status"

    @property
    def native_value(self) -> str | None:
        transfer = self._transfer
        return str(transfer.get("status")) if transfer and transfer.get("status") else None


class OffcloudTransferProgressSensor(_OffcloudTransferSensor):
    """Progress sensor for one Offcloud transfer."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:download-circle-outline"

    def __init__(self, coordinator, request_id: str) -> None:
        super().__init__(coordinator, request_id)
        transfer = self._transfer or {}
        name = transfer.get("fileName") or request_id
        self._attr_name = f"{name} progresso"
        self._attr_unique_id = f"{request_id}_progress"

    @property
    def native_value(self) -> float | None:
        transfer = self._transfer
        if not transfer:
            return None
        value = transfer.get("progressPercent")
        if isinstance(value, (int, float)):
            return float(value)
        if transfer.get("status") == "downloaded":
            return 100.0
        return None


class OffcloudTransferSpeedSensor(_OffcloudTransferSensor):
    """Download speed sensor for one Offcloud transfer."""

    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.BYTES_PER_SECOND
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, request_id: str) -> None:
        super().__init__(coordinator, request_id)
        transfer = self._transfer or {}
        name = transfer.get("fileName") or request_id
        self._attr_name = f"{name} velocidade de download"
        self._attr_unique_id = f"{request_id}_download_speed"

    @property
    def native_value(self) -> float | None:
        transfer = self._transfer
        if not transfer:
            return None
        value = transfer.get("downloadSpeedBps")
        return float(value) if isinstance(value, (int, float)) else None
