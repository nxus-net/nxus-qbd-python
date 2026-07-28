from importlib.metadata import version

from nxus_qbd import __version__


def test_runtime_version_matches_distribution_metadata():
    assert __version__ == version("nxus-qbd")
