"""Auto-pagination and manual page-by-page navigation with the Nxus SDK.

Demonstrates:
  - Sync auto-iteration: ``for customer in client.customers.list()``
  - Manual page-by-page navigation with ``page.get_next_page()``
  - Find-and-stop: breaking out of an auto-iterator early
  - Passing query parameters like ``limit``
  - Async auto-iteration with ``AsyncNxusClient`` and ``async for``

A note on ``break`` and lane release:
  When you ``break`` out of an auto-iterating ``for`` / ``async for`` loop, the
  SDK quietly tells the backend you are done with the cursor. The QuickBooks
  Desktop connection lane is released within milliseconds — your *next* call on
  the same connection does not have to wait for the silent-client timeout to
  expire. There is nothing extra to do; just ``break``.

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


def sync_find_and_stop(client: NxusClient, connection_id: str) -> None:
    """Iterate until you find what you need, then ``break``.

    This is the most common real-world pagination pattern: you don't always
    want every record, you just want the first one that matches some predicate.

    The auto-iterator handles the cleanup for you — when the ``for`` loop exits
    via ``break`` (instead of running out of pages naturally), the SDK fires a
    best-effort ``POST /api/v1/cursors/{cursor}/close`` so the QBD lane is
    released right away. Your next API call on this connection won't sit waiting
    for the silent-client timeout to expire.
    """
    print("=== Sync Find-and-Stop ===\n")

    target_substring = "Store"
    found = None

    # The SDK fetches more pages on demand as the loop consumes items. As soon
    # as we `break`, the SDK signals the backend to release the cursor.
    for customer in client.customers.list(connection_id=connection_id, limit=10):
        name = getattr(customer, "name", None) or getattr(customer, "full_name", None) or ""
        if target_substring.lower() in name.lower():
            found = name
            break  # ← SDK auto-closes the cursor here

    if found:
        print(f"  Matched {found!r} — stopped early.")
    else:
        print(f"  No customer matched {target_substring!r}.")
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


async def async_find_and_stop(connection_id: str, **kwargs) -> None:
    """Async equivalent of :func:`sync_find_and_stop`.

    Same shape, same close-on-break behavior — the SDK signals the backend
    that the cursor can be released as soon as ``break`` exits the loop.
    """
    print("=== Async Find-and-Stop ===\n")

    target_substring = "Store"
    found = None

    async with AsyncNxusClient(**kwargs) as client:
        async for customer in await client.customers.list(connection_id=connection_id, limit=10):
            name = getattr(customer, "name", None) or getattr(customer, "full_name", None) or ""
            if target_substring.lower() in name.lower():
                found = name
                break  # ← SDK auto-closes the cursor here

    if found:
        print(f"  Matched {found!r} — stopped early.")
    else:
        print(f"  No customer matched {target_substring!r}.")
    print()


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

            sync_find_and_stop(client, connection_id)

            """ sync_find_and_stop() OUTPUT:
                === Sync Find-and-Stop ===

                  Matched 'Store #55' — stopped early.
            """

        # Run the async examples
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

        asyncio.run(async_find_and_stop(connection_id, **options))

        """ async_find_and_stop() OUTPUT:
            === Async Find-and-Stop ===

              Matched 'Store #55' — stopped early.
        """

    except NxusApiError as exc:
        print(f"\nAPI Error: {exc.user_message} (status={exc.status})")
        sys.exit(1)


if __name__ == "__main__":
    main()
