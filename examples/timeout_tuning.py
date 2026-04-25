"""Timeout tuning examples for the Nxus QuickBooks Desktop SDK.

Shows three common patterns:

1. Using the SDK defaults
2. Raising the client-wide timeout for heavier workloads
3. Sending a paginated list timeout hint with `X-Nxus-Timeout-Seconds`
4. Overriding timeout on a CRUD request

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_CONNECTION_ID="<connection-id>"
    export NXUS_ENVIRONMENT="development"          # optional
    export NXUS_BASE_URL="https://localhost:7242/" # optional explicit override
    python examples/timeout_tuning.py
"""

from __future__ import annotations

import sys

from nxus_qbd import NxusApiError, NxusClient
from nxus_qbd._transport import DEFAULT_TIMEOUT_SECONDS

from _common import client_options, require_env


def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    print("SDK timeout reference")
    print(f"  Default client timeout: {DEFAULT_TIMEOUT_SECONDS:.0f}s")
    print("  Backend should usually timeout first and return a structured error.")
    print("  Paginated/list requests reuse timeout hints via X-Nxus-Timeout-Seconds.")
    print("  List requests also send X-Nxus-Timeout-Seconds when you pass timeout=...")

    try:
        # 1. Default timeout behavior: suitable for most users
        print("\n1. Default client timeout")
        with NxusClient(**client_options()) as client:
            vendor_page = client.vendors.list(limit=5, connection_id=connection_id)
            print(f"  Vendors page: count={vendor_page.count}, total={vendor_page.total_count}, has_more={vendor_page.has_more}")

        # 2. Global client override: useful for heavy report/query sessions
        print("\n2. Client-wide timeout override (120s)")
        with NxusClient(**client_options(), timeout=120) as client:
            transaction_page = client.transactions.list(
                limit=100,
                DetailLevel="all",
                connection_id=connection_id,
            )
            print(f"  Transactions page: count={transaction_page.count}, total={transaction_page.total_count}, has_more={transaction_page.has_more}")

        # 3. Paginated list timeout hint: keep the client default but tune the backend hint too
        print("\n3. Paginated list timeout hint (45s)")
        with NxusClient(**client_options()) as client:
            hinted_page = client.vendors.list(
                limit=10,
                connection_id=connection_id,
                timeout=45,
            )
            print(
                "  Vendors page with timeout hint: "
                f"count={hinted_page.count}, total={hinted_page.total_count}, has_more={hinted_page.has_more}"
            )

        # 4. Per-request CRUD override: still client-side only
        print("\n4. Per-request CRUD timeout override (30s)")
        with NxusClient(**client_options()) as client:
            fetched = client.vendors.retrieve(
                vendor_page.data[0].id,
                connection_id=connection_id,
                timeout=30,
            )
            print(f"  Retrieved vendor: {fetched.name} (id={fetched.id})")

        print("\nTimeout tuning example complete.")

    except NxusApiError as exc:
        print(f"\nAPI Error: {exc.user_message}")
        print(f"  Status: {exc.status}")
        print(f"  Code:   {exc.code}")
        print(f"  Raw:    {exc.raw}")
        sys.exit(1)


if __name__ == "__main__":
    main()
