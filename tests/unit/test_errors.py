"""Unit tests for :mod:`nxus_qbd.errors`."""

from __future__ import annotations

from nxus_qbd.errors import NxusApiError


def _make(**kwargs) -> NxusApiError:
    kwargs.setdefault("user_message", "msg")
    return NxusApiError("msg", **kwargs)


class TestIsValidationError:
    def test_400_with_validation_code(self) -> None:
        err = _make(status=400, code="VALIDATION_ERROR", type="VALIDATION_ERROR_TYPE")
        assert err.is_validation_error is True

    def test_422_with_per_field_errors(self) -> None:
        err = _make(
            status=422,
            code="VALIDATION_ERROR",
            type="VALIDATION_ERROR_TYPE",
            validation_errors={"name": ["Required."]},
        )
        assert err.is_validation_error is True

    def test_400_non_validation_is_false(self) -> None:
        err = _make(status=400, code="BAD_REQUEST", type="API_ERROR_TYPE")
        assert err.is_validation_error is False

    def test_500_is_false(self) -> None:
        err = _make(status=500, code="INTERNAL_ERROR", type="API_ERROR_TYPE")
        assert err.is_validation_error is False
