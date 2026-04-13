import os
import httpx
import pytest
from dotenv import load_dotenv

from nxus_qbd import NxusEnvironment, resolve_base_url

load_dotenv()  # loads .env into os.environ


@pytest.fixture(scope="session")
def api_key():
    key = os.environ.get("NXUS_API_KEY")
    if not key:
        pytest.skip("NXUS_API_KEY not set — skipping integration tests")
    return key


@pytest.fixture(scope="session")
def base_url():
    return resolve_base_url(
        base_url=os.environ.get("NXUS_BASE_URL"),
        environment=os.environ.get("NXUS_ENVIRONMENT")
        or (NxusEnvironment.DEVELOPMENT if os.environ.get("NXUS_DEV_MODE", "false").lower() == "true" else None),
    )


@pytest.fixture(scope="session")
def dev_mode():
    return os.environ.get("NXUS_DEV_MODE", "false").lower() == "true"


@pytest.fixture(scope="session")
def connection_id():
    return os.environ.get("NXUS_CONNECTION_ID")


def _probe_backend(base_url: str, verify: bool) -> None:
    """Cheap reachability check. Skips the session if the host is unresponsive.

    Hits ``GET /`` because it's a fast unauthenticated health route on both
    localhost dev and production. The OpenAPI spec endpoint is not a safe
    probe — production doesn't serve it, and it's 5 MB on dev.
    """
    try:
        httpx.get(base_url, timeout=10.0, verify=verify, follow_redirects=True)
    except Exception as exc:
        pytest.skip(f"Integration backend unavailable at {base_url}: {exc}")


@pytest.fixture(scope="session")
def client(api_key, base_url, dev_mode):
    _probe_backend(base_url, verify=not dev_mode)
    timeout = float(os.environ.get("NXUS_TEST_TIMEOUT_SECONDS", "100"))

    from nxus_qbd import NxusClient
    with NxusClient(
        api_key=api_key,
        base_url=base_url,
        verify=not dev_mode,
        timeout=timeout,
    ) as c:
        yield c


@pytest.fixture(scope="session")
def async_client(api_key, base_url, dev_mode):
    """Provide the constructor args; tests create their own async client."""
    _probe_backend(base_url, verify=not dev_mode)
    timeout = float(os.environ.get("NXUS_TEST_TIMEOUT_SECONDS", "100"))
    return {
        "api_key": api_key,
        "base_url": base_url,
        "verify": not dev_mode,
        "timeout": timeout,
    }
