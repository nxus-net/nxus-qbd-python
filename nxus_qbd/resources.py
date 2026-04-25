"""Resource namespace classes for the Nxus Python SDK.

Each resource class holds a reference to the shared HTTP transport and exposes
the appropriate CRUD methods for its API endpoints.  URL patterns follow the
Nxus REST convention where the *list* path is plural and the *singular* path
(retrieve / create / update / delete) uses the singular form.

All consumer-facing methods accept **flat keyword arguments** — no ``data={}``,
``params={}``, or ``body={}`` wrappers.  ``connection_id``, ``headers``, and
``timeout`` are extracted before the remaining kwargs are forwarded as the
JSON body (create/update) or query parameters (list/reports). Cursor-paginated
list requests also mirror ``timeout`` into the ``X-Nxus-Timeout-Seconds``
header so backend timeout hints persist across page fetches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel

from nxus_qbd.pagination import (
    CursorPage,
    build_async_cursor_page,
    build_sync_cursor_page,
)

if TYPE_CHECKING:
    from nxus_qbd._transport import SyncTransport, AsyncTransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIMEOUT_HINT_HEADER = "X-Nxus-Timeout-Seconds"

def _extract_options(kwargs: dict) -> tuple[Optional[str], Optional[dict], Optional[float]]:
    """Pop transport options from kwargs, returning connection, headers, timeout."""
    connection_id = kwargs.pop("connection_id", None)
    headers = kwargs.pop("headers", None)
    timeout = kwargs.pop("timeout", None)
    server_timeout_seconds = kwargs.pop("server_timeout_seconds", None)
    if server_timeout_seconds is not None:
        headers = dict(headers or {})
        headers.setdefault(TIMEOUT_HINT_HEADER, _format_timeout_hint(server_timeout_seconds))
    return connection_id, headers, timeout


def _format_timeout_hint(timeout: float) -> str:
    """Render a timeout value as a stable header string."""
    timeout_value = float(timeout)
    if timeout_value.is_integer():
        return str(int(timeout_value))
    return str(timeout)


def _list_headers_with_timeout_hint(
    headers: Optional[Dict[str, str]],
    timeout: Optional[float],
) -> Optional[Dict[str, str]]:
    """Attach the backend timeout hint header for paginated list requests."""
    if timeout is None:
        return headers
    merged_headers = dict(headers or {})
    merged_headers.setdefault(TIMEOUT_HINT_HEADER, _format_timeout_hint(timeout))
    return merged_headers


def _serialize_body(kwargs: dict) -> Optional[dict]:
    """Turn a flat-kwarg body into a JSON-ready dict.

    If the caller passed a single Pydantic BaseModel instance as the only
    positional-style kwarg (e.g. ``vendor=Vendor(...)``) or via a ``model=``
    key, it is dumped with ``by_alias=True`` so wire field names come out in
    camelCase. Otherwise kwargs are returned as-is (old flat-kwarg behavior).

    Individual BaseModel values nested inside kwargs (e.g. ``billing_address=
    Address(...)``) are also dumped to dicts.
    """
    if not kwargs:
        return None
    # Single model instance shortcut
    if len(kwargs) == 1:
        (only_val,) = kwargs.values()
        if isinstance(only_val, BaseModel):
            return only_val.model_dump(mode="json", by_alias=True, exclude_none=True)

    def to_wire_key(key: str) -> str:
        if "_" not in key:
            return key
        parts = key.rstrip("_").split("_")
        head, *tail = parts
        return head + "".join(part[:1].upper() + part[1:] for part in tail)

    def to_wire_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(value, dict):
            return {to_wire_key(str(k)): to_wire_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [to_wire_value(v) for v in value]
        return value

    return {to_wire_key(k): to_wire_value(v) for k, v in kwargs.items()}


def _serialize_params(kwargs: dict) -> Optional[dict]:
    """Turn flat query kwargs into API wire-format params.

    Supports Pythonic snake_case while remaining backward-compatible with
    callers that already pass camelCase query keys.
    """
    if not kwargs:
        return None

    def to_wire_key(key: str) -> str:
        if "_" not in key:
            return key
        parts = key.rstrip("_").split("_")
        head, *tail = parts
        return head + "".join(part[:1].upper() + part[1:] for part in tail)

    def to_wire_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(value, list):
            return [to_wire_value(v) for v in value]
        return value

    return {to_wire_key(k): to_wire_value(v) for k, v in kwargs.items()}


def _parse_one(body: Any, model: Optional[type]) -> Any:
    """Parse a single-resource response through a Pydantic model if set."""
    if model is None or body is None:
        return body
    # Unwrap `{data: {...}}` envelopes if present
    if isinstance(body, dict) and "data" in body and isinstance(body["data"], dict):
        return model.model_validate(body["data"])
    if isinstance(body, dict):
        return model.model_validate(body)
    return body


def _parse_list_items(body: Any, model: Optional[type]) -> Any:
    """Parse the `data: [...]` array in a list response through a model."""
    if model is None or not isinstance(body, dict):
        return body
    items = body.get("data")
    if not isinstance(items, list):
        return body
    body["data"] = [model.model_validate(it) if isinstance(it, dict) else it for it in items]
    return body


def _build_request_kwargs(
    connection_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the kwargs dict to pass to transport.request()."""
    kw: Dict[str, Any] = {}
    if params:
        kw["params"] = params
    if json:
        kw["json"] = json
    merged_headers: Dict[str, str] = {}
    if connection_id:
        merged_headers["X-Connection-Id"] = connection_id
    if headers:
        merged_headers.update(headers)
    if merged_headers:
        kw["headers"] = merged_headers
    if timeout is not None:
        kw["timeout"] = timeout
    return kw


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class _SyncResourceBase:
    """Base for synchronous resource namespaces."""

    _list_path: str
    _singular_path: str  # contains ``{id}`` placeholder
    _create_path: str     # singular form for POST create
    _model: Optional[type] = None  # Pydantic model class for response parsing

    def __init__(self, transport: "SyncTransport") -> None:
        self._t = transport


class _AsyncResourceBase:
    """Base for asynchronous resource namespaces."""

    _list_path: str
    _singular_path: str
    _create_path: str
    _model: Optional[type] = None

    def __init__(self, transport: "AsyncTransport") -> None:
        self._t = transport


# ---------------------------------------------------------------------------
# Mixin capabilities — composed into concrete resource classes
# ---------------------------------------------------------------------------

class _SyncList:
    def list(self, **kwargs: Any) -> CursorPage:
        """List resources with cursor-based pagination.

        Args:
            limit: Maximum number of items to return per page.
            cursor: Pagination cursor from a previous response.
            connection_id: QBD connection GUID or external ID.
            **kwargs: Additional query parameters (filters, sorting, etc.).

        Returns:
            A ``CursorPage`` containing the results and pagination metadata.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        cursor = kwargs.pop("cursor", None)
        limit = kwargs.pop("limit", None)
        # Remaining kwargs become query params
        params = _serialize_params(kwargs) or {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        kw = _build_request_kwargs(
            connection_id,
            _list_headers_with_timeout_hint(headers, timeout),
            timeout,
            params=params or None,
        )
        body = self._t.request("GET", self._list_path, **kw)  # type: ignore[attr-defined]
        body = _parse_list_items(body, getattr(self, "_model", None))

        # Build fetch_kwargs so get_next_page can re-invoke with the same options.
        fetch_kwargs: Dict[str, Any] = {}
        if connection_id:
            fetch_kwargs["connection_id"] = connection_id
        if headers:
            fetch_kwargs["headers"] = headers
        if timeout is not None:
            fetch_kwargs["timeout"] = timeout
        if limit is not None:
            fetch_kwargs["limit"] = limit
        # Forward any extra filter kwargs
        fetch_kwargs.update(kwargs)

        return build_sync_cursor_page(
            body,
            fetcher=self.list,  # type: ignore[attr-defined]
            fetch_kwargs=fetch_kwargs,
        )


class _SyncRetrieve:
    def retrieve(self, id: str, **kwargs: Any) -> Any:
        """Retrieve a single resource by ID.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.

        Returns:
            The resource object as a dictionary.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        params = kwargs or None
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        body = self._t.request("GET", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]
        return _parse_one(body, getattr(self, "_model", None))


class _SyncCreate:
    def create(self, **kwargs: Any) -> Any:
        """Create a new resource.

        All fields are passed as flat keyword arguments — no ``data={}`` wrapper.

        Args:
            connection_id: QBD connection GUID or external ID.
            **kwargs: Resource fields (e.g. ``name``, ``company_name``, ``billing_address``).

        Returns:
            The newly created resource object.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = self._t.request("POST", self._create_path, **kw)  # type: ignore[attr-defined]
        return _parse_one(resp, getattr(self, "_model", None))


class _SyncUpdate:
    def update(self, id: str, **kwargs: Any) -> Any:
        """Update an existing resource.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.
            revision_number: Required for optimistic concurrency control.
            **kwargs: Fields to update.

        Returns:
            The updated resource object.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = self._t.request("POST", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]
        return _parse_one(resp, getattr(self, "_model", None))


class _SyncDelete:
    def delete(self, id: str, **kwargs: Any) -> Any:
        """Delete a resource by ID.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.

        Returns:
            Confirmation of deletion.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        params = kwargs or None
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        return self._t.request("DELETE", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]


# Async equivalents

class _AsyncList:
    async def list(self, **kwargs: Any) -> CursorPage:
        """List resources with cursor-based pagination.

        Args:
            limit: Maximum number of items to return per page.
            cursor: Pagination cursor from a previous response.
            connection_id: QBD connection GUID or external ID.
            **kwargs: Additional query parameters (filters, sorting, etc.).

        Returns:
            A ``CursorPage`` containing the results and pagination metadata.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        cursor = kwargs.pop("cursor", None)
        limit = kwargs.pop("limit", None)
        params = _serialize_params(kwargs) or {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        kw = _build_request_kwargs(
            connection_id,
            _list_headers_with_timeout_hint(headers, timeout),
            timeout,
            params=params or None,
        )
        body = await self._t.request("GET", self._list_path, **kw)  # type: ignore[attr-defined]
        body = _parse_list_items(body, getattr(self, "_model", None))

        fetch_kwargs: Dict[str, Any] = {}
        if connection_id:
            fetch_kwargs["connection_id"] = connection_id
        if headers:
            fetch_kwargs["headers"] = headers
        if timeout is not None:
            fetch_kwargs["timeout"] = timeout
        if limit is not None:
            fetch_kwargs["limit"] = limit
        fetch_kwargs.update(kwargs)

        return build_async_cursor_page(
            body,
            fetcher=self.list,  # type: ignore[attr-defined]
            fetch_kwargs=fetch_kwargs,
        )


class _AsyncRetrieve:
    async def retrieve(self, id: str, **kwargs: Any) -> Any:
        """Retrieve a single resource by ID.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.

        Returns:
            The resource object as a dictionary.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        params = kwargs or None
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        body = await self._t.request("GET", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]
        return _parse_one(body, getattr(self, "_model", None))


class _AsyncCreate:
    async def create(self, **kwargs: Any) -> Any:
        """Create a new resource.

        All fields are passed as flat keyword arguments — no ``data={}`` wrapper.

        Args:
            connection_id: QBD connection GUID or external ID.
            **kwargs: Resource fields (e.g. ``name``, ``company_name``, ``billing_address``).

        Returns:
            The newly created resource object.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = await self._t.request("POST", self._create_path, **kw)  # type: ignore[attr-defined]
        return _parse_one(resp, getattr(self, "_model", None))


class _AsyncUpdate:
    async def update(self, id: str, **kwargs: Any) -> Any:
        """Update an existing resource.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.
            revision_number: Required for optimistic concurrency control.
            **kwargs: Fields to update.

        Returns:
            The updated resource object.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = await self._t.request("POST", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]
        return _parse_one(resp, getattr(self, "_model", None))


class _AsyncDelete:
    async def delete(self, id: str, **kwargs: Any) -> Any:
        """Delete a resource by ID.

        Args:
            id: The QuickBooks-assigned ListID or TxnID.
            connection_id: QBD connection GUID or external ID.

        Returns:
            Confirmation of deletion.
        """
        connection_id, headers, timeout = _extract_options(kwargs)
        params = kwargs or None
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        return await self._t.request("DELETE", self._singular_path.format(id=id), **kw)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Concrete sync resource classes
# ---------------------------------------------------------------------------

def _sync_resource(
    name: str,
    list_path: str,
    singular_path: str,
    create_path: str,
    methods: tuple,
    model: Optional[type] = None,
) -> type:
    """Factory that builds a synchronous resource class with the requested methods."""
    bases = [_SyncResourceBase]
    if "list" in methods:
        bases.append(_SyncList)
    if "retrieve" in methods:
        bases.append(_SyncRetrieve)
    if "create" in methods:
        bases.append(_SyncCreate)
    if "update" in methods:
        bases.append(_SyncUpdate)
    if "delete" in methods:
        bases.append(_SyncDelete)

    attrs = {
        "_list_path": list_path,
        "_singular_path": singular_path,
        "_create_path": create_path,
        "_model": model,
    }
    return type(name, tuple(bases), attrs)


def _async_resource(
    name: str,
    list_path: str,
    singular_path: str,
    create_path: str,
    methods: tuple,
    model: Optional[type] = None,
) -> type:
    """Factory that builds an asynchronous resource class with the requested methods."""
    bases = [_AsyncResourceBase]
    if "list" in methods:
        bases.append(_AsyncList)
    if "retrieve" in methods:
        bases.append(_AsyncRetrieve)
    if "create" in methods:
        bases.append(_AsyncCreate)
    if "update" in methods:
        bases.append(_AsyncUpdate)
    if "delete" in methods:
        bases.append(_AsyncDelete)

    attrs = {
        "_list_path": list_path,
        "_singular_path": singular_path,
        "_create_path": create_path,
        "_model": model,
    }
    return type(name, tuple(bases), attrs)


# ---------------------------------------------------------------------------
# Resource registry — (namespace, list_path, singular_path, create_path, methods)
# ---------------------------------------------------------------------------
# BEGIN AUTO-GENERATED RESOURCE DEFS
_RESOURCE_DEFS: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    ("ar_refund_credit_cards", "/api/v1/ar-refund-credit-cards", "/api/v1/ar-refund-credit-card/{id}", "/api/v1/ar-refund-credit-card", ("list", "retrieve", "create", "update", "delete")),
    ("bills", "/api/v1/bills", "/api/v1/bill/{id}", "/api/v1/bill", ("list", "retrieve", "create", "update", "delete")),
    ("check_bills", "/api/v1/check-bills", "/api/v1/check-bill/{id}", "/api/v1/check-bill", ("list", "retrieve", "create", "update", "delete")),
    ("checks", "/api/v1/checks", "/api/v1/check/{id}", "/api/v1/check", ("list", "retrieve", "create", "update", "delete")),
    ("credit_card_bills", "/api/v1/credit-card-bills", "/api/v1/credit-card-bill/{id}", "/api/v1/credit-card-bill", ("list", "retrieve", "create", "update", "delete")),
    ("credit_card_credits", "/api/v1/credit-card-credits", "/api/v1/credit-card-credit/{id}", "/api/v1/credit-card-credit", ("list", "retrieve", "create", "update", "delete")),
    ("deposits", "/api/v1/deposits", "/api/v1/deposit/{id}", "/api/v1/deposit", ("list", "retrieve", "create", "update", "delete")),
    ("estimates", "/api/v1/estimates", "/api/v1/estimate/{id}", "/api/v1/estimate", ("list", "retrieve", "create", "update", "delete")),
    ("item_receipts", "/api/v1/item-receipts", "/api/v1/item-receipt/{id}", "/api/v1/item-receipt", ("list", "retrieve", "create", "update", "delete")),
    ("journal_entries", "/api/v1/journal-entries", "/api/v1/journal-entry/{id}", "/api/v1/journal-entry", ("list", "retrieve", "create", "update", "delete")),
    ("purchase_orders", "/api/v1/purchase-orders", "/api/v1/purchase-order/{id}", "/api/v1/purchase-order", ("list", "retrieve", "create", "update", "delete")),
    ("sales_receipts", "/api/v1/sales-receipts", "/api/v1/sales-receipt/{id}", "/api/v1/sales-receipt", ("list", "retrieve", "create", "update", "delete")),
    ("sales_tax_payment_checks", "/api/v1/sales-tax-payment-checks", "/api/v1/sales-tax-payment-check/{id}", "/api/v1/sales-tax-payment-check", ("list", "retrieve", "create", "update", "delete")),
    ("time_trackings", "/api/v1/time-tracking-activities", "/api/v1/time-tracking-activity/{id}", "/api/v1/time-tracking-activity", ("list", "retrieve", "create", "update", "delete")),
    ("transactions", "/api/v1/transactions", "/api/v1/transaction/{id}", "/api/v1/transaction", ("list", "retrieve", "delete")),
    ("vendor_credits", "/api/v1/vendor-credits", "/api/v1/vendor-credit/{id}", "/api/v1/vendor-credit", ("list", "retrieve", "create", "update", "delete")),
    ("build_assemblies", "/api/v1/build-assemblies", "/api/v1/build-assembly/{id}", "/api/v1/build-assembly", ("list", "retrieve", "create", "update", "delete")),
    ("charges", "/api/v1/charges", "/api/v1/charge/{id}", "/api/v1/charge", ("list", "retrieve", "create", "update", "delete")),
    ("credit_card_charges", "/api/v1/credit-card-charges", "/api/v1/credit-card-charge/{id}", "/api/v1/credit-card-charge", ("list", "retrieve", "create", "update", "delete")),
    ("credit_memos", "/api/v1/credit-memos", "/api/v1/credit-memo/{id}", "/api/v1/credit-memo", ("list", "retrieve", "create", "update", "delete")),
    ("inventory_adjustments", "/api/v1/inventory-adjustments", "/api/v1/inventory-adjustment/{id}", "/api/v1/inventory-adjustment", ("list", "retrieve", "create", "update", "delete")),
    ("invoices", "/api/v1/invoices", "/api/v1/invoice/{id}", "/api/v1/invoice", ("list", "retrieve", "create", "update", "delete")),
    ("receive_payments", "/api/v1/receive-payments", "/api/v1/receive-payment/{id}", "/api/v1/receive-payment", ("list", "retrieve", "create", "update", "delete")),
    ("accounts", "/api/v1/accounts", "/api/v1/account/{id}", "/api/v1/account", ("list", "retrieve", "create", "update", "delete")),
    ("account_tax_line_infos", "/api/v1/accounts-tax-line-info", "/api/v1/account-tax-line-info/{id}", "/api/v1/account-tax-line-info", ("list", "retrieve")),
    ("bar_codes", "/api/v1/bar-codes", "/api/v1/bar-code/{id}", "/api/v1/bar-code", ("list", "delete")),
    ("billing_rates", "/api/v1/billing-rates", "/api/v1/billing-rate/{id}", "/api/v1/billing-rate", ("list", "retrieve", "create", "delete")),
    ("qbd_classes", "/api/v1/classes", "/api/v1/class/{id}", "/api/v1/class", ("list", "retrieve", "create", "update", "delete")),
    ("currencies", "/api/v1/currencies", "/api/v1/currency/{id}", "/api/v1/currency", ("list", "retrieve", "create", "update")),
    ("customers", "/api/v1/customers", "/api/v1/customer/{id}", "/api/v1/customer", ("list", "retrieve", "create", "update", "delete")),
    ("customer_types", "/api/v1/customer-types", "/api/v1/customer-type/{id}", "/api/v1/customer-type", ("list", "retrieve", "create", "update", "delete")),
    ("date_driven_terms", "/api/v1/date-driven-terms", "/api/v1/date-driven-term/{id}", "/api/v1/date-driven-term", ("list", "retrieve", "create", "update", "delete")),
    ("employees", "/api/v1/employees", "/api/v1/employee/{id}", "/api/v1/employee", ("list", "retrieve", "create", "update", "delete")),
    ("inventory_sites", "/api/v1/inventory-sites", "/api/v1/inventory-site/{id}", "/api/v1/inventory-site", ("list", "retrieve", "create", "update", "delete")),
    ("other_names", "/api/v1/other-names", "/api/v1/other-name/{id}", "/api/v1/other-name", ("list", "retrieve", "create", "update", "delete")),
    ("payment_methods", "/api/v1/payment-methods", "/api/v1/payment-method/{id}", "/api/v1/payment-method", ("list", "retrieve", "create", "update", "delete")),
    ("price_levels", "/api/v1/price-levels", "/api/v1/price-level/{id}", "/api/v1/price-level", ("list", "retrieve", "create", "update", "delete")),
    ("sales_tax_codes", "/api/v1/sales-tax-codes", "/api/v1/sales-tax-code/{id}", "/api/v1/sales-tax-code", ("list", "retrieve", "create", "update", "delete")),
    ("ship_methods", "/api/v1/ship-methods", "/api/v1/ship-method/{id}", "/api/v1/ship-method", ("list", "retrieve", "create", "update", "delete")),
    ("terms", "/api/v1/terms", "/api/v1/term/{id}", "/api/v1/term", ("list", "retrieve", "create", "update", "delete")),
    ("unit_of_measure_sets", "/api/v1/unit-of-measure-sets", "/api/v1/unit-of-measure-set/{id}", "/api/v1/unit-of-measure-set", ("list", "retrieve", "create")),
    ("vendors", "/api/v1/vendors", "/api/v1/vendor/{id}", "/api/v1/vendor", ("list", "retrieve", "create", "update", "delete")),
    ("vendor_types", "/api/v1/vendor-types", "/api/v1/vendor-type/{id}", "/api/v1/vendor-type", ("list", "retrieve", "create", "delete")),
    ("bill_to_pay", "/api/v1/bills-to-pay", "/api/v1/bill-to-pay/{id}", "/api/v1/bill-to-pay", ("list", "retrieve")),
    ("items", "/api/v1/items", "/api/v1/item/{id}", "/api/v1/item", ("list", "retrieve")),
    ("inventory_items", "/api/v1/inventory-items", "/api/v1/inventory-item/{id}", "/api/v1/inventory-item", ("list", "retrieve", "create", "update", "delete")),
    ("item_discounts", "/api/v1/items-discount", "/api/v1/item-discount/{id}", "/api/v1/item-discount", ("list", "retrieve", "create", "update", "delete")),
    ("item_fixed_assets", "/api/v1/items-fixed-asset", "/api/v1/item-fixed-asset/{id}", "/api/v1/item-fixed-asset", ("list", "retrieve", "create", "update", "delete")),
    ("item_groups", "/api/v1/items-group", "/api/v1/item-group/{id}", "/api/v1/item-group", ("list", "retrieve", "create", "update", "delete")),
    ("item_inventory_assemblies", "/api/v1/items-inventory-assembly", "/api/v1/item-inventory-assembly/{id}", "/api/v1/item-inventory-assembly", ("list", "retrieve", "create", "update", "delete")),
    ("item_non_inventory", "/api/v1/items-non-inventory", "/api/v1/item-non-inventory/{id}", "/api/v1/item-non-inventory", ("list", "retrieve", "create", "update", "delete")),
    ("item_other_charges", "/api/v1/items-other-charge", "/api/v1/item-other-charge/{id}", "/api/v1/item-other-charge", ("list", "retrieve", "create", "update", "delete")),
    ("item_payments", "/api/v1/items-payment", "/api/v1/item-payment/{id}", "/api/v1/item-payment", ("list", "retrieve", "create", "update", "delete")),
    ("item_sales_tax", "/api/v1/items-sales-tax", "/api/v1/item-sales-tax/{id}", "/api/v1/item-sales-tax", ("list", "retrieve", "create", "update", "delete")),
    ("item_sales_tax_groups", "/api/v1/items-sales-tax-group", "/api/v1/item-sales-tax-group/{id}", "/api/v1/item-sales-tax-group", ("list", "retrieve", "create", "update", "delete")),
    ("service_items", "/api/v1/items-service", "/api/v1/item-service/{id}", "/api/v1/item-service", ("list", "retrieve", "create", "update", "delete")),
    ("item_subtotals", "/api/v1/items-subtotal", "/api/v1/item-subtotal/{id}", "/api/v1/item-subtotal", ("list", "retrieve", "create", "update", "delete")),
    ("payroll_item_non_wages", "/api/v1/payroll-item-non-wages", "/api/v1/payroll-item-non-wage/{id}", "/api/v1/payroll-item-non-wage", ("list", "retrieve", "delete")),
    ("payroll_item_wages", "/api/v1/payroll-item-wages", "/api/v1/payroll-item-wage/{id}", "/api/v1/payroll-item-wage", ("list", "retrieve", "create", "delete")),
    ("workers_comp_codes", "/api/v1/workers-comp-codes", "/api/v1/workers-comp-code/{id}", "/api/v1/workers-comp-code", ("list", "retrieve", "create", "update", "delete")),
]
# END AUTO-GENERATED RESOURCE DEFS

# ---------------------------------------------------------------------------
# Namespace → Pydantic model class registry
#
# Responses from list/retrieve/create/update are parsed through the bound
# model so callers get typed objects (e.g. vendor.company_name) instead of
# raw dicts.  Resources without an entry here continue to return dicts —
# they'll be wired up as we roll Pydantic out to every resource.
# ---------------------------------------------------------------------------

def _load_models() -> Dict[str, type]:
    """Map every resource namespace → primary Pydantic entity model class.

    Lazy-imported so a broken model file can't break the client on import.
    Resources whose model isn't yet wired return raw dicts (the old behavior).
    """
    # Transactions
    from nxus_qbd.models.qbd.ar_refund_credit_card import ArRefundCreditCard
    from nxus_qbd.models.qbd.bill import Bill
    from nxus_qbd.models.qbd.check_bill import CheckBill
    from nxus_qbd.models.qbd.check import Check
    from nxus_qbd.models.qbd.credit_card_bill import CreditCardBill
    from nxus_qbd.models.qbd.credit_card_credit import CreditCardCredit
    from nxus_qbd.models.qbd.deposit import Deposit
    from nxus_qbd.models.qbd.estimate import Estimate
    from nxus_qbd.models.qbd.item_receipt import ItemReceipt
    from nxus_qbd.models.qbd.journal_entry import JournalEntry
    from nxus_qbd.models.qbd.purchase_order import PurchaseOrder
    from nxus_qbd.models.qbd.sales_receipt import SalesReceipt
    from nxus_qbd.models.qbd.sales_tax_payment_check import SalesTaxPaymentCheck
    from nxus_qbd.models.qbd.time_tracking_activity import TimeTracking
    from nxus_qbd.models.qbd.transaction import Transaction
    from nxus_qbd.models.qbd.vendor_credit import VendorCredit
    from nxus_qbd.models.qbd.build_assembly import BuildAssembly
    from nxus_qbd.models.qbd.charge import Charge
    from nxus_qbd.models.qbd.credit_card_charge import CreditCardCharge
    from nxus_qbd.models.qbd.credit_memo import CreditMemo
    from nxus_qbd.models.qbd.inventory_adjustment import InventoryAdjustment
    from nxus_qbd.models.qbd.invoice import Invoice
    from nxus_qbd.models.qbd.receive_payment import ReceivePayment

    # Lists
    from nxus_qbd.models.qbd.account import Account
    from nxus_qbd.models.qbd.account_tax_line_info import AccountTaxLineInfo
    from nxus_qbd.models.qbd.bar_code import BarCode
    from nxus_qbd.models.qbd.billing_rate import BillingRate
    from nxus_qbd.models.qbd.class_ import Class as QbdClass
    from nxus_qbd.models.qbd.currency import Currency
    from nxus_qbd.models.qbd.customer import Customer
    from nxus_qbd.models.qbd.customer_type import CustomerType
    from nxus_qbd.models.qbd.date_driven_term import DateDrivenTerm
    from nxus_qbd.models.qbd.employee import Employee
    from nxus_qbd.models.qbd.inventory_site import InventorySite
    from nxus_qbd.models.qbd.other_name import OtherName
    from nxus_qbd.models.qbd.payment_method import PaymentMethod
    from nxus_qbd.models.qbd.price_level import PriceLevel
    from nxus_qbd.models.qbd.sales_tax_code import SalesTaxCode
    from nxus_qbd.models.qbd.ship_method import ShipMethod
    from nxus_qbd.models.qbd.term import Term
    from nxus_qbd.models.qbd.unit_of_measure_set import UnitOfMeasureSet
    from nxus_qbd.models.qbd.vendor import Vendor
    from nxus_qbd.models.qbd.vendor_type import VendorType
    from nxus_qbd.models.qbd.bill_to_pay import BillToPayRet

    # Items
    from nxus_qbd.models.qbd.item import Item
    from nxus_qbd.models.qbd.item_inventory import InventoryItem
    from nxus_qbd.models.qbd.item_discount import ItemDiscount
    from nxus_qbd.models.qbd.item_fixed_asset import ItemFixedAsset
    from nxus_qbd.models.qbd.item_group import ItemGroup
    from nxus_qbd.models.qbd.item_inventory_assembly import ItemInventoryAssembly
    from nxus_qbd.models.qbd.item_non_inventory import ItemNonInventory
    from nxus_qbd.models.qbd.item_other_charge import ItemOtherCharge
    from nxus_qbd.models.qbd.item_payment import ItemPayment
    from nxus_qbd.models.qbd.item_sales_tax import ItemSalesTax
    from nxus_qbd.models.qbd.item_sales_tax_group import ItemSalesTaxGroup
    from nxus_qbd.models.qbd.item_service import ServiceItem
    from nxus_qbd.models.qbd.item_subtotal import ItemSubtotal

    # Payroll
    from nxus_qbd.models.qbd.payroll_item_non_wage import PayrollItemNonWage
    from nxus_qbd.models.qbd.payroll_item_wage import PayrollItemWage
    from nxus_qbd.models.qbd.workers_comp_code import WorkersCompCode

    return {
        # Transactions
        "ar_refund_credit_cards": ArRefundCreditCard,
        "bills": Bill,
        "check_bills": CheckBill,
        "checks": Check,
        "credit_card_bills": CreditCardBill,
        "credit_card_credits": CreditCardCredit,
        "deposits": Deposit,
        "estimates": Estimate,
        "item_receipts": ItemReceipt,
        "journal_entries": JournalEntry,
        "purchase_orders": PurchaseOrder,
        "sales_receipts": SalesReceipt,
        "sales_tax_payment_checks": SalesTaxPaymentCheck,
        "time_trackings": TimeTracking,
        "transactions": Transaction,
        "vendor_credits": VendorCredit,
        "build_assemblies": BuildAssembly,
        "charges": Charge,
        "credit_card_charges": CreditCardCharge,
        "credit_memos": CreditMemo,
        "inventory_adjustments": InventoryAdjustment,
        "invoices": Invoice,
        "receive_payments": ReceivePayment,
        # Lists
        "accounts": Account,
        "account_tax_line_infos": AccountTaxLineInfo,
        "bar_codes": BarCode,
        "billing_rates": BillingRate,
        "qbd_classes": QbdClass,
        "currencies": Currency,
        "customers": Customer,
        "customer_types": CustomerType,
        "date_driven_terms": DateDrivenTerm,
        "employees": Employee,
        "inventory_sites": InventorySite,
        "other_names": OtherName,
        "payment_methods": PaymentMethod,
        "price_levels": PriceLevel,
        "sales_tax_codes": SalesTaxCode,
        "ship_methods": ShipMethod,
        "terms": Term,
        "unit_of_measure_sets": UnitOfMeasureSet,
        "vendors": Vendor,
        "vendor_types": VendorType,
        "bill_to_pay": BillToPayRet,
        # Items
        "items": Item,
        "inventory_items": InventoryItem,
        "item_discounts": ItemDiscount,
        "item_fixed_assets": ItemFixedAsset,
        "item_groups": ItemGroup,
        "item_inventory_assemblies": ItemInventoryAssembly,
        "item_non_inventory": ItemNonInventory,
        "item_other_charges": ItemOtherCharge,
        "item_payments": ItemPayment,
        "item_sales_tax": ItemSalesTax,
        "item_sales_tax_groups": ItemSalesTaxGroup,
        "service_items": ServiceItem,
        "item_subtotals": ItemSubtotal,
        # Payroll
        "payroll_item_non_wages": PayrollItemNonWage,
        "payroll_item_wages": PayrollItemWage,
        "workers_comp_codes": WorkersCompCode,
    }


_MODELS: Dict[str, type] = _load_models()


# Build concrete classes and register them in module-level dicts for the
# client to look up at init time.

SYNC_RESOURCES: Dict[str, type] = {}
ASYNC_RESOURCES: Dict[str, type] = {}

for _ns, _lp, _sp, _cp, _methods in _RESOURCE_DEFS:
    _class_name = "".join(part.capitalize() for part in _ns.split("_"))
    _model = _MODELS.get(_ns)
    SYNC_RESOURCES[_ns] = _sync_resource(f"Sync{_class_name}", _lp, _sp, _cp, _methods, _model)
    ASYNC_RESOURCES[_ns] = _async_resource(f"Async{_class_name}", _lp, _sp, _cp, _methods, _model)


# ---------------------------------------------------------------------------
# Special items — create-only, unique URL pattern
# ---------------------------------------------------------------------------

class SyncSpecialItems(_SyncResourceBase):
    _list_path = "/api/v1/special-item"
    _singular_path = ""
    _create_path = "/api/v1/special-item"

    def create(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        return self._t.request("POST", self._create_path, **kw)


class AsyncSpecialItems(_AsyncResourceBase):
    _list_path = "/api/v1/special-item"
    _singular_path = ""
    _create_path = "/api/v1/special-item"

    async def create(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        return await self._t.request("POST", self._create_path, **kw)


SYNC_RESOURCES["special_items"] = SyncSpecialItems
ASYNC_RESOURCES["special_items"] = AsyncSpecialItems


# ---------------------------------------------------------------------------
# Reports — each report is a GET with query params, no resource ID
# ---------------------------------------------------------------------------

_REPORT_ENDPOINTS = {
    "retrieve_general_detail": "/api/v1/reports/general-detail",
    "retrieve_aging": "/api/v1/reports/aging",
    "retrieve_general_summary": "/api/v1/reports/general-summary",
    "retrieve_budget_summary": "/api/v1/reports/budget-summary",
    "retrieve_job": "/api/v1/reports/job",
    "retrieve_time": "/api/v1/reports/time",
    "retrieve_custom_detail": "/api/v1/reports/custom-detail",
    "retrieve_custom_summary": "/api/v1/reports/custom-summary",
    "retrieve_payroll_detail": "/api/v1/reports/payroll-detail",
}


class SyncReports(_SyncResourceBase):
    """Synchronous reports namespace."""

    _list_path = ""
    _singular_path = ""
    _create_path = ""


class AsyncReports(_AsyncResourceBase):
    """Asynchronous reports namespace."""

    _list_path = ""
    _singular_path = ""
    _create_path = ""


def _make_sync_report_method(path: str):
    def method(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        params = _serialize_params(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        return self._t.request("GET", path, **kw)
    return method


def _make_async_report_method(path: str):
    async def method(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        params = _serialize_params(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, params=params)
        return await self._t.request("GET", path, **kw)
    return method


for _method_name, _path in _REPORT_ENDPOINTS.items():
    setattr(SyncReports, _method_name, _make_sync_report_method(_path))
    setattr(AsyncReports, _method_name, _make_async_report_method(_path))


SYNC_RESOURCES["reports"] = SyncReports
ASYNC_RESOURCES["reports"] = AsyncReports


# ---------------------------------------------------------------------------
# Auth Sessions — create (POST) and retrieve (GET) only
# ---------------------------------------------------------------------------

def _auth_session_model() -> type:
    from nxus_qbd.models.core.auth_session import AuthSessionResponse
    return AuthSessionResponse


class SyncAuthSessions(_SyncResourceBase):
    _list_path = "/api/v1/auth-sessions"
    _singular_path = "/api/v1/auth-sessions/{id}"
    _create_path = "/api/v1/auth-sessions"
    _model = _auth_session_model()

    def create(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = self._t.request("POST", self._create_path, **kw)
        return _parse_one(resp, self._model)

    def retrieve(self, session_token: str, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout)
        resp = self._t.request("GET", self._singular_path.format(id=session_token), **kw)
        return _parse_one(resp, self._model)


class AsyncAuthSessions(_AsyncResourceBase):
    _list_path = "/api/v1/auth-sessions"
    _singular_path = "/api/v1/auth-sessions/{id}"
    _create_path = "/api/v1/auth-sessions"
    _model = _auth_session_model()

    async def create(self, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        body = _serialize_body(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout, json=body)
        resp = await self._t.request("POST", self._create_path, **kw)
        return _parse_one(resp, self._model)

    async def retrieve(self, session_token: str, **kwargs: Any) -> Any:
        connection_id, headers, timeout = _extract_options(kwargs)
        kw = _build_request_kwargs(connection_id, headers, timeout)
        resp = await self._t.request("GET", self._singular_path.format(id=session_token), **kw)
        return _parse_one(resp, self._model)


SYNC_RESOURCES["auth_sessions"] = SyncAuthSessions
ASYNC_RESOURCES["auth_sessions"] = AsyncAuthSessions


# ---------------------------------------------------------------------------
# Connections — full CRUD plus custom retrieve_status_authenticated
# ---------------------------------------------------------------------------

def _connection_model() -> Optional[type]:
    try:
        from nxus_qbd.models.core.connections import ConnectionResponse
    except ImportError:
        try:
            from nxus_qbd.models.core.connections import Connection
        except ImportError:
            return None
        return Connection
    return ConnectionResponse


def _connection_status_model() -> Optional[type]:
    try:
        from nxus_qbd.models.core.qwc_auth_setup import ConnectionStatus
    except ImportError:
        return None
    return ConnectionStatus


class SyncConnections(_SyncResourceBase, _SyncList, _SyncRetrieve, _SyncCreate, _SyncUpdate, _SyncDelete):
    _list_path = "/api/v1/connections"
    _singular_path = "/api/v1/connections/{id}"
    _create_path = "/api/v1/connections"
    _model = _connection_model()
    _status_model = _connection_status_model()

    def list(self, **kwargs: Any) -> CursorPage:
        connection_id, headers, timeout = _extract_options(kwargs)
        cursor = kwargs.pop("cursor", None)
        limit = kwargs.pop("limit", None)
        params = _serialize_params(kwargs) or {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        kw = _build_request_kwargs(connection_id, headers, timeout, params=params or None)
        body = self._t.request("GET", self._list_path, **kw)
        if isinstance(body, list):
            if self._model is not None:
                items = [self._model.model_validate(it) if isinstance(it, dict) else it for it in body]
            else:
                items = body
            body = {
                "data": items,
                "hasMore": False,
                "nextCursor": None,
                "count": len(items),
                "limit": limit,
                "totalCount": len(items),
            }
        else:
            body = _parse_list_items(body, self._model)

        fetch_kwargs: Dict[str, Any] = {}
        if connection_id:
            fetch_kwargs["connection_id"] = connection_id
        if headers:
            fetch_kwargs["headers"] = headers
        if timeout is not None:
            fetch_kwargs["timeout"] = timeout
        if limit is not None:
            fetch_kwargs["limit"] = limit
        fetch_kwargs.update(kwargs)

        return build_sync_cursor_page(body, fetcher=self.list, fetch_kwargs=fetch_kwargs)

    def retrieve_status_authenticated(self, connection_id: str, **kwargs: Any) -> Any:
        _, headers, timeout = _extract_options(kwargs)
        kw = _build_request_kwargs(None, headers, timeout)
        resp = self._t.request(
            "GET",
            f"/api/v1/qwc-auth-setup/{connection_id}/status/authenticated",
            **kw,
        )
        return _parse_one(resp, self._status_model)


class AsyncConnections(_AsyncResourceBase, _AsyncList, _AsyncRetrieve, _AsyncCreate, _AsyncUpdate, _AsyncDelete):
    _list_path = "/api/v1/connections"
    _singular_path = "/api/v1/connections/{id}"
    _create_path = "/api/v1/connections"
    _model = _connection_model()
    _status_model = _connection_status_model()

    async def list(self, **kwargs: Any) -> CursorPage:
        connection_id, headers, timeout = _extract_options(kwargs)
        cursor = kwargs.pop("cursor", None)
        limit = kwargs.pop("limit", None)
        params = _serialize_params(kwargs) or {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit

        kw = _build_request_kwargs(connection_id, headers, timeout, params=params or None)
        body = await self._t.request("GET", self._list_path, **kw)
        if isinstance(body, list):
            if self._model is not None:
                items = [self._model.model_validate(it) if isinstance(it, dict) else it for it in body]
            else:
                items = body
            body = {
                "data": items,
                "hasMore": False,
                "nextCursor": None,
                "count": len(items),
                "limit": limit,
                "totalCount": len(items),
            }
        else:
            body = _parse_list_items(body, self._model)

        fetch_kwargs: Dict[str, Any] = {}
        if connection_id:
            fetch_kwargs["connection_id"] = connection_id
        if headers:
            fetch_kwargs["headers"] = headers
        if timeout is not None:
            fetch_kwargs["timeout"] = timeout
        if limit is not None:
            fetch_kwargs["limit"] = limit
        fetch_kwargs.update(kwargs)

        return build_async_cursor_page(body, fetcher=self.list, fetch_kwargs=fetch_kwargs)

    async def retrieve_status_authenticated(self, connection_id: str, **kwargs: Any) -> Any:
        _, headers, timeout = _extract_options(kwargs)
        kw = _build_request_kwargs(None, headers, timeout)
        resp = await self._t.request(
            "GET",
            f"/api/v1/qwc-auth-setup/{connection_id}/status/authenticated",
            **kw,
        )
        return _parse_one(resp, self._status_model)


SYNC_RESOURCES["connections"] = SyncConnections
ASYNC_RESOURCES["connections"] = AsyncConnections
