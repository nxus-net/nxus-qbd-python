"""Nxus QuickBooks Desktop Python SDK."""

from importlib.metadata import PackageNotFoundError, version as distribution_version

from ._transport import NxusLogger
from .client import AsyncNxusClient, NxusClient
from .config import (
    DEFAULT_BASE_URL,
    LOCAL_BASE_URL,
    NxusEnvironment,
    resolve_base_url,
)
from .errors import NxusApiError, NxusApiErrorCode, throw_if_error
from .pagination import CursorPage, PaginationError

try:
    __version__ = distribution_version("nxus-qbd")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "NxusClient",
    "AsyncNxusClient",
    "NxusEnvironment",
    "NxusLogger",
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
