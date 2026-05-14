"""HTTP transport layer wrapping httpx for both sync and async usage."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable

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

REDACTED = "[REDACTED]"
_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
    }
)


@runtime_checkable
class NxusLogger(Protocol):
    """Structured logger contract.

    Any object with ``debug``/``info``/``warn``/``error`` methods that accept
    ``(message, context)`` satisfies this protocol. ``logging.Logger`` works
    via the :class:`StdlibLoggerAdapter` wrapper.
    """

    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None: ...
    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None: ...
    def warn(self, message: str, context: Optional[Dict[str, Any]] = None) -> None: ...
    def error(self, message: str, context: Optional[Dict[str, Any]] = None) -> None: ...


def _redact_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    return {
        k: (REDACTED if k.lower() in _SENSITIVE_HEADER_NAMES else v)
        for k, v in headers.items()
    }


class _DefaultLogger:
    """Prints structured ``[nxus-qbd] <event>`` lines to the stdlib ``logging``
    module under the ``nxus_qbd`` logger. Used when ``verbose=True`` but no
    logger is supplied.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger("nxus_qbd")

    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        self._log.debug("%s %s", message, context or "")

    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        self._log.info("%s %s", message, context or "")

    def warn(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        self._log.warning("%s %s", message, context or "")

    def error(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        self._log.error("%s %s", message, context or "")


def _build_httpx_client_kwargs(
    *,
    base_url: str,
    headers: Dict[str, str],
    timeout: float,
    verify: bool,
    proxy: Optional[str],
    http_client_options: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compose the kwargs passed into ``httpx.Client`` / ``httpx.AsyncClient``.

    ``http_client_options`` is the escape hatch for runtime-specific features
    (custom ``transport``, ``trust_env``, ``mounts``, etc.). Explicit args win
    over the escape hatch where they overlap, except for ``proxy`` which is
    added only when set.
    """
    kwargs: Dict[str, Any] = {
        "base_url": base_url,
        "headers": headers,
        "timeout": timeout,
        "verify": verify,
    }
    if http_client_options:
        # User overrides come first, then explicit args overwrite.
        merged = {**http_client_options, **kwargs}
        kwargs = merged
    if proxy and "proxy" not in kwargs and "proxies" not in kwargs:
        # httpx>=0.26 accepts `proxy=`; older versions use `proxies=`. We pass
        # the modern form and let httpx raise if the version is too old.
        kwargs["proxy"] = proxy
    return kwargs


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
        verbose: bool = False,
        logger: Optional[NxusLogger] = None,
        proxy: Optional[str] = None,
        http_client_options: Optional[Dict[str, Any]] = None,
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
        self._verbose = verbose or logger is not None
        self._logger: NxusLogger = logger if logger is not None else _DefaultLogger()
        self._merged_headers = merged_headers
        self._client = httpx.Client(
            **_build_httpx_client_kwargs(
                base_url=base_url,
                headers=merged_headers,
                timeout=timeout,
                verify=verify,
                proxy=proxy,
                http_client_options=http_client_options,
            )
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
        verbose: Optional[bool] = None,
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
        log_verbose = self._verbose if verbose is None else verbose
        attempt = 0
        while True:
            self._log_request(method, path, params, merged_request_headers, attempt, retry_budget, log_verbose)
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if log_verbose:
                    self._logger.warn("timeout", {"method": method, "path": path, "attempt": attempt})
                raise
            except httpx.TransportError as exc:
                if log_verbose:
                    self._logger.warn(
                        "network-error",
                        {"method": method, "path": path, "attempt": attempt, "reason": str(exc)},
                    )
                if attempt >= retry_budget:
                    raise
                time.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            self._log_response(method, path, response, attempt, log_verbose)
            if response.is_success:
                break

            if attempt >= retry_budget or not _should_retry_response(response):
                raise NxusApiError.from_response(response)

            delay = _compute_retry_delay(attempt, response)
            if log_verbose:
                self._logger.debug(
                    "retry-scheduled",
                    {"path": path, "attempt": attempt + 1, "delay_seconds": delay},
                )
            time.sleep(delay)
            attempt += 1

        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    def raw(
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
        verbose: Optional[bool] = None,
    ) -> httpx.Response:
        """Issue a raw HTTP request and return the unparsed ``httpx.Response``.

        Use this when you need direct access to status, headers, or the
        response body as text/bytes/stream. Bypasses JSON parsing and the typed
        :class:`NxusApiError` mapping, but still applies authentication, the
        default headers, the timeout, and retries. Non-2xx responses are
        returned, not raised — the caller is responsible for ``response.is_success``.
        """
        kwargs: Dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if params:
            kwargs["params"] = params
        merged_request_headers: Dict[str, str] = {}
        if server_timeout_seconds is not None:
            merged_request_headers["X-Nxus-Timeout-Seconds"] = str(server_timeout_seconds)
        if headers:
            merged_request_headers.update(headers)
        if merged_request_headers:
            kwargs["headers"] = merged_request_headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        retry_budget = max(0, self._default_max_retries if max_retries is None else max_retries)
        log_verbose = self._verbose if verbose is None else verbose
        attempt = 0
        while True:
            self._log_request(method, path, params, merged_request_headers, attempt, retry_budget, log_verbose, raw=True)
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if log_verbose:
                    self._logger.warn("timeout", {"method": method, "path": path, "attempt": attempt, "raw": True})
                raise
            except httpx.TransportError as exc:
                if log_verbose:
                    self._logger.warn(
                        "network-error",
                        {"method": method, "path": path, "attempt": attempt, "raw": True, "reason": str(exc)},
                    )
                if attempt >= retry_budget:
                    raise
                time.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            self._log_response(method, path, response, attempt, log_verbose, raw=True)
            if response.is_success:
                return response
            if attempt >= retry_budget or not _should_retry_response(response):
                # Non-retried non-2xx: return the Response, matching the
                # documented "non-2xx returned, not raised" raw contract.
                return response

            delay = _compute_retry_delay(attempt, response)
            if log_verbose:
                self._logger.debug(
                    "retry-scheduled",
                    {"path": path, "attempt": attempt + 1, "delay_seconds": delay, "raw": True},
                )
            time.sleep(delay)
            attempt += 1

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SyncTransport":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- logging helpers ----------------------------------------------------

    def _log_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        per_request_headers: Dict[str, str],
        attempt: int,
        max_retries: int,
        verbose: bool,
        *,
        raw: bool = False,
    ) -> None:
        if not verbose:
            return
        all_headers = {**self._merged_headers, **per_request_headers}
        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "headers": _redact_headers(all_headers),
            "attempt": attempt,
            "max_retries": max_retries,
        }
        if params:
            ctx["params"] = params
        if raw:
            ctx["raw"] = True
        self._logger.debug("request", ctx)

    def _log_response(
        self,
        method: str,
        path: str,
        response: httpx.Response,
        attempt: int,
        verbose: bool,
        *,
        raw: bool = False,
    ) -> None:
        if not verbose:
            return
        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "attempt": attempt,
            "status": response.status_code,
        }
        if raw:
            ctx["raw"] = True
        if response.is_success:
            self._logger.debug("response", ctx)
        else:
            ctx["retry_after"] = _parse_retry_after(response.headers.get("retry-after"))
            ctx["should_retry"] = _parse_should_retry(response.headers.get("x-should-retry"))
            self._logger.warn("response", ctx)


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
        verbose: bool = False,
        logger: Optional[NxusLogger] = None,
        proxy: Optional[str] = None,
        http_client_options: Optional[Dict[str, Any]] = None,
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
        self._verbose = verbose or logger is not None
        self._logger: NxusLogger = logger if logger is not None else _DefaultLogger()
        self._merged_headers = merged_headers
        self._client = httpx.AsyncClient(
            **_build_httpx_client_kwargs(
                base_url=base_url,
                headers=merged_headers,
                timeout=timeout,
                verify=verify,
                proxy=proxy,
                http_client_options=http_client_options,
            )
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
        verbose: Optional[bool] = None,
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
        log_verbose = self._verbose if verbose is None else verbose
        attempt = 0
        while True:
            self._log_request(method, path, params, merged_request_headers, attempt, retry_budget, log_verbose)
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if log_verbose:
                    self._logger.warn("timeout", {"method": method, "path": path, "attempt": attempt})
                raise
            except httpx.TransportError as exc:
                if log_verbose:
                    self._logger.warn(
                        "network-error",
                        {"method": method, "path": path, "attempt": attempt, "reason": str(exc)},
                    )
                if attempt >= retry_budget:
                    raise
                await asyncio.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            self._log_response(method, path, response, attempt, log_verbose)
            if response.is_success:
                break

            if attempt >= retry_budget or not _should_retry_response(response):
                raise NxusApiError.from_response(response)

            delay = _compute_retry_delay(attempt, response)
            if log_verbose:
                self._logger.debug(
                    "retry-scheduled",
                    {"path": path, "attempt": attempt + 1, "delay_seconds": delay},
                )
            await asyncio.sleep(delay)
            attempt += 1

        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    async def raw(
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
        verbose: Optional[bool] = None,
    ) -> httpx.Response:
        """Issue a raw HTTP request and return the unparsed ``httpx.Response``.

        See :meth:`SyncTransport.raw` for full semantics. Non-2xx responses
        are returned (not raised); retries still apply.
        """
        kwargs: Dict[str, Any] = {}
        if json is not None:
            kwargs["json"] = json
        if params:
            kwargs["params"] = params
        merged_request_headers: Dict[str, str] = {}
        if server_timeout_seconds is not None:
            merged_request_headers["X-Nxus-Timeout-Seconds"] = str(server_timeout_seconds)
        if headers:
            merged_request_headers.update(headers)
        if merged_request_headers:
            kwargs["headers"] = merged_request_headers
        if timeout is not None:
            kwargs["timeout"] = timeout

        retry_budget = max(0, self._default_max_retries if max_retries is None else max_retries)
        log_verbose = self._verbose if verbose is None else verbose
        attempt = 0
        while True:
            self._log_request(method, path, params, merged_request_headers, attempt, retry_budget, log_verbose, raw=True)
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                if log_verbose:
                    self._logger.warn("timeout", {"method": method, "path": path, "attempt": attempt, "raw": True})
                raise
            except httpx.TransportError as exc:
                if log_verbose:
                    self._logger.warn(
                        "network-error",
                        {"method": method, "path": path, "attempt": attempt, "raw": True, "reason": str(exc)},
                    )
                if attempt >= retry_budget:
                    raise
                await asyncio.sleep(_compute_retry_delay(attempt))
                attempt += 1
                continue

            self._log_response(method, path, response, attempt, log_verbose, raw=True)
            if response.is_success:
                return response
            if attempt >= retry_budget or not _should_retry_response(response):
                return response

            delay = _compute_retry_delay(attempt, response)
            if log_verbose:
                self._logger.debug(
                    "retry-scheduled",
                    {"path": path, "attempt": attempt + 1, "delay_seconds": delay, "raw": True},
                )
            await asyncio.sleep(delay)
            attempt += 1

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncTransport":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # -- logging helpers ----------------------------------------------------

    def _log_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        per_request_headers: Dict[str, str],
        attempt: int,
        max_retries: int,
        verbose: bool,
        *,
        raw: bool = False,
    ) -> None:
        if not verbose:
            return
        all_headers = {**self._merged_headers, **per_request_headers}
        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "headers": _redact_headers(all_headers),
            "attempt": attempt,
            "max_retries": max_retries,
        }
        if params:
            ctx["params"] = params
        if raw:
            ctx["raw"] = True
        self._logger.debug("request", ctx)

    def _log_response(
        self,
        method: str,
        path: str,
        response: httpx.Response,
        attempt: int,
        verbose: bool,
        *,
        raw: bool = False,
    ) -> None:
        if not verbose:
            return
        ctx: Dict[str, Any] = {
            "method": method,
            "path": path,
            "attempt": attempt,
            "status": response.status_code,
        }
        if raw:
            ctx["raw"] = True
        if response.is_success:
            self._logger.debug("response", ctx)
        else:
            ctx["retry_after"] = _parse_retry_after(response.headers.get("retry-after"))
            ctx["should_retry"] = _parse_should_retry(response.headers.get("x-should-retry"))
            self._logger.warn("response", ctx)


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
