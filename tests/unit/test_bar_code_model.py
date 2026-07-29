from __future__ import annotations

import pytest
from pydantic import ValidationError

from nxus_qbd.models import BarCode

from ._model_payloads import complete_model_payload


def test_bar_code_requires_revision_number():
    payload = complete_model_payload(
        BarCode,
        id="800000A8-1892050011",
        createdAt="2026-04-01T00:00:00Z",
        updatedAt="2026-04-01T00:00:00Z",
        isActive=True,
    )
    payload.pop("revisionNumber")

    with pytest.raises(ValidationError):
        BarCode.model_validate(payload)
