"""Command line entry point: pick the data source and the transport, then serve."""

import argparse
import logging
import os
import sys

from fieldsat.runtime import FIELDS_FILE_VARIABLE, create_demo_server, create_live_server


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
    parser.add_argument(
        "--fields",
        metavar="PATH",
        default=os.environ.get(FIELDS_FILE_VARIABLE) or None,
        help="GeoJSON file of fields to serve instead of the built-in ones (live and demo).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    # Logs go to stderr. With stdio, stdout carries the protocol and nothing else.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
    if args.demo:
        mcp = create_demo_server(fields_file=args.fields)
    else:
        mcp = create_live_server(fields_file=args.fields)
    logging.info("data source: %s", "demo fixtures" if args.demo else "live providers")
    logging.info("fields: %s", args.fields or "built-in registry")

    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
