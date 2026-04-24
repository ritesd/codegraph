"""MCP tool implementations backed by GraphBuilder and SQLiteStore."""

from __future__ import annotations

import fnmatch
import os
from collections import defaultdict, deque
from typing import Any

from mcp.server.fastmcp import FastMCP

from codegraph.config import CONFIG, load_config
from codegraph.core.graph import CodeGraph, GraphBuilder
from codegraph.core.node import EdgeType
from codegraph.output.json_exporter import JsonExporter
from codegraph.output.networkx_exporter import NetworkXExporter
from codegraph.storage.sqlite_store import SQLiteStore


def _node_dict(node: Any, include_code: bool = False) -> dict[str, Any]:
    if include_code:
        return node.to_dict()
    return node.to_slim_dict()


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


def _node_touches_changed_file(node_file: str, changed_files: list[str]) -> bool:
    """Match stored node paths to user-supplied changed paths (relative or absolute)."""
    nf = node_file.replace("\\", "/")
    for raw in changed_files:
        cf = raw.replace("\\", "/").strip()
        if not cf:
            continue
        if cf == nf or cf in nf:
            return True
        # suffix match: e.g. "src/foo.py" matches ".../repo/src/foo.py"
        if nf.endswith(cf) or nf.endswith("/" + cf.lstrip("/")):
            return True
        try:
            if os.path.abspath(cf) == os.path.abspath(nf):
                return True
        except OSError:
            pass
    return False


def register_tools(mcp: FastMCP) -> None:
    """Attach all CodeGraph tools to the FastMCP instance."""

    @mcp.tool()
    def parse_repo(repo_path: str, mode: str = "full") -> dict:
        """Parse a repository folder and store the graph. mode: full or incremental."""
        return _parse_summary(repo_path, mode)

    @mcp.tool()
    def get_node(
        node_id: str = "",
        name: str = "",
        repo: str = "",
        include_code: bool = False,
    ) -> dict:
        """Fetch a single node by id or by name+repo. Default: slim payload; set include_code=true for full node + code_str."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        if node_id:
            n = store.get_node(node_id)
            if n:
                return _node_dict(n, include_code)
        if name and repo:
            found = store.get_by_name(name, repo)
            if found:
                return _node_dict(found[0], include_code)
        return {"error": "not found"}

    @mcp.tool()
    def get_neighbors(
        node_id: str,
        edge_types: list[str] | None = None,
        min_confidence: float = 0.0,
        include_code: bool = False,
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
                neighbors.append({"node": _node_dict(tgt, include_code), "edge": e.to_dict()})
        return {"node": _node_dict(node, include_code), "neighbors": neighbors}

    @mcp.tool()
    def search_nodes(
        repo: str,
        node_type: str = "",
        name_pattern: str = "",
        file_path: str = "",
        language: str = "",
        limit: int = 50,
        offset: int = 0,
        include_code: bool = False,
    ) -> dict:
        """Filter nodes by substring name, type, file, language. Paginated slim results by default."""
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
            out.append(_node_dict(n, include_code))
        total = len(out)
        page = out[offset : offset + limit]
        return {"nodes": page, "total": total, "limit": limit, "offset": offset}

    @mcp.tool()
    def get_class_tree(class_node_id: str, include_code: bool = False) -> dict:
        """Return class node and direct method children."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        cls = store.get_node(class_node_id)
        if cls is None:
            return {"error": "not found"}
        methods = [
            _node_dict(m, include_code)
            for m in store.get_by_repo(cls.repo)
            if m.parent_id == class_node_id
        ]
        return {"class": _node_dict(cls, include_code), "methods": methods}

    @mcp.tool()
    def export_graph(
        repo: str,
        fmt: str = "json",
        json_mode: str = "graph",
        max_nodes: int = 5000,
        include_code: bool = False,
        readable: bool = True,
    ) -> dict:
        """Export stored graph as JSON dict or NetworkX node-link structure. Capped at max_nodes; slim nodes unless include_code=true. When readable=true, nodes include label/display_name and edges include provenance (EXTRACTED/INFERRED/AMBIGUOUS)."""
        store = SQLiteStore(CONFIG.sqlite_path)
        nodes = store.get_by_repo(repo)
        if len(nodes) > max_nodes:
            return {
                "error": "too_large",
                "node_count": len(nodes),
                "max_nodes": max_nodes,
                "hint": "Use search_nodes or get_neighbors for targeted queries",
            }
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
            return JsonExporter().export(
                cg, mode=json_mode, include_code=include_code, readable=readable
            )
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
        include_code: bool = False,
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
            chain.append({"depth": depth, "node": _node_dict(n, include_code), "edge": None})
            for e in n.edges:
                if e.confidence < min_confidence:
                    continue
                if direction == "downstream" and e.edge_type == EdgeType.CALLS:
                    stack.append((e.target_id, depth + 1))
                elif direction == "upstream" and e.edge_type == EdgeType.CALLED_BY:
                    stack.append((e.target_id, depth + 1))
        return {"root": node_id, "chain": chain}

    @mcp.tool()
    def get_nodes_by_id(
        node_ids: list[str],
        include_code: bool = False,
    ) -> list[dict]:
        """Fetch multiple nodes by ID in a single call."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        out: list[dict] = []
        for nid in node_ids:
            n = store.get_node(nid)
            if n:
                out.append(_node_dict(n, include_code))
        return out

    @mcp.tool()
    def get_change_impact(
        repo: str,
        changed_files: list[str],
        max_depth: int = 2,
        min_confidence: float = 0.5,
        include_code: bool = False,
    ) -> dict:
        """Compute blast radius: nodes affected by changes to the given files (callers, subclasses, importers)."""
        store = SQLiteStore(CONFIG.sqlite_path)
        store.init_db()
        nodes = store.get_by_repo(repo)
        if not nodes:
            return {
                "changed_nodes": [],
                "impacted_nodes": [],
                "summary": {
                    "changed_file_count": len(changed_files),
                    "changed_node_count": 0,
                    "impacted_node_count": 0,
                    "max_depth_used": 0,
                },
            }

        by_id = {n.id: n for n in nodes}
        changed_ids: set[str] = set()
        for n in nodes:
            if _node_touches_changed_file(n.file_path, changed_files):
                changed_ids.add(n.id)

        inherits_children: dict[str, list[str]] = defaultdict(list)
        imports_importers: dict[str, list[str]] = defaultdict(list)
        for n in nodes:
            for e in n.edges:
                if e.edge_type == EdgeType.INHERITS and e.confidence >= min_confidence:
                    inherits_children[e.target_id].append(n.id)
                if e.edge_type == EdgeType.IMPORTS and e.confidence >= min_confidence:
                    imports_importers[e.target_id].append(n.id)

        dist: dict[str, int] = {cid: 0 for cid in changed_ids}
        q: deque[str] = deque(changed_ids)

        while q:
            nid = q.popleft()
            d = dist[nid]
            if d >= max_depth:
                continue
            n = by_id.get(nid)
            if n is None:
                continue
            next_d = d + 1

            for e in n.edges:
                if e.confidence < min_confidence:
                    continue
                if e.edge_type == EdgeType.CALLED_BY:
                    tid = e.target_id
                    if tid not in dist or next_d < dist[tid]:
                        dist[tid] = next_d
                        q.append(tid)

            for tid in inherits_children.get(nid, ()):
                if tid not in dist or next_d < dist[tid]:
                    dist[tid] = next_d
                    q.append(tid)

            for tid in imports_importers.get(nid, ()):
                if tid not in dist or next_d < dist[tid]:
                    dist[tid] = next_d
                    q.append(tid)

        impacted_only_sorted = sorted(nid for nid, d in dist.items() if nid not in changed_ids and d > 0)
        max_depth_used = max((dist[nid] for nid in impacted_only_sorted), default=0)

        changed_nodes = [_node_dict(by_id[i], include_code) for i in sorted(changed_ids) if i in by_id]
        impacted_nodes = [_node_dict(by_id[i], include_code) for i in impacted_only_sorted if i in by_id]

        unique_files = {f for f in changed_files if f.strip()}
        return {
            "changed_nodes": changed_nodes,
            "impacted_nodes": impacted_nodes,
            "summary": {
                "changed_file_count": len(unique_files) if unique_files else len(changed_files),
                "changed_node_count": len(changed_ids),
                "impacted_node_count": len(impacted_only_sorted),
                "max_depth_used": max_depth_used,
            },
        }
