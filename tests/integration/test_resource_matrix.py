"""Registry-driven integration smoke tests for the live Nxus API.

The goal is broad endpoint confidence without writing one file per resource.
Read coverage is generated from the SDK resource registry. Mutating coverage is
table-driven and opt-in so it never runs accidentally against production.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
import httpx

from nxus_qbd.models import CreateVendorRequest
from nxus_qbd.errors import NxusApiError
from nxus_qbd.pagination import CursorPage
from nxus_qbd.resources import _RESOURCE_DEFS


READ_EXCLUDED = {"auth_sessions", "reports", "special_items"}
DEFAULT_LIST_CASES = [
    "vendors",
    "customers",
    "accounts",
    "invoices",
    "checks",
    "connections",
    "time_trackings",
    "bar_codes",
]
FULL_LIST_CASES = [
    namespace
    for namespace, *_rest in _RESOURCE_DEFS
    if namespace not in READ_EXCLUDED and "list" in _rest[-1]
]
LIST_CASES = (
    FULL_LIST_CASES
    if os.environ.get("NXUS_ENABLE_FULL_RESOURCE_MATRIX", "").lower() in {"1", "true", "yes"}
    else DEFAULT_LIST_CASES
)
KNOWN_BACKEND_BROKEN = {
    "credit_card_credits": "Backend dependency injection/service wiring is currently broken for this endpoint.",
}
KNOWN_LIST_RETRIEVE_INCONSISTENT = {
    "vendors": "List returns IDs that the retrieve endpoint does not currently accept.",
    "customers": "List returns IDs that the retrieve endpoint does not currently accept.",
    "invoices": "List returns IDs that the retrieve endpoint does not currently accept.",
    "checks": "List returns IDs that the retrieve endpoint does not currently accept.",
    "time_trackings": "List returns IDs that the retrieve endpoint does not currently accept.",
    "bar_codes": "List returns IDs that the retrieve endpoint does not currently accept.",
}


def _skip_if_backend_report_timeout(exc: NxusApiError) -> None:
    message = " ".join(
        str(part)
        for part in [str(exc), exc.user_message, exc.raw]
        if part
    ).lower()
    if "quickbooks desktop timeout" in message or "timeout for operation" in message:
        pytest.skip(f"Report generation timed out in the live QBD environment: {exc}")

REPORT_CASES = [
    ("retrieve_aging", {"report_type": "ARAgingSummary", "period": "ThisYear"}),
    (
        "retrieve_general_detail",
        {
            "report_type": "GeneralLedger",
            "from_report_date": "2025-01-01",
            "to_report_date": "2025-12-31",
        },
    ),
    (
        "retrieve_general_summary",
        {
            "report_type": "ProfitAndLossStandard",
            "from_report_date": "2025-01-01",
            "to_report_date": "2025-12-31",
        },
    ),
]


def _supports(namespace: str, operation: str) -> bool:
    for entry in _RESOURCE_DEFS:
        if entry[0] == namespace:
            return operation in entry[-1]
    return False


def _kwargs_for(namespace: str, connection_id: str | None) -> dict[str, Any]:
    if namespace == "connections":
        return {}
    if not connection_id:
        pytest.skip(f"{namespace} requires NXUS_CONNECTION_ID for live integration tests")
    return {"connection_id": connection_id}


@pytest.mark.parametrize("namespace", LIST_CASES)
def test_list_resource_matrix(client, connection_id, namespace: str):
    """Every list-capable resource should at least return a CursorPage."""
    resource = getattr(client, namespace)
    if namespace in KNOWN_BACKEND_BROKEN:
        pytest.xfail(KNOWN_BACKEND_BROKEN[namespace])

    try:
        page = resource.list(limit=1, **_kwargs_for(namespace, connection_id))
    except NxusApiError as exc:
        if exc.is_rate_limited:
            pytest.skip(f"{namespace} hit connection rate limits: {exc.user_message}")
        raise
    except httpx.ReadTimeout:
        pytest.skip(f"{namespace} timed out in live smoke coverage")

    assert isinstance(page, CursorPage)
    assert isinstance(page.data, list)
    assert isinstance(page.has_more, bool)


@pytest.mark.parametrize("namespace", [n for n in LIST_CASES if _supports(n, "retrieve")])
def test_retrieve_resource_matrix(client, connection_id, namespace: str):
    """If a list resource returns an item, retrieve() should accept its id."""
    resource = getattr(client, namespace)
    if namespace in KNOWN_BACKEND_BROKEN:
        pytest.xfail(KNOWN_BACKEND_BROKEN[namespace])
    if namespace in KNOWN_LIST_RETRIEVE_INCONSISTENT:
        pytest.xfail(KNOWN_LIST_RETRIEVE_INCONSISTENT[namespace])

    try:
        page = resource.list(limit=1, **_kwargs_for(namespace, connection_id))
    except NxusApiError as exc:
        if exc.is_rate_limited:
            pytest.skip(f"{namespace} hit connection rate limits: {exc.user_message}")
        raise
    except httpx.ReadTimeout:
        pytest.skip(f"{namespace} timed out in live smoke coverage")
    if not page.data:
        pytest.skip(f"{namespace} has no data in this environment")

    item = page.data[0]
    item_id = getattr(item, "id", None)
    if not item_id:
        pytest.skip(f"{namespace} items do not expose an id field for retrieve()")

    fetched = resource.retrieve(item_id, **_kwargs_for(namespace, connection_id))
    assert getattr(fetched, "id", None) == item_id


@pytest.mark.parametrize("method_name,params", REPORT_CASES)
def test_report_matrix(client, connection_id, method_name: str, params: dict[str, Any]):
    """A few report families should execute successfully against the live API."""
    if not connection_id:
        pytest.skip("Reports require NXUS_CONNECTION_ID for live integration tests")

    try:
        report = getattr(client.reports, method_name)(connection_id=connection_id, **params)
    except NxusApiError as exc:
        if exc.is_rate_limited:
            pytest.skip(f"Report smoke skipped due to connection rate limit: {exc.user_message}")
        _skip_if_backend_report_timeout(exc)
        raise
    except httpx.ReadTimeout:
        pytest.skip(f"Report smoke for {method_name} timed out")
    assert isinstance(report, dict)
    assert report


def test_connections_list_typed(client):
    """Connections should deserialize into typed response models."""
    try:
        page = client.connections.list(limit=1)
    except NxusApiError as exc:
        if exc.is_rate_limited:
            pytest.skip(f"Connections smoke skipped due to connection rate limit: {exc.user_message}")
        raise
    assert isinstance(page, CursorPage)
    if page.data:
        conn = page.data[0]
        assert getattr(conn, "id", None)


@pytest.mark.skipif(
    os.environ.get("NXUS_ENABLE_MUTATION_TESTS", "").lower() not in {"1", "true", "yes"},
    reason="Mutation tests are opt-in. Set NXUS_ENABLE_MUTATION_TESTS=true to enable.",
)
def test_mutation_registry_vendor_crud(client, connection_id):
    """Table-driven mutation smoke test for a canonical writable resource."""
    if not connection_id:
        pytest.skip("Mutation tests require NXUS_CONNECTION_ID")

    suffix = int(time.time())
    payload = CreateVendorRequest(
        name=f"SDK Smoke Vendor {suffix}",
        company_name=f"SDK Smoke Vendor {suffix}",
    )

    created = client.vendors.create(vendor=payload, connection_id=connection_id)
    try:
        assert created.id

        fetched = client.vendors.retrieve(created.id, connection_id=connection_id)
        assert fetched.id == created.id

        updated = client.vendors.update(
            created.id,
            connection_id=connection_id,
            revision_number=fetched.revision_number,
            name=f"SDK Smoke Vendor Updated {suffix}",
        )
        assert updated.id == created.id
    finally:
        client.vendors.delete(created.id, connection_id=connection_id)
