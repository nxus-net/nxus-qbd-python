from __future__ import annotations

import types
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Union, get_args, get_origin
from uuid import UUID

from pydantic import BaseModel


def complete_model_payload(model: type[BaseModel], /, **overrides: Any) -> dict[str, Any]:
    """Build a wire payload containing every field required by a generated model."""
    payload: dict[str, Any] = {}
    provided = set(overrides)

    for name, field in model.model_fields.items():
        wire_name = field.alias or name
        if not field.is_required() or name in provided or wire_name in provided:
            continue
        payload[wire_name] = _placeholder(field.annotation)

    payload.update(overrides)
    return payload


def _placeholder(annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (Union, types.UnionType):
        if type(None) in args:
            return None
        return _placeholder(args[0])
    if origin is Literal:
        return args[0]
    if origin is list:
        return []
    if origin is dict:
        return {}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return complete_model_payload(annotation)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(member.value for member in annotation if member.value is not None)

    placeholders = {
        str: "value",
        bool: False,
        int: 1,
        float: 1.0,
        date: "2025-01-01",
        datetime: "2025-01-01T00:00:00Z",
        UUID: "00000000-0000-0000-0000-000000000000",
    }
    try:
        return placeholders[annotation]
    except KeyError as exc:
        raise AssertionError(f"No test placeholder for required annotation {annotation!r}") from exc
