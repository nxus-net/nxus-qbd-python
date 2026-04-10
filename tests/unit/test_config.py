from nxus_qbd import (
    DEFAULT_BASE_URL,
    LOCAL_BASE_URL,
    NxusEnvironment,
    resolve_base_url,
)
from nxus_qbd.config import resolve_verify


def test_resolve_base_url_defaults_to_production():
    assert resolve_base_url() == DEFAULT_BASE_URL


def test_resolve_base_url_supports_development_aliases():
    assert resolve_base_url(environment="development") == LOCAL_BASE_URL
    assert resolve_base_url(environment="local") == LOCAL_BASE_URL
    assert resolve_base_url(environment=NxusEnvironment.DEVELOPMENT) == LOCAL_BASE_URL


def test_explicit_base_url_overrides_environment():
    assert (
        resolve_base_url(
            base_url="https://example.test/",
            environment=NxusEnvironment.DEVELOPMENT,
        )
        == "https://example.test/"
    )


def test_resolve_verify_defaults_by_environment():
    assert resolve_verify() is True
    assert resolve_verify(environment="development") is False
    assert resolve_verify(verify=True, environment="development") is True


def test_resolve_verify_disables_tls_for_explicit_localhost_base_url():
    assert resolve_verify(base_url=LOCAL_BASE_URL) is False
