"""Live runtime configuration tests."""

import pytest

from fieldsat.cli import parse_args
from fieldsat.runtime import create_live_server


def test_live_server_requires_provider_credentials() -> None:
    with pytest.raises(RuntimeError, match="COPERNICUS_CLIENT_ID"):
        create_live_server({})


def test_cli_demo_flag() -> None:
    assert parse_args(["--demo"]).demo is True
