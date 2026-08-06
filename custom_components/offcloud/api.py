"""Asynchronous client for the Offcloud REST API."""

from __future__ import annotations

from typing import Any, Iterable

import aiohttp

from .const import API_BASE_URL


class OffcloudApiError(Exception):
    """Base exception raised by the Offcloud API client."""


class OffcloudAuthenticationError(OffcloudApiError):
    """Raised when Offcloud rejects the API key."""


class OffcloudNotFoundError(OffcloudApiError):
    """Raised when an Offcloud request ID does not exist."""


class OffcloudApiClient:
    """Small, Home Assistant friendly Offcloud API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        *,
        base_url: str = API_BASE_URL,
        timeout: int = 45,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise ValueError("The Offcloud API key cannot be empty")
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-Offcloud/1.0",
        }
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=self._timeout,
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    payload = await response.text()
        except TimeoutError as err:
            raise OffcloudApiError("Connection to Offcloud timed out") from err
        except aiohttp.ClientError as err:
            raise OffcloudApiError(f"Network error while contacting Offcloud: {err}") from err

        if response.status == 401:
            raise OffcloudAuthenticationError("Invalid or expired Offcloud API key")
        if response.status == 404:
            raise OffcloudNotFoundError(self._error_message(payload, "Request not found"))
        if response.status >= 400:
            raise OffcloudApiError(
                f"Offcloud returned HTTP {response.status}: "
                f"{self._error_message(payload, response.reason or 'Unknown error')}"
            )
        return payload

    @staticmethod
    def _error_message(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            for key in ("error_description", "error", "message", "detail"):
                if payload.get(key):
                    return str(payload[key])
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        return fallback

    async def account_info(self) -> dict[str, Any]:
        data = await self._request("GET", "/account/info")
        if not isinstance(data, dict):
            raise OffcloudApiError("Unexpected account response")
        return data

    async def sites(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/sites")
        if not isinstance(data, list):
            raise OffcloudApiError("Unexpected sites response")
        return data

    async def cloud_history(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/cloud/history")
        if not isinstance(data, list):
            raise OffcloudApiError("Unexpected cloud history response")
        return data

    async def add_url(self, url: str) -> dict[str, Any]:
        url = url.strip()
        if not url:
            raise ValueError("URL or magnet link cannot be empty")
        data = await self._request("POST", "/cloud", json_data={"url": url})
        if not isinstance(data, dict):
            raise OffcloudApiError("Unexpected add download response")
        return data

    async def cloud_status(self, request_id: str) -> dict[str, Any]:
        request_id = request_id.strip()
        if not request_id:
            raise ValueError("request_id cannot be empty")
        data = await self._request(
            "POST", "/cloud/status", json_data={"requestId": request_id}
        )
        status = data.get("status") if isinstance(data, dict) else None
        if not isinstance(status, dict):
            raise OffcloudApiError("Offcloud response does not contain status object")
        return status

    async def cloud_explore(
        self, request_id: str, *, detailed: bool = True
    ) -> dict[str, Any] | list[str]:
        request_id = request_id.strip()
        if not request_id:
            raise ValueError("request_id cannot be empty")
        params = {"format": "detailed"} if detailed else None
        return await self._request(
            "GET", f"/cloud/explore/{request_id}", params=params
        )

    async def cloud_remove(self, request_ids: Iterable[str]) -> dict[str, Any]:
        cleaned = [str(item).strip() for item in request_ids if str(item).strip()]
        if not cleaned:
            raise ValueError("At least one request_id is required")
        data = await self._request(
            "POST", "/cloud/remove", json_data={"requests": cleaned}
        )
        if not isinstance(data, dict):
            raise OffcloudApiError("Unexpected remove response")
        return data

    async def cache_info(
        self, urls: Iterable[str], *, include_files: bool = False
    ) -> list[dict[str, Any]]:
        cleaned = [str(url).strip() for url in urls if str(url).strip()]
        if not cleaned:
            raise ValueError("At least one magnet link is required")
        data = await self._request(
            "POST",
            "/cache/info",
            json_data={"urls": cleaned, "includeFiles": bool(include_files)},
        )
        if not isinstance(data, list):
            raise OffcloudApiError("Unexpected cache response")
        return data
