"""Protocol smoke test: start the demo server over HTTP and exercise it through a real client."""

import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_until_listening(port: int, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"server did not listen on port {port}")


async def check(url: str, mode: str) -> None:
    async with Client(url, mode=mode) as client:  # type: ignore[arg-type]
        tools = [tool.name for tool in await client.list_tools()]
        assert tools == ["list_fields", "get_satellite_analysis", "get_weather_context"], tools
        result = await client.call_tool(
            "get_satellite_analysis", {"field_id": "SL-PADDY-MINNERIYA", "comparison_days": 14}
        )
        assert result.structured_content is not None
        assert result.structured_content["trend"] == "significant_decline"
        failure = await client.call_tool(
            "get_weather_context", {"field_id": "SL-PADDY-WEATHER-FAIL"}, raise_on_error=False
        )
        assert failure.is_error
        print(f"{mode}: protocol {client.protocol_version}, {len(tools)} tools, calls ok")


def main() -> None:
    port = free_port()
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "fieldsat",
            "--demo",
            "--transport",
            "http",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_until_listening(port)
        url = f"http://127.0.0.1:{port}/mcp"
        asyncio.run(check(url, "auto"))
        asyncio.run(check(url, "legacy"))
    finally:
        server.terminate()
        server.wait(timeout=5)
    print("MCP protocol smoke passed.")


if __name__ == "__main__":
    main()
