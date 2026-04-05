"""MCP tool implementations backed by GraphBuilder and SQLiteStore."""

from __future__ import annotations

import fnmatch
from typing import Any

from mcp.server.fastmcp import FastMCP

from codegraph.config import CONFIG, load_config
from codegraph.core.graph import CodeGraph, GraphBuilder
from codegraph.core.node import EdgeType
from codegraph.output.json_exporter import JsonExporter
from codegraph.output.networkx_exporter import NetworkXExporter
from codegraph.storage.sqlite_store import SQLiteStore


def _parse_summary(repo_path: str, mode: str) -> dict[str, Any]:
    cfg = load_config()
    gb = GraphBuilder(cfg)
    g = gb.build(repo_path, mode=mode)
    edge_count = sum(len(n.edges) for n in g.nodes)
    return {
        "repo": g.repo,
        "node_count": len(g.nodes),
        "edge_count": edge_count,
        "language_summary": g.language_summary,
        "parse_errors": g.parse_errors,
        "git_hash": g.git_hash,
    }


def register_tools(mcp: FastMCP) -> None:
    """Attach all CodeGraph tools to the FastMCP instance."""

    @mcp.tool()
    def parse_repo(repo_path: str, mode: str = "full") -> dict:
        """Parse a repository folder and store the graph. mode: full or incremental."""
        return _parse_summary(repo_path, mode)

    @mcp.tool()
    def get_node(node_id: str = "", name: str = "", repo: str = "") -> dict:
        """Fetch a single node by id or by name+repo."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        if node_id:
            n = store.get_node(node_id)
            if n:
                return n.to_dict()
        if name and repo:
            found = store.get_by_name(name, repo)
            if found:
                return found[0].to_dict()
        return {"error": "not found"}

    @mcp.tool()
    def get_neighbors(
        node_id: str,
        edge_types: list[str] | None = None,
        min_confidence: float = 0.0,
    ) -> dict:
        """Neighbors of a node with optional edge type and confidence filters."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        node = store.get_node(node_id)
        if node is None:
            return {"error": "not found"}
        want: set[str] | None = set(edge_types) if edge_types else None
        neighbors: list[dict] = []
        for e in node.edges:
            if want and e.edge_type.value not in want:
                continue
            if e.confidence < min_confidence:
                continue
            tgt = store.get_node(e.target_id)
            if tgt:
                neighbors.append({"node": tgt.to_dict(), "edge": e.to_dict()})
        return {"node": node.to_dict(), "neighbors": neighbors}

    @mcp.tool()
    def search_nodes(
        repo: str,
        node_type: str = "",
        name_pattern: str = "",
        file_path: str = "",
        language: str = "",
    ) -> list[dict]:
        """Filter nodes by substring name, type, file, language."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        nodes = store.get_by_repo(repo)
        out: list[dict] = []
        np = name_pattern.lower()
        for n in nodes:
            if node_type and n.node_type.value != node_type:
                continue
            if language and n.language.value != language:
                continue
            if file_path and file_path not in n.file_path:
                continue
            if np and np not in n.name.lower() and not fnmatch.fnmatch(n.name.lower(), np):
                continue
            out.append(n.to_dict())
        return out

    @mcp.tool()
    def get_class_tree(class_node_id: str) -> dict:
        """Return class node and direct method children."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        cls = store.get_node(class_node_id)
        if cls is None:
            return {"error": "not found"}
        methods = [m.to_dict() for m in store.get_by_repo(cls.repo) if m.parent_id == class_node_id]
        return {"class": cls.to_dict(), "methods": methods}

    @mcp.tool()
    def export_graph(repo: str, fmt: str = "json", json_mode: str = "graph") -> dict:
        """Export stored graph as JSON dict or NetworkX node-link structure."""
        store = SQLiteStore(CONFIG.sqlite_path)
        nodes = store.get_by_repo(repo)
        cg = CodeGraph(
            repo=repo,
            repo_root="",
            git_hash="",
            nodes=nodes,
            language_summary={},
            parse_errors=[],
            parsed_at="",
        )
        if fmt == "json":
            return JsonExporter().export(cg, mode=json_mode)
        G = NetworkXExporter().export(cg)
        import networkx as nx  # noqa: PLC0415

        return {"node_link_data": nx.node_link_data(G)}

    @mcp.tool()
    def incremental_update(repo_path: str) -> dict:
        """Re-parse git-diff changed files only."""
        return _parse_summary(repo_path, "incremental")

    @mcp.tool()
    def list_repos() -> list[str]:
        """Stored repository names."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        return store.list_repos()

    @mcp.tool()
    def get_call_chain(
        node_id: str,
        direction: str = "downstream",
        max_depth: int = 5,
        min_confidence: float = 0.5,
    ) -> dict:
        """Traverse call graph up or down from node_id."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        root = store.get_node(node_id)
        if root is None:
            return {"error": "not found"}
        chain: list[dict] = []
        visited: set[str] = set()
        stack: list[tuple[str, int]] = [(node_id, 0)]

        while stack:
            nid, depth = stack.pop()
            if depth > max_depth or nid in visited:
                continue
            visited.add(nid)
            n = store.get_node(nid)
            if n is None:
                continue
            chain.append({"depth": depth, "node": n.to_dict(), "edge": None})
            for e in n.edges:
                if e.confidence < min_confidence:
                    continue
                if direction == "downstream" and e.edge_type == EdgeType.CALLS:
                    stack.append((e.target_id, depth + 1))
                elif direction == "upstream" and e.edge_type == EdgeType.CALLED_BY:
                    stack.append((e.target_id, depth + 1))
        return {"root": node_id, "chain": chain}
