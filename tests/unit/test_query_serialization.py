from __future__ import annotations

from typing import Any

from nxus_qbd.resources import ASYNC_RESOURCES, SYNC_RESOURCES


class FakeSyncTransport:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.response


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
