from __future__ import annotations

from nxus_qbd.models import BarCode

from ._model_payloads import complete_model_payload


def test_bar_code_accepts_missing_revision_number():
    barcode = BarCode.model_validate(
        complete_model_payload(
            BarCode,
            id="800000A8-1892050011",
            createdAt="2026-04-01T00:00:00Z",
            updatedAt="2026-04-01T00:00:00Z",
            isActive=True,
        )
    )

    assert barcode.id == "800000A8-1892050011"
    assert barcode.revision_number is None
