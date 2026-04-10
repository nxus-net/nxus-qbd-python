"""Create a QuickBooks Desktop connection and generate a hosted QWC auth URL.

Demonstrates:
  - Creating a new connection
  - Creating an auth session for that connection
  - Printing the hosted auth flow URL your app can send the user to
  - Checking the current authenticated status for the connection

Usage:
    export NXUS_API_KEY="sk_test_..."
    export NXUS_ENVIRONMENT="development"          # optional, uses localhost
    export NXUS_BASE_URL="https://custom.test/"    # optional explicit override
    python auth_setup.py
"""

from __future__ import annotations

import sys
import time

from nxus_qbd import NxusApiError, NxusClient

from _common import client_options


def main() -> None:
    options = client_options()

    with NxusClient(**options) as client:
        try:
            suffix = int(time.time())

            print("--- Creating QuickBooks Desktop connection ---")
            connection = client.connections.create(
                description=f"SDK Auth Setup Example {suffix}",
                external_id=f"sdk-auth-setup-{suffix}",
            )

            connection_id = connection.id
            print("Connection created:")
            print(f"  ID: {connection_id}")
            if connection.external_id:
                print(f"  External ID: {connection.external_id}")
            if connection.description:
                print(f"  Description: {connection.description}")

            print("\n--- Creating auth session ---")
            auth_session = client.auth_sessions.create(
                connection_id=connection_id,
                link_expiry_mins=60,
                # redirect_url="https://your-app.example.com/integrations/qbd/callback",
            )

            print("Auth session created:")
            print(f"  Session ID: {auth_session.id}")
            print(f"  Status: {auth_session.status or '(unknown)'}")
            print(f"  Expires At: {auth_session.expires_at or '(not provided)'}")
            print(f"  Auth Flow URL: {auth_session.auth_flow_url or '(not provided)'}")

            print("\n--- Checking authenticated status ---")
            status = client.connections.retrieve_status_authenticated(connection_id)

            print("Connection auth status:")
            print(f"  Connection ID: {status.connection_id or connection_id}")
            print(f"  Is Connected: {status.is_connected or False}")
            print(f"  Company Name: {status.company_name or '(not connected yet)'}")
            print(f"  Last Sync At: {status.last_sync_at or '(not available yet)'}")

            print("\nNext step:")
            print("  Send your user to the Auth Flow URL above so they can complete the QWC setup.")
            print("  After they finish, poll retrieve_status_authenticated() or continue your app flow.")

        except NxusApiError as exc:
            print(f"\nAPI Error [{exc.status}]: {exc.user_message}")
            if exc.code:
                print(f"  Code: {exc.code}")
            if exc.request_id:
                print(f"  Request ID: {exc.request_id}")
            sys.exit(1)


if __name__ == "__main__":
    main()
