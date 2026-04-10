"""Async CRUD lifecycle for vendors using the Nxus QuickBooks Desktop SDK.

Demonstrates:
  - Creating a vendor with sample data (async)
  - Retrieving the vendor by ID
  - Updating the vendor name
  - Listing vendors (first page)
  - Deleting the vendor
  - Using ``async with`` context manager
  - Handling errors with NxusApiError

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python async_basic_crud.py
"""

import asyncio
import sys
import uuid

from nxus_qbd import AsyncNxusClient, NxusApiError
from nxus_qbd.models import AddressRequest, CreateVendorRequest

from _common import client_options, require_env


async def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    async with AsyncNxusClient(**client_options()) as client:
        try:
            # ---------------------------------------------------------------
            # 1. Create a vendor
            # ---------------------------------------------------------------
            # Use a unique name so the example can be run multiple times.
            unique_suffix = uuid.uuid4().hex[:8]
            vendor_name = f"Acme Office Supplies {unique_suffix}"

            print("Creating vendor...")
            vendor_request = CreateVendorRequest(
                name=vendor_name,
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
            print(f"  Created vendor: {vendor.name} (id={vendor_id})")

            # ---------------------------------------------------------------
            # 2. Retrieve the vendor by ID
            # ---------------------------------------------------------------
            print("\nRetrieving vendor...")
            fetched = await client.vendors.retrieve(vendor_id, connection_id=connection_id)
            print(f"  Retrieved: {fetched.name} (company={fetched.company_name})")

            # ---------------------------------------------------------------
            # 3. Update the vendor name
            # ---------------------------------------------------------------
            print("\nUpdating vendor name...")
            updated = await client.vendors.update(
                vendor_id,
                connection_id=connection_id,
                name="Acme Office Supplies (Updated)",
                revision_number=fetched.revision_number,
            )
            print(f"  Updated name: {updated.name}")

            # ---------------------------------------------------------------
            # 4. List vendors (first page)
            # ---------------------------------------------------------------
            print("\nListing vendors (first page)...")
            page = await client.vendors.list(limit=5, connection_id=connection_id)
            print(f"  Page has {page.count} vendors (total: {page.total_count})")
            for v in page.data:
                print(f"    - {v.name} (id={v.id})")

            # ---------------------------------------------------------------
            # 5. Delete the vendor
            # ---------------------------------------------------------------
            print("\nDeleting vendor...")
            await client.vendors.delete(vendor_id, connection_id=connection_id)
            print(f"  Deleted vendor {vendor_id}")

            print("\nAsync CRUD lifecycle complete.")

        except NxusApiError as exc:
            print(f"\nAPI Error: {exc.user_message}")
            print(f"  Status: {exc.status}")
            print(f"  Code:   {exc.code}")
            print(f'Message: {exc.raw}')
            if exc.validation_errors:
                print("  Validation errors:")
                for field, messages in exc.validation_errors.items():
                    for msg in messages:
                        print(f"    {field}: {msg}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
