"""NxusClient — ergonomic Python wrapper for the Nxus QuickBooks Desktop API.

Provides both synchronous (``NxusClient``) and asynchronous (``AsyncNxusClient``)
clients that group every endpoint into resource namespaces::

    from nxus_qbd import NxusClient

    client = NxusClient(api_key="sk_live_...")
    vendors = client.vendors.list(limit=50)
    vendor = client.vendors.retrieve("some-id")
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nxus_qbd._transport import AsyncTransport, SyncTransport, DEFAULT_TIMEOUT_SECONDS
from nxus_qbd.config import (
    NxusEnvironment,
    resolve_base_url,
    resolve_verify,
)
from nxus_qbd.resources import ASYNC_RESOURCES, SYNC_RESOURCES

__all__ = ["NxusClient", "AsyncNxusClient"]


class NxusClient:
    """Synchronous Nxus API client.

    Parameters
    ----------
    api_key:
        Your Nxus API key (``sk_live_...`` or ``sk_test_...``).
    base_url:
        Explicit base URL override. Defaults to ``https://api.nx-us.net/``
        unless ``environment="development"`` is set.
    environment:
        Named environment shortcut. Use ``"development"`` (or ``"local"``)
        for ``https://localhost:7242/``. Production is the default.
    headers:
        Extra headers merged into every request (e.g. ``X-Connection-Id``).
    timeout:
        Default request timeout in seconds. Defaults to ``100.0`` so the SDK
        waits slightly longer than the backend's structured timeout budgets.
    verify:
        TLS verification override. Defaults to ``True`` in production and
        ``False`` in development unless explicitly set.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: Optional[str] = None,
        environment: Optional[str | NxusEnvironment] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        verify: Optional[bool] = None,
    ) -> None:
        resolved_base_url = resolve_base_url(base_url=base_url, environment=environment)
        resolved_verify = resolve_verify(
            verify=verify,
            base_url=resolved_base_url,
            environment=environment,
        )
        self._transport = SyncTransport(
            base_url=resolved_base_url,
            api_key=api_key,
            headers=headers,
            timeout=timeout,
            verify=resolved_verify,
        )

        # Eagerly build every resource namespace so attribute access is O(1)
        # and IDE autocompletion works on the cached instances.
        self._resources: Dict[str, Any] = {}
        for ns, cls in SYNC_RESOURCES.items():
            resource = cls(self._transport)
            self._resources[ns] = resource

    def __getattr__(self, name: str) -> Any:
        try:
            return self._resources[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' has no resource namespace '{name}'"
            ) from None

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self) -> "NxusClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- Explicit properties for the most common namespaces so that type
    #    checkers and IDEs can provide completions.  ``__getattr__`` still
    #    handles *all* namespaces at runtime. ---------------------------------

    @property
    def ar_refund_credit_cards(self) -> Any:
        """AR Refund Credit Cards — full CRUD."""
        return self._resources["ar_refund_credit_cards"]

    @property
    def bills(self) -> Any:
        """Bills — full CRUD."""
        return self._resources["bills"]

    @property
    def check_bills(self) -> Any:
        """Check Bills — full CRUD."""
        return self._resources["check_bills"]

    @property
    def checks(self) -> Any:
        """Checks — full CRUD."""
        return self._resources["checks"]

    @property
    def credit_card_bills(self) -> Any:
        """Credit Card Bills — full CRUD."""
        return self._resources["credit_card_bills"]

    @property
    def credit_card_credits(self) -> Any:
        """Credit Card Credits — full CRUD."""
        return self._resources["credit_card_credits"]

    @property
    def deposits(self) -> Any:
        """Deposits — full CRUD."""
        return self._resources["deposits"]

    @property
    def estimates(self) -> Any:
        """Estimates — full CRUD."""
        return self._resources["estimates"]

    @property
    def item_receipts(self) -> Any:
        """Item Receipts — full CRUD."""
        return self._resources["item_receipts"]

    @property
    def journal_entries(self) -> Any:
        """Journal Entries — full CRUD."""
        return self._resources["journal_entries"]

    @property
    def purchase_orders(self) -> Any:
        """Purchase Orders — full CRUD."""
        return self._resources["purchase_orders"]

    @property
    def sales_receipts(self) -> Any:
        """Sales Receipts — full CRUD."""
        return self._resources["sales_receipts"]

    @property
    def sales_tax_payment_checks(self) -> Any:
        """Sales Tax Payment Checks — full CRUD."""
        return self._resources["sales_tax_payment_checks"]

    @property
    def time_trackings(self) -> Any:
        """Time Trackings — full CRUD."""
        return self._resources["time_trackings"]

    @property
    def transactions(self) -> Any:
        """Transactions — list, retrieve, delete only."""
        return self._resources["transactions"]

    @property
    def vendor_credits(self) -> Any:
        """Vendor Credits — full CRUD."""
        return self._resources["vendor_credits"]

    @property
    def build_assemblies(self) -> Any:
        """Build Assemblies — full CRUD."""
        return self._resources["build_assemblies"]

    @property
    def charges(self) -> Any:
        """Charges — full CRUD."""
        return self._resources["charges"]

    @property
    def credit_card_charges(self) -> Any:
        """Credit Card Charges — full CRUD."""
        return self._resources["credit_card_charges"]

    @property
    def credit_memos(self) -> Any:
        """Credit Memos — full CRUD."""
        return self._resources["credit_memos"]

    @property
    def inventory_adjustments(self) -> Any:
        """Inventory Adjustments — full CRUD."""
        return self._resources["inventory_adjustments"]

    @property
    def invoices(self) -> Any:
        """Invoices — full CRUD."""
        return self._resources["invoices"]

    @property
    def receive_payments(self) -> Any:
        """Receive Payments — full CRUD."""
        return self._resources["receive_payments"]

    @property
    def accounts(self) -> Any:
        """Accounts — full CRUD."""
        return self._resources["accounts"]

    @property
    def account_tax_line_infos(self) -> Any:
        """Account Tax Line Infos — retrieve only."""
        return self._resources["account_tax_line_infos"]

    @property
    def bar_codes(self) -> Any:
        """Bar Codes — list, retrieve, delete."""
        return self._resources["bar_codes"]

    @property
    def billing_rates(self) -> Any:
        """Billing Rates — list, retrieve, create, delete."""
        return self._resources["billing_rates"]

    @property
    def qbd_classes(self) -> Any:
        """QBD Classes — full CRUD."""
        return self._resources["qbd_classes"]

    @property
    def currencies(self) -> Any:
        """Currencies — list, retrieve, create, update (no delete)."""
        return self._resources["currencies"]

    @property
    def customers(self) -> Any:
        """Customers — full CRUD."""
        return self._resources["customers"]

    @property
    def customer_types(self) -> Any:
        """Customer Types — full CRUD."""
        return self._resources["customer_types"]

    @property
    def date_driven_terms(self) -> Any:
        """Date-Driven Terms — full CRUD."""
        return self._resources["date_driven_terms"]

    @property
    def employees(self) -> Any:
        """Employees — full CRUD."""
        return self._resources["employees"]

    @property
    def inventory_sites(self) -> Any:
        """Inventory Sites — full CRUD."""
        return self._resources["inventory_sites"]

    @property
    def other_names(self) -> Any:
        """Other Names — full CRUD."""
        return self._resources["other_names"]

    @property
    def payment_methods(self) -> Any:
        """Payment Methods — full CRUD."""
        return self._resources["payment_methods"]

    @property
    def price_levels(self) -> Any:
        """Price Levels — full CRUD."""
        return self._resources["price_levels"]

    @property
    def sales_tax_codes(self) -> Any:
        """Sales Tax Codes — full CRUD."""
        return self._resources["sales_tax_codes"]

    @property
    def ship_methods(self) -> Any:
        """Ship Methods — full CRUD."""
        return self._resources["ship_methods"]

    @property
    def special_items(self) -> Any:
        """Special Items — create only."""
        return self._resources["special_items"]

    @property
    def terms(self) -> Any:
        """Terms — full CRUD."""
        return self._resources["terms"]

    @property
    def unit_of_measure_sets(self) -> Any:
        """Unit of Measure Sets — list, retrieve, create."""
        return self._resources["unit_of_measure_sets"]

    @property
    def vendors(self) -> Any:
        """Vendors — full CRUD."""
        return self._resources["vendors"]

    @property
    def vendor_types(self) -> Any:
        """Vendor Types — list, retrieve, create, delete."""
        return self._resources["vendor_types"]

    @property
    def bill_to_pay(self) -> Any:
        """Bills to Pay — list, retrieve only."""
        return self._resources["bill_to_pay"]

    @property
    def items(self) -> Any:
        """Items — aggregate read-only view across all item types."""
        return self._resources["items"]

    @property
    def inventory_items(self) -> Any:
        """Inventory Items — full CRUD."""
        return self._resources["inventory_items"]

    @property
    def item_discounts(self) -> Any:
        """Item Discounts — full CRUD."""
        return self._resources["item_discounts"]

    @property
    def item_fixed_assets(self) -> Any:
        """Item Fixed Assets — full CRUD."""
        return self._resources["item_fixed_assets"]

    @property
    def item_groups(self) -> Any:
        """Item Groups — full CRUD."""
        return self._resources["item_groups"]

    @property
    def item_inventory_assemblies(self) -> Any:
        """Item Inventory Assemblies — full CRUD."""
        return self._resources["item_inventory_assemblies"]

    @property
    def item_non_inventory(self) -> Any:
        """Item Non-Inventory — full CRUD."""
        return self._resources["item_non_inventory"]

    @property
    def item_other_charges(self) -> Any:
        """Item Other Charges — full CRUD."""
        return self._resources["item_other_charges"]

    @property
    def item_payments(self) -> Any:
        """Item Payments — full CRUD."""
        return self._resources["item_payments"]

    @property
    def item_sales_tax(self) -> Any:
        """Item Sales Tax — full CRUD."""
        return self._resources["item_sales_tax"]

    @property
    def item_sales_tax_groups(self) -> Any:
        """Item Sales Tax Groups — full CRUD."""
        return self._resources["item_sales_tax_groups"]

    @property
    def service_items(self) -> Any:
        """Service Items — full CRUD."""
        return self._resources["service_items"]

    @property
    def item_subtotals(self) -> Any:
        """Item Subtotals — full CRUD."""
        return self._resources["item_subtotals"]

    @property
    def payroll_item_non_wages(self) -> Any:
        """Payroll Item Non-Wages — list, retrieve, delete."""
        return self._resources["payroll_item_non_wages"]

    @property
    def payroll_item_wages(self) -> Any:
        """Payroll Item Wages — list, retrieve, create, delete."""
        return self._resources["payroll_item_wages"]

    @property
    def workers_comp_codes(self) -> Any:
        """Workers Comp Codes — full CRUD."""
        return self._resources["workers_comp_codes"]

    @property
    def reports(self) -> Any:
        """Reports — QuickBooks Desktop report endpoints."""
        return self._resources["reports"]

    @property
    def auth_sessions(self) -> Any:
        """Auth Sessions — create and retrieve."""
        return self._resources["auth_sessions"]

    @property
    def connections(self) -> Any:
        """Connections — full CRUD plus status check."""
        return self._resources["connections"]


class AsyncNxusClient:
    """Asynchronous Nxus API client.

    Parameters
    ----------
    api_key:
        Your Nxus API key (``sk_live_...`` or ``sk_test_...``).
    base_url:
        Explicit base URL override. Defaults to ``https://api.nx-us.net/``
        unless ``environment="development"`` is set.
    environment:
        Named environment shortcut. Use ``"development"`` (or ``"local"``)
        for ``https://localhost:7242/``. Production is the default.
    headers:
        Extra headers merged into every request.
    timeout:
        Default request timeout in seconds. Defaults to ``100.0`` so the SDK
        waits slightly longer than the backend's structured timeout budgets.
    verify:
        TLS verification override. Defaults to ``True`` in production and
        ``False`` in development unless explicitly set.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: Optional[str] = None,
        environment: Optional[str | NxusEnvironment] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        verify: Optional[bool] = None,
    ) -> None:
        resolved_base_url = resolve_base_url(base_url=base_url, environment=environment)
        resolved_verify = resolve_verify(
            verify=verify,
            base_url=resolved_base_url,
            environment=environment,
        )
        self._transport = AsyncTransport(
            base_url=resolved_base_url,
            api_key=api_key,
            headers=headers,
            timeout=timeout,
            verify=resolved_verify,
        )

        self._resources: Dict[str, Any] = {}
        for ns, cls in ASYNC_RESOURCES.items():
            resource = cls(self._transport)
            self._resources[ns] = resource

    def __getattr__(self, name: str) -> Any:
        try:
            return self._resources[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' has no resource namespace '{name}'"
            ) from None

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._transport.close()

    async def __aenter__(self) -> "AsyncNxusClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # -- Explicit properties (mirrors NxusClient) ----------------------------

    @property
    def ar_refund_credit_cards(self) -> Any:
        """AR Refund Credit Cards — full CRUD."""
        return self._resources["ar_refund_credit_cards"]

    @property
    def bills(self) -> Any:
        """Bills — full CRUD."""
        return self._resources["bills"]

    @property
    def check_bills(self) -> Any:
        """Check Bills — full CRUD."""
        return self._resources["check_bills"]

    @property
    def checks(self) -> Any:
        """Checks — full CRUD."""
        return self._resources["checks"]

    @property
    def credit_card_bills(self) -> Any:
        """Credit Card Bills — full CRUD."""
        return self._resources["credit_card_bills"]

    @property
    def credit_card_credits(self) -> Any:
        """Credit Card Credits — full CRUD."""
        return self._resources["credit_card_credits"]

    @property
    def deposits(self) -> Any:
        """Deposits — full CRUD."""
        return self._resources["deposits"]

    @property
    def estimates(self) -> Any:
        """Estimates — full CRUD."""
        return self._resources["estimates"]

    @property
    def item_receipts(self) -> Any:
        """Item Receipts — full CRUD."""
        return self._resources["item_receipts"]

    @property
    def journal_entries(self) -> Any:
        """Journal Entries — full CRUD."""
        return self._resources["journal_entries"]

    @property
    def purchase_orders(self) -> Any:
        """Purchase Orders — full CRUD."""
        return self._resources["purchase_orders"]

    @property
    def sales_receipts(self) -> Any:
        """Sales Receipts — full CRUD."""
        return self._resources["sales_receipts"]

    @property
    def sales_tax_payment_checks(self) -> Any:
        """Sales Tax Payment Checks — full CRUD."""
        return self._resources["sales_tax_payment_checks"]

    @property
    def time_trackings(self) -> Any:
        """Time Trackings — full CRUD."""
        return self._resources["time_trackings"]

    @property
    def transactions(self) -> Any:
        """Transactions — list, retrieve, delete only."""
        return self._resources["transactions"]

    @property
    def vendor_credits(self) -> Any:
        """Vendor Credits — full CRUD."""
        return self._resources["vendor_credits"]

    @property
    def build_assemblies(self) -> Any:
        """Build Assemblies — full CRUD."""
        return self._resources["build_assemblies"]

    @property
    def charges(self) -> Any:
        """Charges — full CRUD."""
        return self._resources["charges"]

    @property
    def credit_card_charges(self) -> Any:
        """Credit Card Charges — full CRUD."""
        return self._resources["credit_card_charges"]

    @property
    def credit_memos(self) -> Any:
        """Credit Memos — full CRUD."""
        return self._resources["credit_memos"]

    @property
    def inventory_adjustments(self) -> Any:
        """Inventory Adjustments — full CRUD."""
        return self._resources["inventory_adjustments"]

    @property
    def invoices(self) -> Any:
        """Invoices — full CRUD."""
        return self._resources["invoices"]

    @property
    def receive_payments(self) -> Any:
        """Receive Payments — full CRUD."""
        return self._resources["receive_payments"]

    @property
    def accounts(self) -> Any:
        """Accounts — full CRUD."""
        return self._resources["accounts"]

    @property
    def account_tax_line_infos(self) -> Any:
        """Account Tax Line Infos — retrieve only."""
        return self._resources["account_tax_line_infos"]

    @property
    def bar_codes(self) -> Any:
        """Bar Codes — list, retrieve, delete."""
        return self._resources["bar_codes"]

    @property
    def billing_rates(self) -> Any:
        """Billing Rates — list, retrieve, create, delete."""
        return self._resources["billing_rates"]

    @property
    def qbd_classes(self) -> Any:
        """QBD Classes — full CRUD."""
        return self._resources["qbd_classes"]

    @property
    def currencies(self) -> Any:
        """Currencies — list, retrieve, create, update (no delete)."""
        return self._resources["currencies"]

    @property
    def customers(self) -> Any:
        """Customers — full CRUD."""
        return self._resources["customers"]

    @property
    def customer_types(self) -> Any:
        """Customer Types — full CRUD."""
        return self._resources["customer_types"]

    @property
    def date_driven_terms(self) -> Any:
        """Date-Driven Terms — full CRUD."""
        return self._resources["date_driven_terms"]

    @property
    def employees(self) -> Any:
        """Employees — full CRUD."""
        return self._resources["employees"]

    @property
    def inventory_sites(self) -> Any:
        """Inventory Sites — full CRUD."""
        return self._resources["inventory_sites"]

    @property
    def other_names(self) -> Any:
        """Other Names — full CRUD."""
        return self._resources["other_names"]

    @property
    def payment_methods(self) -> Any:
        """Payment Methods — full CRUD."""
        return self._resources["payment_methods"]

    @property
    def price_levels(self) -> Any:
        """Price Levels — full CRUD."""
        return self._resources["price_levels"]

    @property
    def sales_tax_codes(self) -> Any:
        """Sales Tax Codes — full CRUD."""
        return self._resources["sales_tax_codes"]

    @property
    def ship_methods(self) -> Any:
        """Ship Methods — full CRUD."""
        return self._resources["ship_methods"]

    @property
    def special_items(self) -> Any:
        """Special Items — create only."""
        return self._resources["special_items"]

    @property
    def terms(self) -> Any:
        """Terms — full CRUD."""
        return self._resources["terms"]

    @property
    def unit_of_measure_sets(self) -> Any:
        """Unit of Measure Sets — list, retrieve, create."""
        return self._resources["unit_of_measure_sets"]

    @property
    def vendors(self) -> Any:
        """Vendors — full CRUD."""
        return self._resources["vendors"]

    @property
    def vendor_types(self) -> Any:
        """Vendor Types — list, retrieve, create, delete."""
        return self._resources["vendor_types"]

    @property
    def bill_to_pay(self) -> Any:
        """Bills to Pay — list, retrieve only."""
        return self._resources["bill_to_pay"]

    @property
    def items(self) -> Any:
        """Items — aggregate read-only view across all item types."""
        return self._resources["items"]

    @property
    def inventory_items(self) -> Any:
        """Inventory Items — full CRUD."""
        return self._resources["inventory_items"]

    @property
    def item_discounts(self) -> Any:
        """Item Discounts — full CRUD."""
        return self._resources["item_discounts"]

    @property
    def item_fixed_assets(self) -> Any:
        """Item Fixed Assets — full CRUD."""
        return self._resources["item_fixed_assets"]

    @property
    def item_groups(self) -> Any:
        """Item Groups — full CRUD."""
        return self._resources["item_groups"]

    @property
    def item_inventory_assemblies(self) -> Any:
        """Item Inventory Assemblies — full CRUD."""
        return self._resources["item_inventory_assemblies"]

    @property
    def item_non_inventory(self) -> Any:
        """Item Non-Inventory — full CRUD."""
        return self._resources["item_non_inventory"]

    @property
    def item_other_charges(self) -> Any:
        """Item Other Charges — full CRUD."""
        return self._resources["item_other_charges"]

    @property
    def item_payments(self) -> Any:
        """Item Payments — full CRUD."""
        return self._resources["item_payments"]

    @property
    def item_sales_tax(self) -> Any:
        """Item Sales Tax — full CRUD."""
        return self._resources["item_sales_tax"]

    @property
    def item_sales_tax_groups(self) -> Any:
        """Item Sales Tax Groups — full CRUD."""
        return self._resources["item_sales_tax_groups"]

    @property
    def service_items(self) -> Any:
        """Service Items — full CRUD."""
        return self._resources["service_items"]

    @property
    def item_subtotals(self) -> Any:
        """Item Subtotals — full CRUD."""
        return self._resources["item_subtotals"]

    @property
    def payroll_item_non_wages(self) -> Any:
        """Payroll Item Non-Wages — list, retrieve, delete."""
        return self._resources["payroll_item_non_wages"]

    @property
    def payroll_item_wages(self) -> Any:
        """Payroll Item Wages — list, retrieve, create, delete."""
        return self._resources["payroll_item_wages"]

    @property
    def workers_comp_codes(self) -> Any:
        """Workers Comp Codes — full CRUD."""
        return self._resources["workers_comp_codes"]

    @property
    def reports(self) -> Any:
        """Reports — QuickBooks Desktop report endpoints."""
        return self._resources["reports"]

    @property
    def auth_sessions(self) -> Any:
        """Auth Sessions — create and retrieve."""
        return self._resources["auth_sessions"]

    @property
    def connections(self) -> Any:
        """Connections — full CRUD plus status check."""
        return self._resources["connections"]
