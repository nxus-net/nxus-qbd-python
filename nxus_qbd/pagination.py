"""Cursor-based auto-pagination for the Nxus Python SDK.

Provides ``CursorPage`` — a page object that supports:

- Accessing page metadata (``has_more``, ``next_cursor``, ``total_count``, ...)
- Fetching the next page via ``get_next_page()`` / ``await get_next_page()``
- Sync iteration: ``for item in page``
- Async iteration: ``async for item in page``
"""

from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
)

T = TypeVar("T")


class PaginationError(Exception):
    """Raised when pagination fails (missing fields, no more pages, etc.)."""

    def __init__(
        self,
        message: str,
        *,
        cause_data: Any = None,
        status: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.cause_data = cause_data
        self.status = status


# Type aliases for the fetcher callables stored on each page so that
# ``get_next_page`` can transparently fetch the next page of results.
SyncFetcher = Callable[..., Any]
AsyncFetcher = Callable[..., Coroutine[Any, Any, Any]]


class CursorPage(Generic[T]):
    """A single page of cursor-paginated results.

    Parameters
    ----------
    data:
        The items in this page.
    has_more:
        Whether additional pages exist beyond this one.
    next_cursor:
        Opaque cursor string to fetch the next page (``None`` when on the
        last page).
    count:
        Number of items in *this* page (typically ``len(data)``).
    limit:
        The ``limit`` query parameter that was used for this request.
    page:
        1-based page number (informational, provided by the API).
    remaining_count:
        How many items remain after this page (if the API provides it).
    total_count:
        Total number of items across all pages (if the API provides it).
    """

    __slots__ = (
        "data",
        "has_more",
        "next_cursor",
        "count",
        "limit",
        "page",
        "remaining_count",
        "total_count",
        "_sync_fetcher",
        "_async_fetcher",
        "_fetch_kwargs",
    )

    def __init__(
        self,
        *,
        data: List[T],
        has_more: bool,
        next_cursor: Optional[str],
        count: Optional[int] = None,
        limit: Optional[int] = None,
        page: Optional[int] = None,
        remaining_count: Optional[int] = None,
        total_count: Optional[int] = None,
    ) -> None:
        self.data = data
        self.has_more = has_more
        self.next_cursor = next_cursor
        self.count = count if count is not None else len(data)
        self.limit = limit
        self.page = page
        self.remaining_count = remaining_count
        self.total_count = total_count

        # Fetchers are attached after construction by the resource list method
        self._sync_fetcher: Optional[SyncFetcher] = None
        self._async_fetcher: Optional[AsyncFetcher] = None
        self._fetch_kwargs: Dict[str, Any] = {}

    # -- navigation ----------------------------------------------------------

    def has_next_page(self) -> bool:
        """Return ``True`` if there is another page to fetch."""
        return self.has_more and self.next_cursor is not None

    def get_next_page(self) -> "CursorPage[T]":
        """Fetch and return the next page (synchronous).

        Raises ``PaginationError`` if there are no more pages or if the page
        was created from an async context and no sync fetcher is available.
        """
        if not self.has_next_page():
            raise PaginationError("No additional pages are available.")
        if self._sync_fetcher is None:
            raise PaginationError(
                "No synchronous fetcher is attached to this page. "
                "Use 'await page.get_next_page_async()' in async contexts."
            )
        return self._sync_fetcher(cursor=self.next_cursor, **self._fetch_kwargs)

    async def get_next_page_async(self) -> "CursorPage[T]":
        """Fetch and return the next page (asynchronous).

        Raises ``PaginationError`` if there are no more pages or if the page
        was created from a sync context and no async fetcher is available.
        """
        if not self.has_next_page():
            raise PaginationError("No additional pages are available.")
        if self._async_fetcher is None:
            raise PaginationError(
                "No asynchronous fetcher is attached to this page. "
                "Use 'page.get_next_page()' in sync contexts."
            )
        return await self._async_fetcher(cursor=self.next_cursor, **self._fetch_kwargs)

    # -- sync iteration ------------------------------------------------------

    def __iter__(self) -> Iterator[T]:
        """Iterate over all items across *all* pages (synchronous).

        Usage::

            for item in client.customers.list():
                print(item)
        """
        page: CursorPage[T] = self
        while True:
            yield from page.data
            if not page.has_next_page():
                return
            page = page.get_next_page()

    # -- async iteration -----------------------------------------------------

    def __aiter__(self) -> AsyncIterator[T]:
        """Iterate over all items across *all* pages (asynchronous).

        Usage::

            async for item in await client.customers.list():
                print(item)
        """
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[T]:
        page: CursorPage[T] = self
        while True:
            for item in page.data:
                yield item
            if not page.has_next_page():
                return
            page = await page.get_next_page_async()

    # -- repr ----------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"CursorPage(count={self.count}, has_more={self.has_more}, "
            f"next_cursor={self.next_cursor!r})"
        )

    def __len__(self) -> int:
        """Return the number of items in *this* page."""
        return len(self.data)


# ---------------------------------------------------------------------------
# Helpers for building CursorPage from raw API response dicts
# ---------------------------------------------------------------------------

def _normalize_page(body: Any) -> Dict[str, Any]:
    """Extract pagination fields from a raw response dict.

    The API returns camelCase keys; we normalize to snake_case for the
    ``CursorPage`` constructor.
    """
    if not isinstance(body, dict):
        raise PaginationError(
            "Expected a paginated response object with data, hasMore, "
            "and nextCursor fields.",
            cause_data=body,
        )

    data = body.get("data")
    if not isinstance(data, list):
        data = []

    return {
        "data": data,
        "has_more": bool(body.get("hasMore", False)),
        "next_cursor": body.get("nextCursor") if isinstance(body.get("nextCursor"), str) else None,
        "count": body.get("count"),
        "limit": body.get("limit"),
        "page": body.get("page"),
        "remaining_count": body.get("remainingCount"),
        "total_count": body.get("totalCount"),
    }


def build_sync_cursor_page(
    body: Any,
    *,
    fetcher: SyncFetcher,
    fetch_kwargs: Dict[str, Any],
) -> CursorPage:
    """Build a ``CursorPage`` from a raw JSON body with a sync fetcher attached."""
    fields = _normalize_page(body)
    page: CursorPage = CursorPage(**fields)
    page._sync_fetcher = fetcher
    page._fetch_kwargs = fetch_kwargs
    return page


def build_async_cursor_page(
    body: Any,
    *,
    fetcher: AsyncFetcher,
    fetch_kwargs: Dict[str, Any],
) -> CursorPage:
    """Build a ``CursorPage`` from a raw JSON body with an async fetcher attached."""
    fields = _normalize_page(body)
    page: CursorPage = CursorPage(**fields)
    page._async_fetcher = fetcher
    page._fetch_kwargs = fetch_kwargs
    return page
