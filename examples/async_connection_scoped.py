"""Async multi-company data isolation using connection-scoped requests.

Demonstrates:
  - Passing ``connection_id`` per request to scope data to a specific
    QuickBooks Desktop company file (async)
  - Switching between connections
  - The tenant vs. connection isolation model

Background:
  The Nxus API uses a two-level isolation model:

    Tenant (API key)
      Your organization.  Identified by your API key (``sk_live_...``).
      A single tenant can have many QuickBooks Desktop connections.

    Connection (X-Connection-Id header)
      A single QuickBooks Desktop company file linked to your tenant.
      Each connection has its own vendors, customers, invoices, etc.
      When you pass ``connection_id`` on an SDK method, it sets the
      ``X-Connection-Id`` header, scoping the request to that company.

  If your tenant has only one connection you can omit ``connection_id``
  and the API will use the default connection.

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"              # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"        # optional explicit override
    export NXUS_CONNECTION_ID_A="<connection-guid-a>"   # first company
    export NXUS_CONNECTION_ID_B="<connection-guid-b>"   # second company
    python async_connection_scoped.py
"""

import asyncio
import os
import sys

from nxus_qbd import AsyncNxusClient, NxusApiError

from _common import client_options, require_env


async def list_vendors_for_connection(
    client: AsyncNxusClient,
    connection_id: str,
    label: str,
) -> None:
    """List the first few vendors scoped to a given connection (async)."""
    print(f"\n--- Vendors for {label} (connection: {connection_id}) ---\n")

    page = await client.vendors.list(limit=5, connection_id=connection_id)
    print(f"  Total vendors: {page.total_count}")
    for vendor in page.data:
        print(f"    - {vendor.name} (id={vendor.id})")

    if page.count == 0:
        print("    (no vendors found)")


async def main() -> None:
    connection_a = require_env(
        "NXUS_CONNECTION_ID_A",
        "Set it to the GUID (or externalId) of your first QBD connection.",
    )
    connection_b = os.environ.get("NXUS_CONNECTION_ID_B")

    async with AsyncNxusClient(**client_options()) as client:
        try:
            # -----------------------------------------------------------------
            # List connections available to this tenant
            # -----------------------------------------------------------------
            print("=== Available Connections (async) ===\n")
            connections_page = await client.connections.list(limit=10)
            for conn in connections_page.data:
                status = getattr(conn, "lifecycle_state", None) or "unknown"
                name = getattr(conn, "company_name", None) or getattr(conn, "description", None) or conn.id
                print(f"  {conn.id}  {name}  (state={status})")

            # -----------------------------------------------------------------
            # Scope requests to Connection A
            # -----------------------------------------------------------------
            await list_vendors_for_connection(client, connection_a, "Company A")

            # -----------------------------------------------------------------
            # Scope requests to Connection B (if provided)
            # -----------------------------------------------------------------
            if connection_b:
                await list_vendors_for_connection(client, connection_b, "Company B")
            else:
                print("\n  (Skipping Company B — NXUS_CONNECTION_ID_B not set)")

            # -----------------------------------------------------------------
            # Per-request connection_id also works on create/update/delete
            # -----------------------------------------------------------------
            print("\n=== Create a vendor in Company A (async) ===\n")
            vendor = await client.vendors.create(
                connection_id=connection_a,
                name="Demo Supplier (Async Connection-Scoped)",
                company_name="Demo Supplier LLC",
            )
            print(f"  Created vendor '{vendor.name}' in Company A")

            # Clean up
            await client.vendors.delete(vendor.id, connection_id=connection_a)
            print(f"  Deleted vendor '{vendor.name}' from Company A")

        except NxusApiError as exc:
            print(f"\nAPI Error: {exc.user_message} (status={exc.status}, code={exc.code})")
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
