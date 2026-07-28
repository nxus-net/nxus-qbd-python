from __future__ import annotations

from nxus_qbd.models import Customer, QbdRef

from ._model_payloads import complete_model_payload


def test_qbd_ref_requires_id_and_exposes_fullname():
    ref = QbdRef(id="80000001-1234567890", fullname="Net 60")

    assert ref.id == "80000001-1234567890"
    assert ref.fullname == "Net 60"


def test_customer_accepts_nested_refs():
    customer = Customer.model_validate(
        complete_model_payload(
            Customer,
            id="8000009F-1892066345",
            createdAt="2029-12-15T21:59:05+00:00",
            updatedAt="2029-12-15T21:59:05+00:00",
            revisionNumber="1892066345",
            customerType={"id": "80000001-1", "fullname": "Search Engine"},
            terms={"id": "80000002-1", "fullname": "Net 60"},
            salesRep={"id": "80000003-1", "fullname": "MK"},
        )
    )

    assert customer.customer_type is not None
    assert customer.customer_type.id == "80000001-1"
    assert customer.customer_type.fullname == "Search Engine"
    assert customer.terms is not None
    assert customer.terms.fullname == "Net 60"
    assert customer.sales_rep is not None
    assert customer.sales_rep.fullname == "MK"
