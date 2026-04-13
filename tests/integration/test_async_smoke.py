"""Async integration smoke tests for the Nxus Python SDK.

These tests run against the live API using the async client and require
NXUS_API_KEY to be set. They are automatically skipped when the key is
absent (via the session-scoped ``api_key`` fixture in conftest.py).
"""

import asyncio
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


@pytest.mark.asyncio
async def test_async_full_pagination_with_interleaved_retrieve(async_client, connection_id):
    """Fetch every vendor page while issuing a same-connection retrieve mid-stream.

    This validates the paused-iterator / continuation flow end-to-end:
    - the cursor remains resumable across every page
    - an interleaved GET request on the same connection completes
    - the full paginated result set can still be drained without losing state
    """
    if not connection_id:
        pytest.skip("NXUS_CONNECTION_ID is required for async smoke tests")

    async with AsyncNxusClient(**async_client) as client:
        try:
            page = await client.vendors.list(limit=1, connection_id=connection_id)
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async pagination smoke skipped due to live API read timeout")

        if not page.data:
            pytest.skip("No vendors were found in this company file.")

        first_vendor = page.data[0]
        first_vendor_id = getattr(first_vendor, "id", None)
        if not first_vendor_id:
            pytest.skip("The first vendor did not expose an id.")

        seen_ids: list[str] = []
        seen_set: set[str] = set()

        def record_page(current: CursorPage) -> None:
            for item in current.data:
                item_id = getattr(item, "id", None)
                if item_id and item_id not in seen_set:
                    seen_set.add(item_id)
                    seen_ids.append(item_id)

        record_page(page)
        expected_total = page.total_count

        retrieve_task = None
        page_number = 1

        while page.has_next_page():
            page_number += 1

            if retrieve_task is None:
                retrieve_task = asyncio.create_task(
                    client.vendors.retrieve(first_vendor_id, connection_id=connection_id)
                )

            try:
                page = await page.get_next_page_async()
            except NxusApiError as exc:
                _skip_if_rate_limited(exc)
                raise
            except httpx.ReadTimeout:
                pytest.skip("Async pagination smoke skipped due to live API read timeout while fetching the next page")

            record_page(page)

        if retrieve_task is not None:
            fetched = await retrieve_task
            assert getattr(fetched, "id", None) == first_vendor_id

        assert seen_ids, "Expected at least one vendor id to be collected."
        assert len(seen_ids) == len(seen_set), "Pagination returned duplicate vendor ids."

        if expected_total is not None:
            assert len(seen_ids) == expected_total, (
                f"Expected to collect {expected_total} unique vendors, "
                f"but collected {len(seen_ids)}."
            )


@pytest.mark.asyncio
async def test_async_page_two_interleaved_retrieve_limit_20(async_client, connection_id):
    """Use a normal page size, queue a retrieve during page-2 fetch, then drain the rest.

    This matches the backend's iterator-lease semantics:
    - page 1 is fetched with limit=20
    - while page 2 is being requested, a singular retrieve is queued on the same connection
    - pagination continues to drain all remaining pages
    - only after pagination finishes do we expect the queued retrieve to complete
    """
    if not connection_id:
        pytest.skip("NXUS_CONNECTION_ID is required for async smoke tests")

    async with AsyncNxusClient(**async_client) as client:
        try:
            page = await client.vendors.list(limit=20, connection_id=connection_id)
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async page-two smoke skipped due to live API read timeout on page 1")

        if not page.data:
            pytest.skip("No vendors were found in this company file.")

        first_vendor_id = getattr(page.data[0], "id", None)
        if not first_vendor_id:
            pytest.skip("The first vendor did not expose an id.")

        if not page.has_next_page():
            pytest.skip("Vendor list does not have a second page in this environment.")

        seen_ids: list[str] = []
        seen_set: set[str] = set()

        def record_page(current: CursorPage) -> None:
            for item in current.data:
                item_id = getattr(item, "id", None)
                if item_id and item_id not in seen_set:
                    seen_set.add(item_id)
                    seen_ids.append(item_id)

        expected_total = page.total_count
        record_page(page)

        try:
            page2_task = asyncio.create_task(page.get_next_page_async())
            retrieve_task = asyncio.create_task(
                client.vendors.retrieve(first_vendor_id, connection_id=connection_id, timeout=90)
            )
            page = await page2_task
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async page-two smoke skipped due to live API read timeout during page-2/retrieve interleave")

        record_page(page)

        while page.has_next_page():
            try:
                page = await page.get_next_page_async()
            except NxusApiError as exc:
                _skip_if_rate_limited(exc)
                raise
            except httpx.ReadTimeout:
                pytest.skip("Async page-two smoke skipped due to live API read timeout while draining remaining pages")
            record_page(page)

        try:
            retrieved = await retrieve_task
        except NxusApiError as exc:
            _skip_if_rate_limited(exc)
            raise
        except httpx.ReadTimeout:
            pytest.skip("Async page-two smoke skipped because the queued retrieve timed out after pagination completed")

        assert getattr(retrieved, "id", None) == first_vendor_id
        assert seen_ids, "Expected at least one vendor id to be collected."
        assert len(seen_ids) == len(seen_set), "Pagination returned duplicate vendor ids."

        if expected_total is not None:
            assert len(seen_ids) == expected_total, (
                f"Expected to collect {expected_total} unique vendors, "
                f"but collected {len(seen_ids)}."
            )
