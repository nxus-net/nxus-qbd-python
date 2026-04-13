# nxus-qbd

Official Python SDK for the [Nxus](https://nx-us.net/docs) QuickBooks Desktop API.

## Installation

```bash
pip install nxus-qbd
```

## Quick Start

```python
from nxus_qbd import NxusClient, NxusEnvironment

client = NxusClient(
    api_key="sk_live_…",
    environment=NxusEnvironment.PRODUCTION,  # default
)

# List vendors (with connection scoping)
vendors = client.vendors.list(connection_id="conn_abc123", limit=50)

# Retrieve a single customer
customer = client.customers.retrieve("cust_123", connection_id="conn_abc123")

# Create an invoice
invoice = client.invoices.create(
    customer_ref_list_id="cust_123",
    connection_id="conn_abc123",
)
```

## Async Support

```python
from nxus_qbd import AsyncNxusClient

async with AsyncNxusClient(api_key="sk_live_…") as client:
    vendors = await client.vendors.list(connection_id="conn_abc123")
```

The SDK defaults to a `100s` client timeout so normal callers can receive the
API's structured timeout responses for heavier QuickBooks operations. Advanced
callers can still override this globally or per request:

```python
client = NxusClient(api_key="sk_live_…", timeout=120)
vendors = client.vendors.list(connection_id="conn_abc123", timeout=30)
```

## Environments

Production is the default and uses `https://api.nx-us.net/`.

```python
from nxus_qbd import NxusClient

# Production (default)
client = NxusClient(api_key="sk_live_…")

# Local development convenience
client = NxusClient(api_key="sk_test_…", environment="development")

# Explicit override still wins
client = NxusClient(api_key="sk_test_…", base_url="https://staging.example.com/")
```

If you point `base_url` at `localhost` explicitly, the SDK also relaxes TLS
verification by default so local dev stays frictionless.

## Connection Scoping

Every request requires a `connection_id` to identify which QuickBooks Desktop company file to target:

```python
# Per-request
client.vendors.list(connection_id="conn_abc123")

# Global default via headers
client = NxusClient(
    api_key="sk_live_…",
    headers={"X-Connection-Id": "conn_abc123"},
)
```

## Pagination

All list methods return a paginated response that supports both manual page navigation and auto-iteration:

```python
# Auto-paginate through all records (sync)
for vendor in client.vendors.list(limit=100):
    print(vendor.name)

# Auto-paginate through all records (async)
async for vendor in await async_client.vendors.list(limit=100):
    print(vendor.name)
```

> [!IMPORTANT]
> **Processing Constraints**: Each paginated request must either complete or be cancelled before the subsequent request for that connection can be processed by the backend.
>
> - **Async API (Primary)**: The Async API is the recommended way to handle these requests as it allows for better lifecycle management.
> - **Sync Wrappers**: While sync wrappers are provided for convenience, you may need to increase your client-side timeouts to ensure large paginated sets complete successfully.

## Examples

Runnable examples live in [`examples/`](examples/) and cover both sync and async usage:

| Example | Description |
|---|---|
| [`basic_crud.py`](examples/basic_crud.py) | Create, retrieve, update, list, and delete a vendor |
| [`auth_setup.py`](examples/auth_setup.py) | Create a connection, generate a hosted QWC auth flow URL, and check auth status |
| [`auto_pagination.py`](examples/auto_pagination.py) | Sync and async auto-iteration across pages |
| [`error_handling.py`](examples/error_handling.py) | Error categorization, retry with backoff, validation errors |
| [`connection_scoped.py`](examples/connection_scoped.py) | Multi-company isolation with `connection_id` |
| [`timeout_tuning.py`](examples/timeout_tuning.py) | Default timeout behavior, client-wide overrides, and per-request timeout tuning |
| [`reports.py`](examples/reports.py) | Aging, general detail, and general summary reports |
| [`async_basic_crud.py`](examples/async_basic_crud.py) | Async CRUD lifecycle |
| [`async_error_handling.py`](examples/async_error_handling.py) | Async error handling and retry patterns |
| [`async_connection_scoped.py`](examples/async_connection_scoped.py) | Async multi-company data isolation |
| [`async_reports.py`](examples/async_reports.py) | Async report retrieval |

All examples auto-load a `.env` file from the project root. Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```ini
NXUS_API_KEY=sk_test_your_key_here
NXUS_ENVIRONMENT=development
NXUS_CONNECTION_ID=your_connection_id_here
```

Optional overrides:

```ini
NXUS_BASE_URL=https://localhost:7242/
NXUS_DEV_MODE=true
```

Then run any example:

```bash
python examples/basic_crud.py
```

## Tests

The test suite includes focused unit coverage plus optional live integration tests:

| File | What it covers |
|---|---|
| [`tests/conftest.py`](tests/conftest.py) | Shared fixtures — loads `.env`, provides `client` and `async_client` fixtures, auto-skips when `NXUS_API_KEY` is not set |
| [`tests/unit/test_config.py`](tests/unit/test_config.py) | Environment/base URL resolution behavior |
| [`tests/unit/test_vendor_pydantic_wiring.py`](tests/unit/test_vendor_pydantic_wiring.py) | Typed response parsing and snake_case request serialization |
| [`tests/integration/test_smoke.py`](tests/integration/test_smoke.py) | Sync tests — list vendors/accounts, pagination with limits, cursor metadata, auto-pagination iteration, 404 error handling |
| [`tests/integration/test_async_smoke.py`](tests/integration/test_async_smoke.py) | Async tests — list vendors, async auto-pagination |

Run the full suite:

```bash
# Install dev dependencies
pip install nxus-qbd[dev]
# — or with uv —
uv sync

# Run tests (skipped automatically if NXUS_API_KEY is not set)
pytest

# Run only unit tests
pytest tests/unit -q

# Run with verbose output
pytest -v

# Run only async tests
pytest tests/integration/test_async_smoke.py -v
```

## Resources

All QuickBooks Desktop resources are available as properties:

| Category | Resources |
|---|---|
| **Transactions** | `invoices`, `bills`, `checks`, `deposits`, `estimates`, `credit_memos`, `purchase_orders`, `sales_receipts`, `journal_entries`, `receive_payments`, `vendor_credits`, `credit_card_charges`, `credit_card_bills`, `credit_card_credits`, `charges`, `build_assemblies`, `ar_refund_credit_cards`, `sales_tax_payment_checks`, `item_receipts`, `check_bills`, `time_trackings`, `transactions` |
| **Lists** | `accounts`, `customers`, `vendors`, `employees`, `other_names`, `currencies`, `terms`, `date_driven_terms`, `payment_methods`, `ship_methods`, `sales_tax_codes`, `price_levels`, `qbd_classes`, `customer_types`, `vendor_types`, `billing_rates`, `inventory_sites`, `bar_codes`, `account_tax_line_infos`, `bill_to_pay`, `unit_of_measure_sets`, `special_items` |
| **Items** | `items`, `inventory_items`, `item_discounts`, `item_fixed_assets`, `item_groups`, `item_inventory_assemblies`, `item_non_inventory`, `item_other_charges`, `item_payments`, `item_sales_tax`, `item_sales_tax_groups`, `service_items`, `item_subtotals` |
| **Payroll** | `payroll_item_non_wages`, `payroll_item_wages`, `workers_comp_codes` |
| **Reports** | `reports.retrieve_general_detail()`, `reports.retrieve_aging()`, etc. |
| **Platform** | `auth_sessions`, `connections` |

## License

MIT
