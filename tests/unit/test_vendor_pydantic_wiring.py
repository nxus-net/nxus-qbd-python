"""End-to-end unit test for Pydantic model wiring on the vendors resource.

Uses a fake transport so no network or API key is required. Verifies:

  1. Create accepts a Pydantic Vendor and serializes it with camelCase aliases
  2. Create accepts flat kwargs (snake_case) and the response is parsed
  3. Retrieve returns a typed Vendor with snake_case attribute access
  4. List returns an envelope whose data items are typed Vendor instances
  5. Update accepts a Pydantic Vendor for the body
"""

from __future__ import annotations

from typing import Any

import pytest

from nxus_qbd.models import Vendor
from nxus_qbd.resources import SYNC_RESOURCES


class FakeSyncTransport:
    """Records every request and returns a queued response."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def queue(self, response: Any) -> None:
        self.responses.append(response)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.responses.pop(0)


@pytest.fixture
def vendors():
    transport = FakeSyncTransport()
    cls = SYNC_RESOURCES["vendors"]
    resource = cls(transport)
    return resource, transport


def _wire_vendor(**overrides: Any) -> dict:
    """A minimal valid Vendor wire payload (camelCase)."""
    base = {
        "id": "80000001-1234567890",
        "objectType": "qbd_vendor",
        "name": "Acme",
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-01T00:00:00Z",
        "revisionNumber": "1",
        "companyName": "Acme Inc.",
        "phone": "555-0100",
    }
    base.update(overrides)
    return base


def test_retrieve_returns_typed_vendor(vendors):
    resource, transport = vendors
    transport.queue(_wire_vendor())

    result = resource.retrieve("80000001-1234567890", connection_id="conn-1")

    assert isinstance(result, Vendor)
    # snake_case attribute access works
    assert result.company_name == "Acme Inc."
    assert result.revision_number == "1"
    assert result.phone == "555-0100"
    # Wire-format request was made
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/v1/vendor/80000001-1234567890"
    assert call["headers"]["X-Connection-Id"] == "conn-1"


def test_create_accepts_pydantic_model(vendors):
    resource, transport = vendors
    transport.queue(_wire_vendor(companyName="Foo LLC"))

    payload = Vendor(
        id="placeholder",
        createdAt="2025-01-01T00:00:00Z",
        updatedAt="2025-01-01T00:00:00Z",
        revisionNumber="1",
        companyName="Foo LLC",
    )
    result = resource.create(vendor=payload, connection_id="conn-1")

    assert isinstance(result, Vendor)
    assert result.company_name == "Foo LLC"
    # The wire body was serialized with camelCase aliases
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/v1/vendor"
    assert call["json"]["companyName"] == "Foo LLC"
    assert call["json"]["revisionNumber"] == "1"
    assert "company_name" not in call["json"]  # snake_case must NOT leak to wire


def test_create_accepts_flat_kwargs(vendors):
    resource, transport = vendors
    transport.queue(_wire_vendor(companyName="Bar Co"))

    result = resource.create(companyName="Bar Co", phone="555-9999", connection_id="conn-1")

    assert isinstance(result, Vendor)
    assert result.company_name == "Bar Co"
    call = transport.calls[0]
    assert call["json"] == {"companyName": "Bar Co", "phone": "555-9999"}


def test_create_accepts_snake_case_kwargs(vendors):
    resource, transport = vendors
    transport.queue(_wire_vendor(companyName="Snake Co"))

    result = resource.create(
        company_name="Snake Co",
        phone="555-2222",
        billing_address={"postal_code": "73301"},
        connection_id="conn-1",
    )

    assert isinstance(result, Vendor)
    assert result.company_name == "Snake Co"
    call = transport.calls[0]
    assert call["json"] == {
        "companyName": "Snake Co",
        "phone": "555-2222",
        "billingAddress": {"postalCode": "73301"},
    }


def test_vendor_model_accepts_snake_case_fields():
    vendor = Vendor(
        id="80000001-1234567890",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        revision_number="1",
        company_name="Snake Case LLC",
    )

    assert vendor.company_name == "Snake Case LLC"
    assert vendor.revision_number == "1"


def test_list_returns_typed_items(vendors):
    resource, transport = vendors
    transport.queue(
        {
            "data": [_wire_vendor(id="A"), _wire_vendor(id="B", companyName="Beta")],
            "nextCursor": None,
            "hasMore": False,
        }
    )

    page = resource.list(limit=10, connection_id="conn-1")

    # CursorPage exposes .data as the parsed list
    items = page.data
    assert len(items) == 2
    assert all(isinstance(v, Vendor) for v in items)
    assert items[0].id == "A"
    assert items[1].company_name == "Beta"


def test_update_serializes_pydantic_model(vendors):
    resource, transport = vendors
    transport.queue(_wire_vendor(companyName="Renamed"))

    payload = Vendor(
        id="80000001-1234567890",
        createdAt="2025-01-01T00:00:00Z",
        updatedAt="2025-01-01T00:00:00Z",
        revisionNumber="2",
        companyName="Renamed",
    )
    result = resource.update("80000001-1234567890", vendor=payload, connection_id="conn-1")

    assert isinstance(result, Vendor)
    assert result.company_name == "Renamed"
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/v1/vendor/80000001-1234567890"
    assert call["json"]["companyName"] == "Renamed"
    assert call["json"]["revisionNumber"] == "2"
