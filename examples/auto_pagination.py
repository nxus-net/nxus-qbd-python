"""Auto-pagination and manual page-by-page navigation with the Nxus SDK.

Demonstrates:
  - Sync auto-iteration: ``for customer in client.customers.list()``
  - Manual page-by-page navigation with ``page.get_next_page()``
  - Passing query parameters like ``limit``
  - Async auto-iteration with ``AsyncNxusClient`` and ``async for``

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python auto_pagination.py
"""

import asyncio
import sys

from nxus_qbd import NxusClient, AsyncNxusClient, NxusApiError

from _common import client_options, require_env


def sync_auto_iterate(client: NxusClient, connection_id: str) -> None:
    """Iterate over ALL customers across every page automatically.

    The CursorPage object returned by ``.list()`` implements ``__iter__``,
    which transparently fetches the next page when the current one is
    exhausted.  You never have to manage cursors yourself.
    """
    print("=== Sync Auto-Iteration ===\n")

    total = 0
    # The `limit` kwarg controls page size (how many items per request).
    # Iteration still walks through ALL pages.
    for customer in client.customers.list(connection_id=connection_id, limit=25):
        total += 1
        name = getattr(customer, "name", None) or getattr(customer, "full_name", None) or "unnamed"
        if total <= 5:
            print(f"  {total}. {name}")
        elif total == 6:
            print("  ...")

    print(f"\n  Total customers iterated: {total}\n")


def sync_manual_pages(client: NxusClient, connection_id: str) -> None:
    """Walk through pages manually using ``get_next_page()``.

    This is useful when you need per-page control — for example, to show
    page metadata, implement "Load More" in a UI, or stop early.
    """
    print("=== Manual Page-by-Page Navigation ===\n")

    page_num = 0
    page = client.customers.list(connection_id=connection_id, limit=10)

    while True:
        page_num += 1
        print(f"  Page {page_num}: {page.count} items  "
              f"(total_count={page.total_count}, has_more={page.has_more})")

        for customer in page.data:
            name = getattr(customer, "name", None) or getattr(customer, "full_name", None) or "unnamed"
            print(f"    - {name}")

        # Stop after 3 pages for this demo
        if page_num >= 3:
            print("\n  (stopped after 3 pages for demo purposes)")
            break

        if not page.has_next_page():
            print("\n  Reached the last page.")
            break

        page = page.get_next_page()

    print()


async def async_auto_iterate(connection_id: str, **kwargs) -> None:
    """Iterate over ALL customers asynchronously with ``async for``.

    The async client returns CursorPage objects that support
    ``__aiter__``, so you can use ``async for`` to iterate across all
    pages without blocking the event loop.
    """
    print("=== Async Auto-Iteration ===\n")

    async with AsyncNxusClient(**kwargs) as client:
        total = 0
        # The ``await`` is on ``.list()`` (it's an async method), then
        # ``async for`` handles page-to-page fetching.
        async for customer in await client.customers.list(connection_id=connection_id, limit=25):
            total += 1
            name = getattr(customer, "name", None) or getattr(customer, "full_name", None) or "unnamed"
            if total <= 5:
                print(f"  {total}. {name}")
            elif total == 6:
                print("  ...")

        print(f"\n  Total customers iterated (async): {total}\n")


def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )
    options = client_options()

    try:
        with NxusClient(**options) as client:
            sync_auto_iterate(client, connection_id)

            """ sync_auto_iterate() OUTPUT:
                === Sync Auto-Iteration ===

                1. TEST-19996293
                2. New Custy
                3. Store #55
                4. Kern Lighting Warehouse
                5. Store #45
                ...

                Total customers iterated: 68
            """
            sync_manual_pages(client, connection_id)

            """ sync_manual_pages() OUTPUT:
                === Manual Page-by-Page Navigation ===

                Page 1: 10 items  (total_count=68, has_more=True)
                    - TEST-19996293
                    - New Custy
                    - Store #55
                    - Kern Lighting Warehouse
                    - Store #45
                    - Store #44
                    - Store #43
                    - Store #42
                    - Store #41
                    - Store #40

                Page 2: 10 items  (total_count=68, has_more=True)
                    - Store #39
                    - Store #38
                    - Store #37
                    - Store #36
                    - Store #35
                    - Store #34
                    - Store #33
                    - Store #32
                    - Store #31
                    - Store #30

                Page 3: 10 items  (total_count=68, has_more=True)
                    - Store #29
                    - Store #28
                    - Store #27
                    - Store #26
                    - Store #25
                    - Store #24
                    - Store #23
                    - Store #22
                    - Store #21
                    - Store #20

                (stopped after 3 pages for demo purposes)
            """

        # Run the async example
        asyncio.run(async_auto_iterate(connection_id, **options))

        """ async_auto_iterate() OUTPUT:
            === Async Auto-Iteration ===

            1. TEST-19996293
            2. New Custy
            3. Store #55
            4. Kern Lighting Warehouse
            5. Store #45
            ...

            Total customers iterated (async): 68
        """

    except NxusApiError as exc:
        print(f"\nAPI Error: {exc.user_message} (status={exc.status})")
        sys.exit(1)


if __name__ == "__main__":
    main()
