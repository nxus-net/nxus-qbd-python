"""Environment and base URL helpers for the Nxus Python SDK."""

from __future__ import annotations

from enum import Enum
from typing import Optional

DEFAULT_BASE_URL = "https://api.nx-us.net/"
LOCAL_BASE_URL = "https://localhost:7242/"


class NxusEnvironment(str, Enum):
    """Named SDK environments with stable default base URLs."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"


def normalize_environment(environment: Optional[str | NxusEnvironment]) -> NxusEnvironment:
    """Normalize environment aliases into a stable enum value."""
    if environment is None:
        return NxusEnvironment.PRODUCTION
    if isinstance(environment, NxusEnvironment):
        return environment

    value = environment.strip().lower().replace("_", "-")
    if value in {"production", "prod", "live"}:
        return NxusEnvironment.PRODUCTION
    if value in {"development", "develop", "dev", "local", "localhost"}:
        return NxusEnvironment.DEVELOPMENT

    raise ValueError(
        "Unsupported environment. Use 'production' or 'development'."
    )


def resolve_base_url(
    *,
    base_url: Optional[str] = None,
    environment: Optional[str | NxusEnvironment] = None,
) -> str:
    """Resolve the SDK base URL.

    Explicit ``base_url`` always wins. Otherwise, the environment decides:
    production -> ``https://api.nx-us.net/``
    development -> ``https://localhost:7242/``
    """
    if base_url:
        return base_url

    env = normalize_environment(environment)
    if env is NxusEnvironment.DEVELOPMENT:
        return LOCAL_BASE_URL
    return DEFAULT_BASE_URL


def resolve_verify(
    *,
    verify: Optional[bool] = None,
    base_url: Optional[str] = None,
    environment: Optional[str | NxusEnvironment] = None,
) -> bool:
    """Resolve TLS verification behavior.

    Explicit ``verify`` always wins. Development defaults to ``False`` to make
    local self-signed certificates painless; production defaults to ``True``.
    """
    if verify is not None:
        return verify
    if base_url:
        lowered = base_url.lower()
        if "localhost" in lowered or "127.0.0.1" in lowered:
            return False
    return normalize_environment(environment) is not NxusEnvironment.DEVELOPMENT
