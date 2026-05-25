from __future__ import annotations

import asyncio
from typing import Any

import pytest

from nxus_qbd.resources import ASYNC_RESOURCES, SYNC_RESOURCES, _RESOURCE_DEFS


EXPECTED_VOID_RESOURCES = [
    "ar_refund_credit_cards",
    "bills",
    "check_bill_payments",
    "checks",
    "credit_card_bill_payments",
    "credit_card_credits",
    "deposits",
    "item_receipts",
    "journal_entries",
    "sales_receipts",
    "vendor_credits",
    "charges",
    "credit_card_charges",
    "credit_memos",
    "inventory_adjustments",
    "invoices",
]

VOID_RESOURCE_PATHS = [
    (namespace, singular_path.format(id="txn_123") + "/void")
    for namespace, _list_path, singular_path, _create_path, methods in _RESOURCE_DEFS
    if "void" in methods
]


class FakeSyncTransport:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.response


class QueuedSyncTransport:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.responses.pop(0)


class QueuedAsyncTransport:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.responses.pop(0)


def _wire_vendor(vendor_id: str, company_name: str = "Acme") -> dict[str, Any]:
    return {
        "id": vendor_id,
        "objectType": "qbd_vendor",
        "name": company_name,
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-01T00:00:00Z",
        "revisionNumber": "1",
        "companyName": company_name,
        "phone": "555-0100",
    }


def _wire_void_response(object_type: str = "Invoice") -> dict[str, Any]:
    return {
        "id": "txn_123",
        "objectType": object_type,
        "status": "voided",
        "voided": True,
        "refNumber": "REF-123",
    }


def test_void_resource_registry_matches_supported_qbd_transaction_endpoints():
    assert [namespace for namespace, _path in VOID_RESOURCE_PATHS] == EXPECTED_VOID_RESOURCES


def test_sync_void_resources_post_to_singular_void_endpoints():
    for namespace, expected_path in VOID_RESOURCE_PATHS:
        transport = FakeSyncTransport(_wire_void_response(namespace))
        resource = SYNC_RESOURCES[namespace](transport)

        result = resource.void(
            "txn_123",
            connection_id="conn-1",
            headers={"X-Custom-Header": "custom"},
            server_timeout_seconds=75,
        )

        assert result.id == "txn_123"
        assert result.object_type == namespace
        assert result.status == "voided"
        assert result.voided is True

        call = transport.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == expected_path
        assert call["headers"]["X-Connection-Id"] == "conn-1"
        assert call["headers"]["X-Custom-Header"] == "custom"
        assert call["headers"]["X-Nxus-Timeout-Seconds"] == "75"
        assert "params" not in call
        assert "json" not in call


@pytest.mark.asyncio
async def test_async_void_posts_to_singular_void_endpoint():
    transport = QueuedAsyncTransport(_wire_void_response())
    resource = ASYNC_RESOURCES["invoices"](transport)

    result = await resource.void("txn_123", connection_id="conn-1")

    assert result.id == "txn_123"
    assert result.object_type == "Invoice"
    assert result.voided is True
    assert transport.calls == [
        {
            "method": "POST",
            "path": "/api/v1/invoice/txn_123/void",
            "headers": {"X-Connection-Id": "conn-1"},
        }
    ]


def test_list_serializes_snake_case_query_params():
    transport = FakeSyncTransport(
        {"data": [], "hasMore": False, "nextCursor": None, "count": 0}
    )
    resource = SYNC_RESOURCES["vendors"](transport)

    resource.list(
        connection_id="conn-1",
        limit=5,
        updated_since="2026-01-01",
        name_starts_with="Acme",
    )

    call = transport.calls[0]
    assert call["params"] == {
        "limit": 5,
        "updatedSince": "2026-01-01",
        "nameStartsWith": "Acme",
    }


def test_list_sends_timeout_hint_header_and_preserves_it_across_next_page():
    transport = QueuedSyncTransport(
        {
            "data": [_wire_vendor("vendor-1")],
            "hasMore": True,
            "nextCursor": "cursor-2",
            "count": 1,
        },
        {
            "data": [_wire_vendor("vendor-2", "Beta")],
            "hasMore": False,
            "nextCursor": None,
            "count": 1,
        },
    )
    resource = SYNC_RESOURCES["vendors"](transport)

    page = resource.list(
        connection_id="conn-1",
        limit=1,
        timeout=45,
        headers={"X-Custom-Header": "custom"},
    )
    page_2 = page.get_next_page()

    first_call = transport.calls[0]
    second_call = transport.calls[1]

    assert page.data[0].id == "vendor-1"
    assert page_2.data[0].id == "vendor-2"

    assert first_call["params"] == {"limit": 1}
    assert second_call["params"] == {"limit": 1, "cursor": "cursor-2"}
    assert "timeoutSeconds" not in first_call["params"]
    assert "timeoutSeconds" not in second_call["params"]

    assert first_call["headers"]["X-Connection-Id"] == "conn-1"
    assert second_call["headers"]["X-Connection-Id"] == "conn-1"
    assert first_call["headers"]["X-Custom-Header"] == "custom"
    assert second_call["headers"]["X-Custom-Header"] == "custom"
    assert first_call["headers"]["X-Nxus-Timeout-Seconds"] == "45"
    assert second_call["headers"]["X-Nxus-Timeout-Seconds"] == "45"
    assert first_call["timeout"] == 45
    assert second_call["timeout"] == 45


def test_server_timeout_seconds_is_sent_as_header_not_query_or_body():
    transport = FakeSyncTransport(_wire_vendor("vendor-1"))
    resource = SYNC_RESOURCES["vendors"](transport)

    resource.create(name="Acme", server_timeout_seconds=80)

    call = transport.calls[0]
    assert call["json"] == {"name": "Acme"}
    assert call["headers"]["X-Nxus-Timeout-Seconds"] == "80"

    transport = FakeSyncTransport(
        {"data": [], "hasMore": False, "nextCursor": None, "count": 0}
    )
    resource = SYNC_RESOURCES["vendors"](transport)

    resource.list(limit=1, timeout=45, server_timeout_seconds=70)

    call = transport.calls[0]
    assert call["params"] == {"limit": 1}
    assert call["timeout"] == 45
    assert call["headers"]["X-Nxus-Timeout-Seconds"] == "70"


def test_report_serializes_snake_case_query_params():
    transport = FakeSyncTransport({"rows": []})
    resource = SYNC_RESOURCES["reports"](transport)

    resource.retrieve_general_summary(
        connection_id="conn-1",
        report_type="ProfitAndLossStandard",
        from_report_date="2025-01-01",
        to_report_date="2025-12-31",
        summarize_columns_by="Month",
    )

    call = transport.calls[0]
    assert call["params"] == {
        "reportType": "ProfitAndLossStandard",
        "fromReportDate": "2025-01-01",
        "toReportDate": "2025-12-31",
        "summarizeColumnsBy": "Month",
    }


def test_report_keeps_existing_camel_case_params():
    transport = FakeSyncTransport({"rows": []})
    resource = SYNC_RESOURCES["reports"](transport)

    resource.retrieve_aging(
        connection_id="conn-1",
        reportType="ARAgingSummary",
        period="ThisYear",
    )

    call = transport.calls[0]
    assert call["params"] == {
        "reportType": "ARAgingSummary",
        "period": "ThisYear",
    }


@pytest.mark.asyncio
async def test_async_list_sends_timeout_hint_header_and_preserves_it_across_next_page():
    transport = QueuedAsyncTransport(
        {
            "data": [_wire_vendor("vendor-1")],
            "hasMore": True,
            "nextCursor": "cursor-2",
            "count": 1,
        },
        {
            "data": [_wire_vendor("vendor-2", "Beta")],
            "hasMore": False,
            "nextCursor": None,
            "count": 1,
        },
    )
    resource = ASYNC_RESOURCES["vendors"](transport)

    page = await resource.list(
        connection_id="conn-1",
        limit=1,
        timeout=60,
        headers={"X-Custom-Header": "custom"},
    )
    page_2 = await page.get_next_page_async()

    first_call = transport.calls[0]
    second_call = transport.calls[1]

    assert page.data[0].id == "vendor-1"
    assert page_2.data[0].id == "vendor-2"

    assert first_call["params"] == {"limit": 1}
    assert second_call["params"] == {"limit": 1, "cursor": "cursor-2"}
    assert "timeoutSeconds" not in first_call["params"]
    assert "timeoutSeconds" not in second_call["params"]

    assert first_call["headers"]["X-Connection-Id"] == "conn-1"
    assert second_call["headers"]["X-Connection-Id"] == "conn-1"
    assert first_call["headers"]["X-Custom-Header"] == "custom"
    assert second_call["headers"]["X-Custom-Header"] == "custom"
    assert first_call["headers"]["X-Nxus-Timeout-Seconds"] == "60"
    assert second_call["headers"]["X-Nxus-Timeout-Seconds"] == "60"
    assert first_call["timeout"] == 60
    assert second_call["timeout"] == 60


def test_sync_auto_pagination_closes_cursor_on_early_exit():
    transport = QueuedSyncTransport(
        {
            "data": [_wire_vendor("vendor-1")],
            "hasMore": True,
            "nextCursor": "cursor-2",
            "count": 1,
        },
        None,
    )
    resource = SYNC_RESOURCES["vendors"](transport)

    page = resource.list(limit=1)

    for item in page:
        assert item.id == "vendor-1"
        break

    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["path"] == "/api/v1/vendors"
    assert transport.calls[1]["method"] == "POST"
    assert transport.calls[1]["path"] == "/api/v1/cursors/cursor-2/close"
    assert "X-Connection-Id" not in transport.calls[1].get("headers", {})


@pytest.mark.asyncio
async def test_async_auto_pagination_closes_cursor_on_early_exit():
    transport = QueuedAsyncTransport(
        {
            "data": [_wire_vendor("vendor-1")],
            "hasMore": True,
            "nextCursor": "cursor-2",
            "count": 1,
        },
        None,
    )
    resource = ASYNC_RESOURCES["vendors"](transport)

    page = await resource.list(limit=1)

    async for item in page:
        assert item.id == "vendor-1"
        break

    await asyncio.sleep(0.01)

    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["path"] == "/api/v1/vendors"
    assert transport.calls[1]["method"] == "POST"
    assert transport.calls[1]["path"] == "/api/v1/cursors/cursor-2/close"
    assert "X-Connection-Id" not in transport.calls[1].get("headers", {})
