"""Comprehensive error handling patterns with the Nxus SDK.

Demonstrates:
  - ``throw_if_error(response)`` for raw httpx responses
  - ``NxusApiError.from_response()`` for manual error construction
  - Boolean helpers: is_auth_error, is_not_found, is_validation_error,
    is_rate_limited, is_conflict, is_integration_error
  - Accessing user_message, code, validation_errors
  - Retry with exponential backoff for rate limits

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python error_handling.py
"""

import sys
import time

import httpx

from nxus_qbd import NxusClient, NxusApiError, throw_if_error

from _common import client_options, effective_base_url, effective_verify, require_env


# ---------------------------------------------------------------------------
# 1. Using throw_if_error with raw httpx responses
# ---------------------------------------------------------------------------

def demo_throw_if_error(base_url: str, api_key: str, connection_id: str, verify: bool) -> None:
    """Use ``throw_if_error`` when making raw httpx calls outside the SDK.

    This is handy if you need to call an endpoint that the SDK does not
    wrap, or if you want to inspect the raw response before raising.
    """
    print("=== throw_if_error Pattern ===\n")

    url = f"{base_url.rstrip('/')}/api/v1/vendors"
    response = httpx.get(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Connection-Id": connection_id,
        },
        timeout=30.0,
        verify=verify,
    )

    try:
        # throw_if_error raises NxusApiError for any non-2xx status.
        throw_if_error(response)
        print("  Request succeeded (2xx). No error thrown.\n")
    except NxusApiError as exc:
        print(f"  Caught NxusApiError: {exc.user_message}\n")


# ---------------------------------------------------------------------------
# 2. NxusApiError.from_response — build an error manually
# ---------------------------------------------------------------------------

def demo_from_response(base_url: str, api_key: str, connection_id: str, verify: bool) -> None:
    """Construct a ``NxusApiError`` from an httpx.Response without raising.

    Useful when you want to inspect the error before deciding whether
    to raise or handle it silently.
    """
    print("=== NxusApiError.from_response Pattern ===\n")

    # Deliberately request a resource that does not exist.
    url = f"{base_url.rstrip('/')}/api/v1/vendor/nonexistent-id-12345"
    response = httpx.get(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Connection-Id": connection_id,
        },
        timeout=30.0,
        verify=verify,
    )

    if not response.is_success:
        error = NxusApiError.from_response(response)
        print(f"  Status:       {error.status}")
        print(f"  Code:         {error.code}")
        print(f"  Type:         {error.type}")
        print(f"  User message: {error.user_message}")
        print(f"  Request ID:   {error.request_id}")
        print()
    else:
        print("  (Unexpectedly succeeded — the vendor exists!)\n")


# ---------------------------------------------------------------------------
# 3. Boolean helpers for error categorization
# ---------------------------------------------------------------------------

def demo_boolean_helpers(client: NxusClient, connection_id: str) -> None:
    """Show how to branch on error type using boolean helpers."""
    print("=== Boolean Error Helpers ===\n")

    try:
        # Try to retrieve a vendor that almost certainly does not exist.
        client.vendors.retrieve("nonexistent-id-00000", connection_id=connection_id)
    except NxusApiError as exc:
        if exc.is_not_found:
            print("  is_not_found  = True  -> Resource does not exist.")
        if exc.is_auth_error:
            print("  is_auth_error = True  -> Check your API key or permissions.")
        if exc.is_validation_error:
            print("  is_validation_error = True  -> Fix the request body.")
            if exc.validation_errors:
                for field, messages in exc.validation_errors.items():
                    for msg in messages:
                        print(f"    {field}: {msg}")
        if exc.is_rate_limited:
            print("  is_rate_limited = True  -> Slow down and retry.")
        if exc.is_conflict:
            print("  is_conflict   = True  -> Stale editSequence; re-fetch and retry.")
        if exc.is_integration_error:
            print(f"  is_integration_error = True  -> QBD error code: {exc.integration_code}")

        # user_message is always safe to display to end users.
        print(f"\n  user_message: {exc.user_message}")
        print(f"  code:         {exc.code}")
        print()


# ---------------------------------------------------------------------------
# 4. Retry with exponential backoff for rate limits
# ---------------------------------------------------------------------------

def list_vendors_with_retry(
    client: NxusClient,
    connection_id: str,
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> None:
    """Retry rate-limited requests with exponential backoff.

    When the API returns HTTP 429 the SDK raises ``NxusApiError`` with
    ``is_rate_limited == True``.  This function catches that and retries
    with increasing delays: 1s, 2s, 4s, 8s, 16s ...
    """
    print("=== Rate-Limit Retry Pattern ===\n")

    for attempt in range(1, max_retries + 1):
        try:
            page = client.vendors.list(connection_id=connection_id, limit=5)
            print(f"  Success on attempt {attempt}: got {page.count} vendors.\n")
            return
        except NxusApiError as exc:
            if exc.is_rate_limited and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"  Rate limited (attempt {attempt}/{max_retries}). "
                      f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                # Not a rate-limit error, or we exhausted retries — re-raise.
                raise

    print("  Exhausted all retries.\n")


# ---------------------------------------------------------------------------
# 5. Validation error details
# ---------------------------------------------------------------------------

def demo_validation_error(client: NxusClient, connection_id: str) -> None:
    """Trigger a validation error and inspect per-field messages."""
    print("=== Validation Error Details ===\n")

    try:
        # Send an empty body — the API should reject it with field errors.
        client.vendors.create(connection_id=connection_id)
    except NxusApiError as exc:
        if exc.is_validation_error and exc.validation_errors:
            print("  Validation failed. Field errors:")
            for field, messages in exc.validation_errors.items():
                for msg in messages:
                    print(f"    {field}: {msg}")
        else:
            print(f"  Error (not a validation error): {exc.user_message}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    options = client_options()
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    demo_throw_if_error(
        effective_base_url(),
        str(options["api_key"]),
        connection_id,
        verify=effective_verify(),
    )
    demo_from_response(
        effective_base_url(),
        str(options["api_key"]),
        connection_id,
        verify=effective_verify(),
    )

    with NxusClient(**options) as client:
        demo_boolean_helpers(client, connection_id)
        list_vendors_with_retry(client, connection_id)
        demo_validation_error(client, connection_id)


if __name__ == "__main__":
    main()
