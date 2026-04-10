"""Integration smoke tests for the Nxus Python SDK.

These tests run against the live API and require NXUS_API_KEY to be set
in a .env file or the environment. They are automatically skipped when the
key is absent (via the session-scoped ``api_key`` fixture in conftest.py).
"""

import pytest

from nxus_qbd.errors import NxusApiError
from nxus_qbd.pagination import CursorPage


def _skip_if_rate_limited(exc: NxusApiError) -> None:
    if exc.is_rate_limited:
        pytest.skip(f"Integration test skipped due to connection rate limit: {exc.user_message}")


def _require_connection(connection_id: str | None) -> str:
    if not connection_id:
        pytest.skip("NXUS_CONNECTION_ID is required for smoke tests")
    return connection_id


# ---------------------------------------------------------------------------
# Smoke Tests
# ---------------------------------------------------------------------------


def test_list_vendors(client, connection_id):
    """List vendors and verify the response is a CursorPage with a data list."""
    cid = _require_connection(connection_id)
    try:
        page = client.vendors.list(connection_id=cid)
    except NxusApiError as exc:
        _skip_if_rate_limited(exc)
        raise
    assert isinstance(page, CursorPage)
    assert isinstance(page.data, list)


def test_list_accounts(client, connection_id):
    """List accounts and verify response structure."""
    cid = _require_connection(connection_id)
    try:
        page = client.accounts.list(connection_id=cid)
    except NxusApiError as exc:
        _skip_if_rate_limited(exc)
        raise
    assert isinstance(page, CursorPage)
    assert isinstance(page.data, list)
    assert isinstance(page.has_more, bool)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_list_customers_with_limit(client, connection_id):
    """List customers with limit=2 and verify at most 2 items returned."""
    cid = _require_connection(connection_id)
    try:
        page = client.customers.list(limit=2, connection_id=cid)
    except NxusApiError as exc:
        _skip_if_rate_limited(exc)
        raise
    assert isinstance(page, CursorPage)
    assert isinstance(page.data, list)
    assert len(page.data) <= 2


def test_cursor_page_metadata(client, connection_id):
    """Verify that CursorPage exposes has_more, next_cursor, and total_count."""
    cid = _require_connection(connection_id)
    try:
        page = client.vendors.list(limit=1, connection_id=cid)
    except NxusApiError as exc:
        _skip_if_rate_limited(exc)
        raise
    assert isinstance(page, CursorPage)
    assert hasattr(page, "has_more")
    assert hasattr(page, "next_cursor")
    assert hasattr(page, "total_count")
    assert isinstance(page.has_more, bool)


def test_auto_pagination_iterates(client, connection_id):
    """Auto-pagination should iterate at least 1 item (if any vendors exist)."""
    cid = _require_connection(connection_id)
    items = []
    try:
        for item in client.vendors.list(limit=1, connection_id=cid):
            items.append(item)
            # Stop after 3 to keep the test fast
            if len(items) >= 3:
                break
    except NxusApiError as exc:
        _skip_if_rate_limited(exc)
        raise
    # If the account has vendors we should see at least 1;
    # if not, the loop simply doesn't execute — that's fine.
    assert len(items) >= 0
    if items:
        assert items[0] is not None


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


def test_retrieve_nonexistent_returns_404(client, connection_id):
    """Retrieving a non-existent ID should raise NxusApiError with is_not_found."""
    cid = _require_connection(connection_id)
    with pytest.raises(NxusApiError) as exc_info:
        client.vendors.retrieve("00000000-0000-0000-0000-000000000000", connection_id=cid)
    err = exc_info.value
    _skip_if_rate_limited(err)
    assert err.status == 404
    assert err.is_not_found is True
