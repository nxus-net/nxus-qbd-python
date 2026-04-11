from __future__ import annotations

from nxus_qbd.models import BarCode


def test_bar_code_accepts_missing_revision_number():
    barcode = BarCode(
        id="800000A8-1892050011",
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
        is_active=True,
    )

    assert barcode.id == "800000A8-1892050011"
    assert barcode.revision_number is None
