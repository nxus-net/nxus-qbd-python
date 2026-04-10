"""Async error handling patterns with the Nxus SDK.

Demonstrates:
  - ``NxusApiError`` catching with async client
  - Boolean helpers: is_auth_error, is_not_found, is_validation_error,
    is_rate_limited, is_conflict, is_integration_error
  - Accessing user_message, code, validation_errors
  - Async retry with exponential backoff for rate limits

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python async_error_handling.py
"""

import asyncio
import sys

from nxus_qbd import AsyncNxusClient, NxusApiError

from _common import client_options, require_env


# ---------------------------------------------------------------------------
# 1. Boolean helpers for error categorization (async)
# ---------------------------------------------------------------------------

async def demo_boolean_helpers(client: AsyncNxusClient, connection_id: str) -> None:
    """Show how to branch on error type using boolean helpers."""
    print("=== Boolean Error Helpers (async) ===\n")

    try:
        await client.vendors.retrieve("nonexistent-id-00000", connection_id=connection_id)
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

        print(f"\n  user_message: {exc.user_message}")
        print(f"  code:         {exc.code}")
        print()


# ---------------------------------------------------------------------------
# 2. Async retry with exponential backoff for rate limits
# ---------------------------------------------------------------------------

async def list_vendors_with_retry(
    client: AsyncNxusClient,
    connection_id: str,
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> None:
    """Retry rate-limited requests with exponential backoff (async).

    Uses ``asyncio.sleep`` instead of ``time.sleep`` so we don't block
    the event loop while waiting.
    """
    print("=== Rate-Limit Retry Pattern (async) ===\n")

    for attempt in range(1, max_retries + 1):
        try:
            page = await client.vendors.list(connection_id=connection_id, limit=5)
            print(f"  Success on attempt {attempt}: got {page.count} vendors.\n")
            return
        except NxusApiError as exc:
            if exc.is_rate_limited and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"  Rate limited (attempt {attempt}/{max_retries}). "
                      f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise

    print("  Exhausted all retries.\n")


# ---------------------------------------------------------------------------
# 3. Async validation error details
# ---------------------------------------------------------------------------

async def demo_validation_error(client: AsyncNxusClient, connection_id: str) -> None:
    """Trigger a validation error and inspect per-field messages (async)."""
    print("=== Validation Error Details (async) ===\n")

    try:
        await client.vendors.create(connection_id=connection_id)
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

async def main() -> None:
    connection_id = require_env(
        "NXUS_CONNECTION_ID",
        "Set it to the GUID (or externalId) of your QBD connection.",
    )

    async with AsyncNxusClient(**client_options()) as client:
        await demo_boolean_helpers(client, connection_id)
        await list_vendors_with_retry(client, connection_id)
        await demo_validation_error(client, connection_id)


if __name__ == "__main__":
    asyncio.run(main())
