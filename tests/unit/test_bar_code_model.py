from __future__ import annotations

from nxus_qbd.models import BarCode

from ._model_payloads import complete_model_payload


def test_bar_code_parses_without_revision_number():
    """Live list/retrieve responses omit revisionNumber even though the backend
    spec marks it required. spec/overlay.json corrects that upstream, so the
    model has to accept a payload without it."""
    payload = complete_model_payload(
        BarCode,
        id="800000A8-1892050011",
        createdAt="2026-04-01T00:00:00Z",
        updatedAt="2026-04-01T00:00:00Z",
        isActive=True,
    )
    payload.pop("revisionNumber", None)

    bar_code = BarCode.model_validate(payload)

    assert bar_code.revision_number is None
