"""Common response shapes and type definitions for the Nxus API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict


class PaginationMeta(TypedDict, total=False):
    """Pagination metadata returned by list endpoints."""

    page: int
    limit: int
    totalCount: int
    totalPages: int
    hasNextPage: bool
    hasPreviousPage: bool


class PaginatedResponse(TypedDict, total=False):
    """Envelope for paginated list responses."""

    data: List[Dict[str, Any]]
    meta: PaginationMeta


class ErrorDetail(TypedDict, total=False):
    """A single validation/error detail."""

    field: str
    message: str


class ErrorResponse(TypedDict, total=False):
    """Standard API error response shape."""

    status: int
    title: str
    detail: str
    errors: List[ErrorDetail]


@dataclass
class RequestOptions:
    """Options that can be passed to any resource method.

    These are separated from ``**kwargs`` query parameters for clarity.
    """

    connection_id: Optional[str] = None
    """If set, sends the ``X-Connection-Id`` header for connection-scoped requests."""

    headers: Optional[Dict[str, str]] = None
    """Extra headers merged into the request."""

    timeout: Optional[float] = None
    """Per-request timeout override in seconds."""

    extra_params: Dict[str, Any] = field(default_factory=dict)
    """Additional query parameters forwarded to the request."""
