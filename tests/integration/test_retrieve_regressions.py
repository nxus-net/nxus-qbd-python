"""Focused retrieve regression coverage for known list -> retrieve mismatches.

These tests intentionally exercise the contract pattern we have been debugging:

1. list a resource
2. take the first returned ``id``
3. immediately call ``retrieve(id)``

The goal is to prove whether singular detail endpoints accept the IDs surfaced by
their corresponding list endpoints in the current live environment.
"""

from __future__ import annotations

from typing import Any

import pytest
import httpx

from nxus_qbd.errors import NxusApiError


RETRIEVE_REGRESSION_CASES = [
    ("vendors", "vendor"),
    ("invoices", "invoice"),
    ("time_trackings", "time tracking entry"),
    ("bar_codes", "bar code"),
]


def _resource_kwargs(namespace: str, connection_id: str | None) -> dict[str, Any]:
    if not connection_id:
        pytest.skip(f"{namespace} requires NXUS_CONNECTION_ID for live integration tests")
    return {"connection_id": connection_id}


@pytest.mark.parametrize("namespace,label", RETRIEVE_REGRESSION_CASES)
def test_list_then_retrieve_regression_matrix(client, connection_id, namespace: str, label: str):
    """List a resource, capture the first returned id, then retrieve it directly."""
    resource = getattr(client, namespace)

    try:
        page = resource.list(limit=1, **_resource_kwargs(namespace, connection_id))
    except NxusApiError as exc:
        if exc.is_rate_limited:
            pytest.skip(f"{namespace} hit connection rate limits: {exc.user_message}")
        raise
    except httpx.ReadTimeout:
        pytest.skip(f"{namespace} timed out in live regression coverage")

    if not page.data:
        pytest.skip(f"No {label} records were found in this company file.")

    first = page.data[0]
    item_id = getattr(first, "id", None)
    if not item_id:
        pytest.fail(f"The first {label} record did not expose an id.")

    try:
        fetched = resource.retrieve(item_id, **_resource_kwargs(namespace, connection_id))
    except NxusApiError as exc:
        pytest.fail(
            f"{namespace}.retrieve({item_id}) failed after list() returned that same id. "
            f"status={exc.status}, code={exc.code}, raw={exc.raw}"
        )

    assert getattr(fetched, "id", None) == item_id
