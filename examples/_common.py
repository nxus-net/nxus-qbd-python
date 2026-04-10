"""Shared helpers for runnable SDK examples."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from nxus_qbd import NxusEnvironment, resolve_base_url
from nxus_qbd.config import resolve_verify

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def require_env(name: str, message: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    print(f"Error: {name} environment variable is required.")
    print(f"  {message}")
    sys.exit(1)


def resolve_environment() -> str | None:
    environment = os.environ.get("NXUS_ENVIRONMENT")
    if environment:
        return environment
    if os.environ.get("NXUS_DEV_MODE", "false").lower() == "true":
        return NxusEnvironment.DEVELOPMENT.value
    return None


def client_options() -> dict[str, Any]:
    return {
        "api_key": require_env("NXUS_API_KEY", "export NXUS_API_KEY='sk_test_...'"),
        "base_url": os.environ.get("NXUS_BASE_URL"),
        "environment": resolve_environment(),
    }


def effective_base_url() -> str:
    return resolve_base_url(
        base_url=os.environ.get("NXUS_BASE_URL"),
        environment=resolve_environment(),
    )


def effective_verify() -> bool:
    return resolve_verify(
        base_url=os.environ.get("NXUS_BASE_URL"),
        environment=resolve_environment(),
    )
