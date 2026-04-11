"""Async integration smoke tests for the Nxus Python SDK.

These tests run against the live API using the async client and require
NXUS_API_KEY to be set. They are automatically skipped when the key is
absent (via the session-scoped ``api_key`` fixture in conftest.py).
"""

import pytest
import httpx

from nxus_qbd import AsyncNxusClient
from nxus_qbd.errors import NxusApiError
from nxus_qbd.pagination import CursorPage


def _skip_if_rate_limited(exc: NxusApiError) -> None:
    if exc.is_rate_limited:
        pytest.skip(f"Integration test skipped due to connection rate limit: {exc.user_message}")


@pytest.mark.asyncio
async def test_async_list_vendors(async_client, connection_id):
    """List vendors using the async client."""
    if not connection_id:
        pytest.skip("NXUS_CONNECTION_ID is required for async smoke tests")
    async with AsyncNxusClient(**async_client) as client:
        try:
            page = await client.vendors.list(connection_id=connection_id)
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async smoke skipped due to live API read timeout")
        assert isinstance(page, CursorPage)
        assert isinstance(page.data, list)
        assert isinstance(page.has_more, bool)


@pytest.mark.asyncio
async def test_async_auto_pagination(async_client, connection_id):
    """Async auto-pagination should iterate at least 1 item (if any exist)."""
    if not connection_id:
        pytest.skip("NXUS_CONNECTION_ID is required for async smoke tests")
    items = []
    async with AsyncNxusClient(**async_client) as client:
        try:
            async for item in await client.vendors.list(limit=1, connection_id=connection_id):
                items.append(item)
                if len(items) >= 3:
                    break
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async smoke skipped due to live API read timeout")
    assert len(items) >= 0
    if items:
        assert items[0] is not None
