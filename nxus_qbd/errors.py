"""Typed error handling for the Nxus Python SDK.

Normalizes both ``StandardErrorResponse`` and ``ProblemDetails`` shapes from
the nXus API into a single ``NxusApiError`` exception with typed properties
and convenience boolean helpers.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

import httpx


# ---------------------------------------------------------------------------
# Error code / type enums (mirrors the backend ErrorCode / ErrorType)
# ---------------------------------------------------------------------------

class NxusApiErrorCode(str, Enum):
    """Known error codes returned by the nXus API."""

    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    QBD_CONNECTION_ERROR = "QBD_CONNECTION_ERROR"
    QBD_STALE_EDIT_SEQUENCE = "QBD_STALE_EDIT_SEQUENCE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    QBD_INTEGRATION_ERROR = "QBD_INTEGRATION_ERROR"
    CONFLICT = "CONFLICT"


class NxusApiErrorType(str, Enum):
    """Broad error categories returned by the nXus API."""

    AUTHENTICATION_ERROR_TYPE = "AUTHENTICATION_ERROR_TYPE"
    VALIDATION_ERROR_TYPE = "VALIDATION_ERROR_TYPE"
    NOT_FOUND_ERROR_TYPE = "NOT_FOUND_ERROR_TYPE"
    RATE_LIMIT_ERROR_TYPE = "RATE_LIMIT_ERROR_TYPE"
    INTEGRATION_ERROR_TYPE = "INTEGRATION_ERROR_TYPE"
    API_ERROR_TYPE = "API_ERROR_TYPE"


# ---------------------------------------------------------------------------
# NxusApiError
# ---------------------------------------------------------------------------

class NxusApiError(Exception):
    """Typed error class for all nXus API errors.

    Normalizes both ``StandardErrorResponse`` and ``ProblemDetails`` shapes
    into a single class with typed properties and helper getters.

    Examples
    --------
    ::

        try:
            page = client.customers.list()
        except NxusApiError as exc:
            if exc.is_auth_error:
                # handle auth
                ...
            print(exc.user_message)
    """

    def __init__(
        self,
        message: str,
        *,
        user_message: str,
        status: int = 0,
        code: Optional[str] = None,
        type: Optional[str] = None,
        request_id: Optional[str] = None,
        integration_code: Optional[str] = None,
        validation_errors: Optional[Dict[str, List[str]]] = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.type = type
        self.status = status
        self.user_message = user_message
        self.request_id = request_id
        self.integration_code = integration_code
        self.validation_errors = validation_errors
        self.raw = raw

    # -- boolean helpers -----------------------------------------------------

    @property
    def is_rate_limited(self) -> bool:
        """Whether this is a rate-limit error (429)."""
        return self.status == 429 or self.code == "RATE_LIMIT_EXCEEDED"

    @property
    def is_auth_error(self) -> bool:
        """Whether this is an authentication/authorization error (401 or 403)."""
        return (
            self.status in (401, 403)
            or self.type == "AUTHENTICATION_ERROR_TYPE"
        )

    @property
    def is_validation_error(self) -> bool:
        """Whether this is a validation error.

        The nXus API emits validation errors on both 400 and 422 responses,
        with ``code == "VALIDATION_ERROR"`` and
        ``type == "VALIDATION_ERROR_TYPE"``. Per-field details may or may not
        be present. This predicate returns True if any of those signals are
        set, so callers can reliably catch validation failures regardless of
        the specific HTTP status used.
        """
        return (
            self.status == 422
            or self.code == "VALIDATION_ERROR"
            or self.type == "VALIDATION_ERROR_TYPE"
            or bool(self.validation_errors)
        )

    @property
    def is_not_found(self) -> bool:
        """Whether this is a not-found error (404)."""
        return self.status == 404 or self.type == "NOT_FOUND_ERROR_TYPE"

    @property
    def is_integration_error(self) -> bool:
        """Whether this error originated from QuickBooks Desktop."""
        return self.integration_code is not None

    @property
    def is_conflict(self) -> bool:
        """Whether this is a stale edit sequence conflict (refresh and retry)."""
        return self.status == 409 or self.code == "QBD_STALE_EDIT_SEQUENCE"

    # -- factory class methods -----------------------------------------------

    @classmethod
    def from_response(cls, response: httpx.Response) -> "NxusApiError":
        """Create a ``NxusApiError`` from an ``httpx.Response``.

        Handles:
        - ``StandardErrorResponse``: ``{ "error": { "message": ..., ... } }``
        - ``ProblemDetails``: ``{ "title": ..., "detail": ..., "status": ..., "errors": ... }``
        - Plain string bodies
        - Unknown / unparseable bodies
        """
        status = response.status_code
        raw: Any = None

        # Try to parse JSON body
        try:
            body = response.json()
            raw = body
        except Exception:
            text = response.text.strip()
            if text:
                return cls(
                    text,
                    user_message=text,
                    status=status,
                    raw=text,
                )
            return cls(
                f"HTTP {status}",
                user_message=f"Request failed with status {status}.",
                status=status,
                raw=None,
            )

        return cls.from_error(body, status=status)

    @classmethod
    def from_error(cls, error: Any, *, status: int = 0) -> "NxusApiError":
        """Create a ``NxusApiError`` from any error value.

        Handles dict (StandardErrorResponse / ProblemDetails), str, or unknown
        shapes.
        """
        if isinstance(error, NxusApiError):
            return error

        if not error:
            return cls(
                "An unexpected error occurred.",
                user_message="An unexpected error occurred.",
                status=status,
                raw=error,
            )

        if isinstance(error, str):
            return cls(
                error,
                user_message=error,
                status=status,
                raw=error,
            )

        if isinstance(error, dict):
            # StandardErrorResponse shape: { "error": { "message": ..., ... } }
            err_detail = error.get("error")
            if isinstance(err_detail, dict) and "message" in err_detail:
                return cls(
                    err_detail.get("message", ""),
                    user_message=err_detail.get("userFacingMessage") or err_detail.get("message", ""),
                    status=err_detail.get("httpStatusCode") or status,
                    code=err_detail.get("code"),
                    type=err_detail.get("type"),
                    request_id=err_detail.get("requestId"),
                    integration_code=err_detail.get("integrationCode"),
                    raw=error,
                )

            # ProblemDetails shape: { "title": ..., "detail": ..., "status": ..., "errors": ... }
            if "status" in error and ("title" in error or "detail" in error):
                message = error.get("detail") or error.get("title") or "Validation failed."
                return cls(
                    message,
                    user_message=error.get("detail") or error.get("title") or "Please check your input and try again.",
                    status=error.get("status") or 422,
                    type="VALIDATION_ERROR_TYPE",
                    code="VALIDATION_ERROR",
                    validation_errors=error.get("errors"),
                    raw=error,
                )

            # Fallback: plain dict with .message
            message = (
                error.get("message")
                or error.get("detail")
                or error.get("title")
                or "An unexpected error occurred."
            )
            return cls(
                message,
                user_message=message,
                status=error.get("status") or error.get("statusCode") or status,
                raw=error,
            )

        # Unknown type
        return cls(
            "An unexpected error occurred.",
            user_message="An unexpected error occurred.",
            status=status,
            raw=error,
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def throw_if_error(response: httpx.Response) -> None:
    """Raise ``NxusApiError`` if *response* indicates a non-2xx status.

    Use in call sites where you want a throw-based pattern::

        response = httpx.get(...)
        throw_if_error(response)
        # response is now guaranteed 2xx
    """
    if not response.is_success:
        raise NxusApiError.from_response(response)
