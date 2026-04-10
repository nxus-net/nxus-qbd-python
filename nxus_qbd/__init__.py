"""Nxus QuickBooks Desktop Python SDK."""

from .client import AsyncNxusClient, NxusClient
from .config import (
    DEFAULT_BASE_URL,
    LOCAL_BASE_URL,
    NxusEnvironment,
    resolve_base_url,
)
from .errors import NxusApiError, NxusApiErrorCode, throw_if_error
from .pagination import CursorPage, PaginationError

__version__ = "0.1.0"
__all__ = [
    "NxusClient",
    "AsyncNxusClient",
    "NxusEnvironment",
    "NxusApiError",
    "NxusApiErrorCode",
    "throw_if_error",
    "CursorPage",
    "PaginationError",
    "DEFAULT_BASE_URL",
    "LOCAL_BASE_URL",
    "resolve_base_url",
    "__version__",
]
