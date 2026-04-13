"""Async multi-resource CRUD walkthrough for the Nxus QuickBooks Desktop SDK.

This example focuses on the resources we recently investigated most deeply:

- Vendors: full CRUD lifecycle
- Invoices: full CRUD lifecycle
- Time tracking: full CRUD lifecycle
- Bar codes: list + retrieve verification (the API surface is retrieve-only)

Why this file exists:
- it demonstrates the typed Python SDK in a real-world async flow
- it shows how to discover prerequisite IDs automatically
- it is useful for validating that create -> retrieve works against a stable
  QuickBooks session

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    export NXUS_CONNECTION_ID="<connection-id>"
    python async_basic_crud.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from nxus_qbd import AsyncNxusClient, NxusApiError
from nxus_qbd.models import (
    AddressRequest,
    CreateInvoiceRequest,
    CreateItemLineRequest,
    CreateTimeTrackingRequest,
    CreateVendorRequest,
)

from _common import client_options, require_env


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def first_id(resource: Any, connection_id: str, label: str, **filters: Any) -> str:
    """Return the first object ID from a list endpoint or abort with context."""
    page = await resource.list(limit=5, connection_id=connection_id, **filters)
    if not page.data:
        raise RuntimeError(f"No {label} records were found in this company file.")
    first = page.data[0]
    item_id = getattr(first, "id", None)
    if not item_id:
        raise RuntimeError(f"The first {label} record did not expose an id.")
    return item_id


async def run_vendor_crud(client: AsyncNxusClient, connection_id: str) -> None:
    section("1. Vendor CRUD")

    suffix = uuid.uuid4().hex[:8]
    vendor_request = CreateVendorRequest(
        name=f"Acme Office Supplies {suffix}",
        company_name="Acme Office Supplies Inc.",
        first_name="Jane",
        last_name="Smith",
        email="jane.smith@acme-supplies.example.com",
        phone="555-012-3456",
        billing_address=AddressRequest(
            line1="100 Commerce Blvd",
            city="Austin",
            state="TX",
            postal_code="73301",
        ),
    )

    vendor = await client.vendors.create(vendor=vendor_request, connection_id=connection_id)
    vendor_id = vendor.id
    print(f"Created vendor: {vendor.name} (id={vendor_id})")

    try:
        fetched = await client.vendors.retrieve(vendor_id, connection_id=connection_id)
        print(f"Retrieved vendor: {fetched.name} (company={fetched.company_name})")

        updated = await client.vendors.update(
            vendor_id,
            connection_id=connection_id,
            name=f"Acme Office Supplies {suffix} Updated",
            revision_number=fetched.revision_number,
        )
        print(f"Updated vendor name: {updated.name}")

        page = await client.vendors.list(limit=5, connection_id=connection_id)
        print(f"Listed {page.count} vendors on the first page (total={page.total_count})")
    finally:
        await client.vendors.delete(vendor_id, connection_id=connection_id)
        print(f"Deleted vendor: {vendor_id}")


async def run_invoice_crud(client: AsyncNxusClient, connection_id: str) -> None:
    section("2. Invoice CRUD")

    customer_id = await first_id(client.customers, connection_id, "customer")
    item_id = await first_id(client.service_items, connection_id, "service item")
    suffix = uuid.uuid4().hex[:6]

    invoice_request = CreateInvoiceRequest(
        customer_id=customer_id,
        transaction_date="2026-04-11",
        memo=f"SDK invoice example {suffix}",
        ref_number=f"EX{suffix[:4].upper()}",
        lines=[
            CreateItemLineRequest(
                item_id=item_id,
                description="SDK invoice line",
                quantity=1,
                rate=1.0,
                amount=1.0,
            )
        ],
    )

    invoice = await client.invoices.create(invoice=invoice_request, connection_id=connection_id)
    invoice_id = invoice.id
    print(f"Created invoice: id={invoice_id}, ref_number={invoice.ref_number}")

    try:
        fetched = await client.invoices.retrieve(invoice_id, connection_id=connection_id)
        print(
            "Retrieved invoice:",
            f"id={fetched.id},",
            f"ref_number={fetched.ref_number},",
            f"customer={getattr(getattr(fetched, 'customer', None), 'id', None)}",
        )

        updated = await client.invoices.update(
            invoice_id,
            connection_id=connection_id,
            revision_number=fetched.revision_number,
            memo="SDK invoice example (updated)",
        )
        print(f"Updated invoice memo: {updated.memo}")

        page = await client.invoices.list(limit=5, connection_id=connection_id)
        print(f"Listed {page.count} invoices on the first page (total={page.total_count})")
    finally:
        await client.invoices.delete(invoice_id, connection_id=connection_id)
        print(f"Deleted invoice: {invoice_id}")


async def run_time_tracking_crud(client: AsyncNxusClient, connection_id: str) -> None:
    section("3. Time Tracking CRUD")

    entity_id = await first_id(client.employees, connection_id, "employee")
    service_item_id = await first_id(client.service_items, connection_id, "service item")
    customer_id = await first_id(client.customers, connection_id, "customer")

    time_request = CreateTimeTrackingRequest(
        transaction_date="2026-04-11",
        entity_id=entity_id,
        customer_id=customer_id,
        item_service_id=service_item_id,
        duration="PT1H0M0S",
        notes="SDK time tracking example",
    )

    time_entry = await client.time_trackings.create(
        time_tracking=time_request,
        connection_id=connection_id,
    )
    time_entry_id = time_entry.id
    print(
        "Created time entry:",
        f"id={time_entry_id},",
        f"duration={time_entry.duration},",
        f"transaction_date={time_entry.transaction_date}",
    )

    try:
        fetched = await client.time_trackings.retrieve(time_entry_id, connection_id=connection_id)
        print(
            "Retrieved time entry:",
            f"id={fetched.id},",
            f"duration={fetched.duration},",
            f"notes={fetched.notes}",
        )

        updated = await client.time_trackings.update(
            time_entry_id,
            connection_id=connection_id,
            revision_number=fetched.revision_number,
            entity_id=entity_id,
            duration="PT1H30M0S",
            notes="SDK time tracking example (updated)",
        )
        print(f"Updated time entry: duration={updated.duration}, notes={updated.notes}")

        page = await client.time_trackings.list(limit=5, connection_id=connection_id)
        print(f"Listed {page.count} time entries on the first page (total={page.total_count})")
    finally:
        await client.time_trackings.delete(time_entry_id, connection_id=connection_id)
        print(f"Deleted time entry: {time_entry_id}")


async def run_bar_code_probe(client: AsyncNxusClient, connection_id: str) -> None:
    section("4. Bar Code Retrieve Verification")

    print(
        "Bar codes do not support normal create/update in the same way as the\n"
        "other resources above, so this section demonstrates the supported\n"
        "list -> retrieve flow against an existing record."
    )

    page = await client.bar_codes.list(limit=5, connection_id=connection_id)
    if not page.data:
        print("No bar codes were found in this company file, so the retrieve probe was skipped.")
        return

    barcode = page.data[0]
    print(
        "Listed barcode:",
        f"id={barcode.id},",
        f"name={barcode.name},",
        f"list_type={barcode.list_type}",
    )

    try:
        fetched = await client.bar_codes.retrieve(barcode.id, connection_id=connection_id)
        print(
            "Retrieved barcode:",
            f"id={fetched.id},",
            f"name={fetched.name},",
            f"revision_number={fetched.revision_number}",
        )
    except NxusApiError as exc:
        print("Bar code retrieve did not round-trip cleanly in this environment.")
        print(f"  Status: {exc.status}")
        print(f"  Message: {exc.user_message}")
        print("  This is useful diagnostic information rather than a Python SDK syntax issue.")


async def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    async with AsyncNxusClient(**client_options()) as client:
        try:
            await run_vendor_crud(client, connection_id)
            await run_invoice_crud(client, connection_id)
            await run_time_tracking_crud(client, connection_id)
            await run_bar_code_probe(client, connection_id)
            print("\nAsync multi-resource walkthrough complete.")

        except (NxusApiError, RuntimeError) as exc:
            print(f"\nExample aborted: {exc}")
            if isinstance(exc, NxusApiError):
                print(f"  Status: {exc.status}")
                print(f"  Code:   {exc.code}")
                print(f"  Raw:    {exc.raw}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
