"""Pulling reports from QuickBooks Desktop via the Nxus SDK.

Demonstrates:
  - Retrieving an aging report
  - Retrieving a general detail report
  - Retrieving a general summary report
  - Passing query parameters for date ranges and report types

Available report methods on ``client.reports``:
  - retrieve_aging
  - retrieve_general_detail
  - retrieve_general_summary
  - retrieve_budget_summary
  - retrieve_job
  - retrieve_time
  - retrieve_custom_detail
  - retrieve_custom_summary
  - retrieve_payroll_detail

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python reports.py
"""

import json
import sys

from nxus_qbd import NxusClient, NxusApiError

from _common import client_options, require_env


def print_report_summary(title: str, report: dict) -> None:
    """Pretty-print a truncated summary of a report response."""
    print(f"\n--- {title} ---\n")

    # Reports may include metadata fields like reportName, reportBasis, etc.
    for key in ("reportName", "reportBasis", "reportType",
                "dateFrom", "dateTo", "subtotalBy"):
        if key in report:
            print(f"  {key}: {report[key]}")

    # Print the first few rows if the report includes data rows
    rows = report.get("rows") or report.get("data") or []
    if isinstance(rows, list) and rows:
        print(f"  Row count: {len(rows)}")
        print("  First 3 rows (truncated):")
        for row in rows[:3]:
            # Compact JSON for readability
            print(f"    {json.dumps(row, default=str)[:120]}")
    elif isinstance(rows, dict) and rows:
        # Some reports return rows as a dict keyed by group/category
        print(f"  Row groups: {len(rows)}")
        print("  First 3 groups (truncated):")
        for i, (key, value) in enumerate(rows.items()):
            if i >= 3:
                break
            preview = json.dumps(value, default=str)[:100]
            print(f"    {key}: {preview}")
    else:
        # Show top-level keys for inspection
        print(f"  Response keys: {list(report.keys())}")

    print()


def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    with NxusClient(**client_options()) as client:
        try:
            # ---------------------------------------------------------------
            # 1. Aging report (e.g. A/R or A/P aging)
            # ---------------------------------------------------------------
            # Query parameters are passed as flat keyword arguments.
            # Common parameters include:
            #   - report_type: "APAgingDetail", "APAgingSummary",
            #                  "ARAgingDetail", "ARAgingSummary", etc.
            #   - period: "Today", "ThisMonth", "ThisYear", "All", etc.
            #   - from_report_date / to_report_date: explicit date range (YYYY-MM-DD)
            print("=== Aging Report ===")
            aging = client.reports.retrieve_aging(
                connection_id=connection_id,
                report_type="ARAgingSummary",
                period="ThisYear",
            )
            print_report_summary("A/R Aging Summary", aging)

            # ---------------------------------------------------------------
            # 2. General detail report
            # ---------------------------------------------------------------
            # General detail reports return row-level transaction data.
            # Specify date range with from_report_date / to_report_date.
            print("=== General Detail Report ===")
            detail = client.reports.retrieve_general_detail(
                connection_id=connection_id,
                report_type="GeneralLedger",
                from_report_date="2025-01-01",
                to_report_date="2025-12-31",
            )
            print_report_summary("General Ledger Detail", detail)

            # ---------------------------------------------------------------
            # 3. General summary report
            # ---------------------------------------------------------------
            # General summary reports return aggregated totals.
            print("=== General Summary Report ===")
            summary = client.reports.retrieve_general_summary(
                connection_id=connection_id,
                report_type="ProfitAndLossStandard",
                from_report_date="2025-01-01",
                to_report_date="2025-12-31",
                summarize_columns_by="Month",
            )
            print_report_summary("Profit & Loss Summary", summary)

            # ---------------------------------------------------------------
            # Tip: use **dict for dynamic parameter building.
            # ---------------------------------------------------------------
            report_params = {
                "report_type": "BalanceSheetStandard",
                "period": "ThisYear",
            }
            balance_sheet = client.reports.retrieve_general_summary(
                connection_id=connection_id,
                **report_params,
            )
            print_report_summary("Balance Sheet (via spread dict)", balance_sheet)

        except NxusApiError as exc:
            print(f"\nAPI Error: {exc.user_message}")
            print(f"  Status: {exc.status}")
            print(f"  Code:   {exc.code}")
            if exc.is_integration_error:
                print(f"  QBD integration code: {exc.integration_code}")
            sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
