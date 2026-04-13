from __future__ import annotations

from nxus_qbd.models import Customer, QbdRef


def test_qbd_ref_accepts_full_name_without_id():
    ref = QbdRef(full_name="Net 60")

    assert ref.id is None
    assert ref.full_name == "Net 60"


def test_customer_accepts_partial_nested_refs():
    customer = Customer(
        id="8000009F-1892066345",
        created_at="2029-12-15T21:59:05+00:00",
        updated_at="2029-12-15T21:59:05+00:00",
        revision_number="1892066345",
        customer_type={"fullName": "Search Engine"},
        terms={"fullName": "Net 60"},
        sales_rep={"fullName": "MK"},
    )

    assert customer.customer_type is not None
    assert customer.customer_type.id is None
    assert customer.customer_type.full_name == "Search Engine"
    assert customer.terms is not None
    assert customer.terms.full_name == "Net 60"
    assert customer.sales_rep is not None
    assert customer.sales_rep.full_name == "MK"
