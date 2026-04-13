"""HTTP transport layer wrapping httpx for both sync and async usage."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from nxus_qbd.errors import NxusApiError

DEFAULT_TIMEOUT_SECONDS = 100.0


class SyncTransport:
    """Synchronous HTTP transport backed by ``httpx.Client``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        verify: bool = True,
    ) -> None:
        merged_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        self._client = httpx.Client(
            base_url=base_url,
            headers=merged_headers,
            timeout=timeout,
            verify=verify,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send a request and return parsed JSON (or raw response on non-JSON).

        Raises ``NxusApiError`` on non-2xx responses instead of
        ``httpx.HTTPStatusError``.
        """
        kwargs: Dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if params:
            kwargs["params"] = params
        if headers:
            kwargs["headers"] = headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        response = self._client.request(method, path, **kwargs)

        if not response.is_success:
            raise NxusApiError.from_response(response)

        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SyncTransport":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncTransport:
    """Asynchronous HTTP transport backed by ``httpx.AsyncClient``."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        verify: bool = True,
    ) -> None:
        merged_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=merged_headers,
            timeout=timeout,
            verify=verify,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send a request and return parsed JSON (or raw response on non-JSON).

        Raises ``NxusApiError`` on non-2xx responses instead of
        ``httpx.HTTPStatusError``.
        """
        kwargs: Dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if params:
            kwargs["params"] = params
        if headers:
            kwargs["headers"] = headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        response = await self._client.request(method, path, **kwargs)

        if not response.is_success:
            raise NxusApiError.from_response(response)

        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
