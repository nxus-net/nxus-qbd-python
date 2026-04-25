from __future__ import annotations

from typing import Any

import pytest

from nxus_qbd.resources import ASYNC_RESOURCES, SYNC_RESOURCES


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
