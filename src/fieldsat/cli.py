"""Command line entry point: pick the data source and the transport, then serve."""

import argparse
import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv

from fieldsat.runtime import create_demo_server, create_live_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fieldsat", description="Serve field evidence over MCP.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="stdio: the client starts this process. http: serve on a URL. sse: legacy HTTP.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Address to listen on (http, sse)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (http, sse)")
    parser.add_argument(
        "--demo",
        action="store_true",
        default=os.environ.get("STEMLINK_MCP_DEMO") == "1",
        help="Serve fixed demo numbers instead of calling Copernicus and Open-Meteo.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    # Read .env from the working directory. Variables already set in the environment win.
    # Load before parse_args: the --demo default reads STEMLINK_MCP_DEMO.
    load_dotenv(find_dotenv(usecwd=True))
    args = parse_args(argv)
    # Logs go to stderr. With stdio, stdout carries the protocol and nothing else.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    mcp = create_demo_server() if args.demo else create_live_server()
    logging.info("data source: %s", "demo fixtures" if args.demo else "live providers")

    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
