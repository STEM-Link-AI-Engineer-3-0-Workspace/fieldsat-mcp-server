"""Live runtime configuration tests."""

import pytest

from fieldsat.cli import parse_args
from fieldsat.runtime import create_live_server

LIVE_ENVIRONMENT = {
    "COPERNICUS_CLIENT_ID": "client-id",
    "COPERNICUS_CLIENT_SECRET": "client-secret",
}


def test_live_server_requires_provider_credentials() -> None:
    with pytest.raises(RuntimeError, match="COPERNICUS_CLIENT_ID"):
        create_live_server({})


async def test_live_server_exposes_the_same_tools() -> None:
    mcp = create_live_server(LIVE_ENVIRONMENT)
    assert [tool.name for tool in await mcp.list_tools()] == [
        "list_fields",
        "get_satellite_analysis",
        "get_weather_context",
    ]


def test_cli_defaults_to_stdio() -> None:
    args = parse_args([])
    assert args.transport == "stdio"
    assert args.port == 8000


def test_cli_accepts_http_and_demo() -> None:
    args = parse_args(["--transport", "http", "--port", "9000", "--demo"])
    assert (args.transport, args.port, args.demo) == ("http", 9000, True)


def test_testing_module_builds_an_http_app() -> None:
    from fieldsat.testing import app

    assert app is not None
