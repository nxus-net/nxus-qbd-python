"""HTTP transport layer wrapping httpx for both sync and async usage."""

from __future__ import annotations

import asyncio
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

import httpx

from nxus_qbd.errors import NxusApiError

DEFAULT_TIMEOUT_SECONDS = 100.0
DEFAULT_MAX_RETRIES = 2
RETRY_BASE_DELAY_SECONDS = 0.5
RETRY_MAX_DELAY_SECONDS = 8.0
# 409 is intentionally omitted: the backend overloads it for both retryable
# lock contention (`ObjectInUse`, `LockFailed`) and terminal business-rule
# violations (`OutdatedEditSequence`, `NameNotUnique`, `TimeCreationMismatch`).
# Without `x-should-retry` to disambiguate, retrying 409 blindly will burn
# attempts on errors that need client-side action. Servers that emit the
# header (`x-should-retry: true`) override this fallback and opt 409s in.
RETRYABLE_STATUSES = {408, 429}


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
        server_timeout_seconds: Optional[int] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        merged_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        if server_timeout_seconds is not None:
            merged_headers.setdefault(
                "X-Nxus-Timeout-Seconds", str(server_timeout_seconds)
            )
        self._default_server_timeout_seconds = server_timeout_seconds
        self._default_max_retries = max(0, max_retries)
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
        server_timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
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
        merged_request_headers: Dict[str, str] = {}
        if server_timeout_seconds is not None:
            merged_request_headers["X-Nxus-Timeout-Seconds"] = str(
                server_timeout_seconds
            )
        if headers:
            merged_request_headers.update(headers)
        if merged_request_headers:
            kwargs["headers"] = merged_request_headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        retry_budget = max(0, self._default_max_retries if max_retries is None else max_retries)
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                raise
            except httpx.TransportError:
                if attempt >= retry_budget:
                    raise
                time.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            if response.is_success:
                break

            if attempt >= retry_budget or not _should_retry_response(response):
                raise NxusApiError.from_response(response)

            time.sleep(_compute_retry_delay(attempt, response))
            attempt += 1

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
        server_timeout_seconds: Optional[int] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        merged_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        if server_timeout_seconds is not None:
            merged_headers.setdefault(
                "X-Nxus-Timeout-Seconds", str(server_timeout_seconds)
            )
        self._default_server_timeout_seconds = server_timeout_seconds
        self._default_max_retries = max(0, max_retries)
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
        server_timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
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
        merged_request_headers: Dict[str, str] = {}
        if server_timeout_seconds is not None:
            merged_request_headers["X-Nxus-Timeout-Seconds"] = str(
                server_timeout_seconds
            )
        if headers:
            merged_request_headers.update(headers)
        if merged_request_headers:
            kwargs["headers"] = merged_request_headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        retry_budget = max(0, self._default_max_retries if max_retries is None else max_retries)
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                raise
            except httpx.TransportError:
                if attempt >= retry_budget:
                    raise
                await asyncio.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            if response.is_success:
                break

            if attempt >= retry_budget or not _should_retry_response(response):
                raise NxusApiError.from_response(response)

            await asyncio.sleep(_compute_retry_delay(attempt, response))
            attempt += 1

        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def _should_retry_response(response: httpx.Response) -> bool:
    should_retry = _parse_should_retry(response.headers.get("x-should-retry"))
    if should_retry is not None:
        return should_retry
    return response.status_code in RETRYABLE_STATUSES or response.status_code >= 500


def _compute_retry_delay(attempt: int, response: Optional[httpx.Response] = None) -> float:
    if response is not None:
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        if retry_after is None:
            retry_after = _parse_body_retry_after(response)
        if retry_after is not None:
            return min(retry_after, RETRY_MAX_DELAY_SECONDS)

    exponential = min(RETRY_BASE_DELAY_SECONDS * (2**attempt), RETRY_MAX_DELAY_SECONDS)
    return exponential + random.random() * exponential * 0.5


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None

    try:
        seconds = float(value)
    except ValueError:
        seconds = None
    if seconds is not None and seconds >= 0:
        return seconds

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, retry_at.timestamp() - time.time())


def _parse_body_retry_after(response: httpx.Response) -> Optional[float]:
    """Extract ``error.retryAfter`` (seconds) from a JSON error body.

    Used as a fallback for the standard ``Retry-After`` header so the SDK
    still honors retry pacing when proxies strip hop-by-hop headers but
    preserve the JSON body.
    """
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error_obj = body.get("error") if isinstance(body.get("error"), dict) else None
    candidate: Any = None
    if error_obj is not None:
        candidate = error_obj.get("retryAfter")
    if candidate is None:
        candidate = body.get("retryAfter")
    if isinstance(candidate, bool):  # bool is a subclass of int — exclude explicitly
        return None
    if isinstance(candidate, (int, float)) and candidate >= 0:
        return float(candidate)
    return None


def _parse_should_retry(value: Optional[str]) -> Optional[bool]:
    if not value:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None
