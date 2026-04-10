"""Page-by-page pagination walkthrough with the Nxus QuickBooks Desktop SDK.

Demonstrates:
  - Fetching all pages of a paginated endpoint with a limit of 20
  - Logging the first 5 items on each page
  - Showing page metadata (page number, count, total, cursor)
  - Both sync and async variants

Usage:
    # Ensure .env is configured with NXUS_API_KEY, NXUS_BASE_URL,
    # NXUS_CONNECTION_ID, and optionally NXUS_ENVIRONMENT.
    python pagination_walkthrough.py
"""

import asyncio
import sys

from nxus_qbd import NxusClient, AsyncNxusClient, NxusApiError

from _common import client_options, require_env


PAGE_LIMIT = 20
MAX_PREVIEW = 5


def print_page_preview(page_num: int, page) -> None:
    """Print metadata and the first few items for a single page."""
    print(f"\n  Page {page_num}")
    print(f"  ├── items on page : {page.count}")
    print(f"  ├── total_count   : {page.total_count}")
    print(f"  ├── has_more      : {page.has_more}")
    print(f"  ├── next_cursor   : {page.next_cursor or '(none)'}")
    print(f"  └── first {min(MAX_PREVIEW, page.count)} items:")

    for i, item in enumerate(page.data[:MAX_PREVIEW]):
        name = (
            getattr(item, "name", None)
            or getattr(item, "full_name", None)
            or getattr(item, "company_name", None)
            or "(unnamed)"
        )
        print(f"       {i + 1}. {name}")

    if page.count > MAX_PREVIEW:
        print(f"       ... and {page.count - MAX_PREVIEW} more")


# ---------------------------------------------------------------------------
# Sync walkthrough
# ---------------------------------------------------------------------------

def sync_pagination_walkthrough(client: NxusClient, connection_id: str) -> None:
    """Fetch every page of vendors synchronously, printing a preview of each."""
    print("=" * 60)
    print("  Sync Pagination Walkthrough  (limit={})".format(PAGE_LIMIT))
    print("=" * 60)

    page = client.vendors.list(connection_id=connection_id, limit=PAGE_LIMIT)
    page_num = 1
    total_items = 0

    while True:
        print_page_preview(page_num, page)
        total_items += page.count

        if not page.has_next_page():
            break

        page = page.get_next_page()
        page_num += 1

    print(f"\n  Done. {page_num} page(s), {total_items} total items.\n")


# ---------------------------------------------------------------------------
# Async walkthrough
# ---------------------------------------------------------------------------

async def async_pagination_walkthrough(
    connection_id: str,
    **kwargs,
) -> None:
    """Fetch every page of vendors asynchronously, printing a preview of each."""
    print("=" * 60)
    print("  Async Pagination Walkthrough  (limit={})".format(PAGE_LIMIT))
    print("=" * 60)

    async with AsyncNxusClient(**kwargs) as client:
        page = await client.vendors.list(connection_id=connection_id, limit=PAGE_LIMIT)
        page_num = 1
        total_items = 0

        while True:
            print_page_preview(page_num, page)
            total_items += page.count

            if not page.has_next_page():
                break

            page = await page.get_next_page_async()
            page_num += 1

        print(f"\n  Done. {page_num} page(s), {total_items} total items.\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )
    options = client_options()

    try:
        # --- Sync ---
        with NxusClient(**options) as client:
            sync_pagination_walkthrough(client, connection_id)

        # --- Async ---
        asyncio.run(async_pagination_walkthrough(connection_id, **options))

    except NxusApiError as exc:
        print(f"\nAPI Error: {exc.user_message} (status={exc.status})")
        sys.exit(1)


if __name__ == "__main__":
    main()
