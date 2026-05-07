"""Unit tests for transport retry behavior."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from nxus_qbd._transport import AsyncTransport, SyncTransport
from nxus_qbd.errors import NxusApiError


API_URL = "https://api.example.test/"
RESOURCE_URL = "https://api.example.test/api/v1/connections/conn_123"


def _error_response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json={"error": {"message": "try again", "httpStatusCode": status}},
        headers=headers,
    )


@respx.mock
def test_sync_retries_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nxus_qbd._transport.time.sleep", lambda _delay: None)
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[
            _error_response(503),
            httpx.Response(200, json={"id": "conn_123"}),
        ]
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        result = transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2


@respx.mock
def test_sync_honors_x_should_retry_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nxus_qbd._transport.time.sleep", lambda _delay: None)
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[
            _error_response(400, {"X-Should-Retry": "true"}),
            httpx.Response(200, json={"id": "conn_123"}),
        ]
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        result = transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2


@respx.mock
def test_sync_honors_x_should_retry_false() -> None:
    route = respx.get(RESOURCE_URL).mock(
        return_value=_error_response(503, {"X-Should-Retry": "false"})
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        with pytest.raises(NxusApiError) as exc_info:
            transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert exc_info.value.status == 503
    assert route.call_count == 1


@respx.mock
def test_sync_per_request_max_retries_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nxus_qbd._transport.time.sleep", lambda _delay: None)
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[
            _error_response(503),
            httpx.Response(200, json={"id": "conn_123"}),
        ]
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test", max_retries=0)
    try:
        result = transport.request(
            "GET",
            "/api/v1/connections/conn_123",
            max_retries=1,
        )
    finally:
        transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2


@respx.mock
def test_sync_does_not_retry_409_by_default() -> None:
    # 409 is overloaded server-side: lock contention is transient, but
    # OutdatedEditSequence / NameNotUnique are terminal. Without
    # x-should-retry, the safe default is to surface to the caller.
    route = respx.get(RESOURCE_URL).mock(return_value=_error_response(409))

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        with pytest.raises(NxusApiError) as exc_info:
            transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert exc_info.value.status == 409
    assert route.call_count == 1


@respx.mock
def test_sync_retries_409_when_x_should_retry_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("nxus_qbd._transport.time.sleep", lambda _delay: None)
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[
            _error_response(409, {"X-Should-Retry": "true"}),
            httpx.Response(200, json={"id": "conn_123"}),
        ]
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        result = transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2


@respx.mock
def test_sync_uses_body_retry_after_when_header_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_delays: list[float] = []

    def fake_sleep(delay: float) -> None:
        captured_delays.append(delay)

    monkeypatch.setattr("nxus_qbd._transport.time.sleep", fake_sleep)
    body_response = httpx.Response(
        429,
        json={
            "error": {
                "message": "rate limited",
                "code": "RATE_LIMIT_EXCEEDED",
                "httpStatusCode": 429,
                "retryAfter": 1,
            }
        },
    )
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[body_response, httpx.Response(200, json={"id": "conn_123"})]
    )

    transport = SyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        result = transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2
    assert captured_delays == [1.0]


@respx.mock
@pytest.mark.asyncio
async def test_async_retries_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    route = respx.get(RESOURCE_URL).mock(
        side_effect=[
            _error_response(429, {"Retry-After": "1"}),
            httpx.Response(200, json={"id": "conn_123"}),
        ]
    )

    transport = AsyncTransport(base_url=API_URL, api_key="sk_test")
    try:
        result = await transport.request("GET", "/api/v1/connections/conn_123")
    finally:
        await transport.close()

    assert result == {"id": "conn_123"}
    assert route.call_count == 2
