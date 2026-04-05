"""Standalone MCP server for CodeGraph."""

from __future__ import annotations

import argparse
import logging

from mcp.server.fastmcp import FastMCP

from codegraph.config import CONFIG
from codegraph.mcp.tools import register_tools

log = logging.getLogger("codegraph")

TRANSPORTS = ("stdio", "sse", "streamable-http")


def create_app(host: str, port: int) -> FastMCP:
    app = FastMCP("codegraph", host=host, port=port)
    register_tools(app)
    return app


def main(
    host: str | None = None,
    port: int | None = None,
    transport: str | None = None,
) -> None:
    logging.basicConfig(level=logging.INFO)
    h = host or CONFIG.mcp_host
    p = port or CONFIG.mcp_port
    t = transport or CONFIG.mcp_transport
    if t not in TRANSPORTS:
        raise SystemExit(f"Unknown transport {t!r}. Choose from {TRANSPORTS}")

    app = create_app(h, p)
    log.info("CodeGraph MCP starting transport=%s host=%s port=%s", t, h, p)
    app.run(transport=t)  # type: ignore[arg-type]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CodeGraph MCP server")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--transport", choices=TRANSPORTS, default=None)
    args = parser.parse_args()
    main(host=args.host, port=args.port, transport=args.transport)
