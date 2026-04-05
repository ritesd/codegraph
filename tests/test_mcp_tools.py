from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from codegraph.mcp.tools import register_tools


def test_register_tools():
    app = FastMCP("test")
    register_tools(app)

    async def run() -> set[str]:
        tools = await app.list_tools()
        return {t.name for t in tools}

    names = asyncio.run(run())
    assert "parse_repo" in names
    assert "get_node" in names
