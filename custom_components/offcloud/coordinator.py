"""Data coordinator for Offcloud."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OffcloudApiClient, OffcloudApiError, OffcloudAuthenticationError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_SPEED_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[KMGT]?i?B)\s*(?:/s|ps)",
    re.IGNORECASE,
)
_SIZE_PAIR_PATTERN = re.compile(
    r"(?P<downloaded>\d+(?:[.,]\d+)?)\s*(?P<downloaded_unit>[KMGT]?i?B)"
    r"\s+(?:of|de)\s+"
    r"(?P<total>\d+(?:[.,]\d+)?)\s*(?P<total_unit>[KMGT]?i?B)",
    re.IGNORECASE,
)
_PEERS_PATTERN = re.compile(r"(?:from|de)\s+(?P<peers>\d+)\s+peers?", re.IGNORECASE)
_ETA_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\s+"
    r"(?:left|remaining|restantes?)",
    re.IGNORECASE,
)
_BYTE_FACTORS: dict[str, int] = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}
_ETA_FACTORS: dict[str, int] = {
    "SECOND": 1,
    "SECONDS": 1,
    "SEC": 1,
    "SECS": 1,
    "MINUTE": 60,
    "MINUTES": 60,
    "MIN": 60,
    "MINS": 60,
    "HOUR": 3600,
    "HOURS": 3600,
    "HR": 3600,
    "HRS": 3600,
    "DAY": 86400,
    "DAYS": 86400,
}


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
        self._samples: dict[str, tuple[float, float, int | None]] = {}
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
            transfers = await self._async_enrich_active_transfers(transfers)
        except OffcloudAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except OffcloudApiError as err:
            raise UpdateFailed(str(err)) from err

        now = time.monotonic()
        decorated = [self._decorate_transfer(dict(transfer), now) for transfer in transfers]
        current_ids = {
            str(item.get("requestId"))
            for item in decorated
            if item.get("requestId") is not None
        }
        for request_id in set(self._samples) - current_ids:
            self._samples.pop(request_id, None)

        return {
            "account": account,
            "transfers": decorated,
            "updated_at": dt_util.utcnow().isoformat(),
        }

    async def _async_enrich_active_transfers(
        self, transfers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch the freshest progress for active transfers."""
        active = [
            item
            for item in transfers
            if item.get("status") == "created" and item.get("requestId")
        ]
        if not active:
            return transfers

        results = await asyncio.gather(
            *[
                self.client.cloud_status(str(item["requestId"]))
                for item in active
            ],
            return_exceptions=True,
        )
        status_by_id: dict[str, dict[str, Any]] = {}
        for transfer, result in zip(active, results, strict=False):
            if isinstance(result, dict):
                status_by_id[str(transfer["requestId"])] = result

        enriched: list[dict[str, Any]] = []
        for transfer in transfers:
            merged = dict(transfer)
            request_id = str(transfer.get("requestId") or "")
            if request_id in status_by_id:
                merged.update(status_by_id[request_id])
            enriched.append(merged)
        return enriched

    def _decorate_transfer(
        self, transfer: dict[str, Any], now: float
    ) -> dict[str, Any]:
        """Normalise progress and parse metrics returned in Offcloud messages."""
        request_id = str(transfer.get("requestId") or "").strip()
        status = str(transfer.get("status") or "")
        message_metrics = self._parse_message_metrics(transfer.get("message"))

        total_bytes = self._extract_total_bytes(transfer)
        if total_bytes is None:
            total_bytes = message_metrics.get("total_bytes")

        downloaded_bytes = self._extract_downloaded_bytes(transfer)
        if downloaded_bytes is None:
            downloaded_bytes = message_metrics.get("downloaded_bytes")

        progress = self._normalise_progress(transfer.get("progress"))
        progress_source: str | None = "api" if progress is not None else None
        if progress is None and downloaded_bytes is not None and total_bytes:
            progress = min(max(downloaded_bytes / total_bytes, 0.0), 1.0)
            progress_source = "message"
        if status == "downloaded":
            progress = 1.0
            progress_source = "finished"

        speed_bps, speed_source = self._extract_direct_speed(transfer)
        if speed_bps is None and message_metrics.get("speed_bps") is not None:
            speed_bps = float(message_metrics["speed_bps"])
            speed_source = "message"

        previous = self._samples.get(request_id)
        if (
            speed_bps is None
            and previous is not None
            and progress is not None
            and total_bytes is not None
        ):
            previous_time, previous_progress, previous_total = previous
            effective_total = total_bytes or previous_total
            elapsed = now - previous_time
            progress_delta = progress - previous_progress
            if elapsed > 0 and progress_delta >= 0 and effective_total:
                speed_bps = progress_delta * effective_total / elapsed
                speed_source = "estimated"

        if request_id and progress is not None:
            self._samples[request_id] = (now, progress, total_bytes)

        transfer["progress"] = progress
        transfer["progressPercent"] = (
            round(progress * 100, 1) if progress is not None else None
        )
        transfer["progressSource"] = progress_source
        transfer["downloadedBytes"] = downloaded_bytes
        transfer["totalBytes"] = total_bytes
        transfer["peers"] = message_metrics.get("peers")
        transfer["etaSeconds"] = message_metrics.get("eta_seconds")

        if status == "downloaded":
            transfer["downloadSpeedBps"] = 0.0
            transfer["speedSource"] = "finished"
        else:
            transfer["downloadSpeedBps"] = (
                round(speed_bps, 1) if speed_bps is not None else None
            )
            transfer["speedSource"] = speed_source
        return transfer

    @staticmethod
    def _normalise_progress(value: Any) -> float | None:
        if not isinstance(value, (int, float)):
            return None
        progress = float(value)
        if progress > 1.0 and progress <= 100.0:
            progress /= 100.0
        return max(0.0, min(progress, 1.0))

    @staticmethod
    def _extract_total_bytes(transfer: dict[str, Any]) -> int | None:
        for key in (
            "totalBytes",
            "total_bytes",
            "totalSize",
            "total_size",
            "fileSize",
            "file_size",
            "size",
        ):
            value = transfer.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)

        files = transfer.get("files")
        if isinstance(files, list):
            sizes = [
                item.get("size")
                for item in files
                if isinstance(item, dict)
                and isinstance(item.get("size"), (int, float))
                and item.get("size") > 0
            ]
            if sizes:
                return int(sum(sizes))
        return None

    @staticmethod
    def _extract_downloaded_bytes(transfer: dict[str, Any]) -> int | None:
        for key in (
            "downloadedBytes",
            "downloaded_bytes",
            "bytesDownloaded",
            "bytes_downloaded",
            "downloadedSize",
            "downloaded_size",
        ):
            value = transfer.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return None

    @staticmethod
    def _parse_bytes(value: str, unit: str) -> int | None:
        factor = _BYTE_FACTORS.get(unit.upper())
        if factor is None:
            return None
        return int(float(value.replace(",", ".")) * factor)

    @classmethod
    def _parse_message_metrics(cls, value: Any) -> dict[str, int | float | None]:
        metrics: dict[str, int | float | None] = {
            "speed_bps": None,
            "downloaded_bytes": None,
            "total_bytes": None,
            "peers": None,
            "eta_seconds": None,
        }
        if not isinstance(value, str):
            return metrics

        speed_match = _SPEED_PATTERN.search(value)
        if speed_match:
            metrics["speed_bps"] = cls._parse_bytes(
                speed_match.group("value"), speed_match.group("unit")
            )

        size_match = _SIZE_PAIR_PATTERN.search(value)
        if size_match:
            metrics["downloaded_bytes"] = cls._parse_bytes(
                size_match.group("downloaded"), size_match.group("downloaded_unit")
            )
            metrics["total_bytes"] = cls._parse_bytes(
                size_match.group("total"), size_match.group("total_unit")
            )

        peers_match = _PEERS_PATTERN.search(value)
        if peers_match:
            metrics["peers"] = int(peers_match.group("peers"))

        eta_match = _ETA_PATTERN.search(value)
        if eta_match:
            number = float(eta_match.group("value").replace(",", "."))
            factor = _ETA_FACTORS.get(eta_match.group("unit").upper())
            if factor is not None:
                metrics["eta_seconds"] = int(number * factor)

        return metrics

    def _extract_direct_speed(
        self, transfer: dict[str, Any]
    ) -> tuple[float | None, str | None]:
        for key in (
            "bytesPerSecond",
            "bytes_per_second",
            "downloadSpeedBytes",
            "download_speed_bytes",
        ):
            value = transfer.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return float(value), "api"

        for key in ("downloadSpeed", "download_speed", "speed"):
            value = transfer.get(key)
            if isinstance(value, str):
                match = _SPEED_PATTERN.search(value)
                if match:
                    parsed = self._parse_bytes(match.group("value"), match.group("unit"))
                    if parsed is not None:
                        return float(parsed), "api_text"
        return None, None

    async def async_add_url(self, url: str) -> dict[str, Any]:
        result = await self.client.add_url(url)
        await self.async_request_refresh()
        return result

    async def async_remove(self, request_ids: list[str]) -> dict[str, Any]:
        result = await self.client.cloud_remove(request_ids)
        for request_id in request_ids:
            self._samples.pop(request_id, None)
        await self.async_request_refresh()
        return result
