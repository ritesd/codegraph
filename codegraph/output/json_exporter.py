"""Export CodeGraph to JSON (flat or adjacency graph)."""

from __future__ import annotations

import json
import os
from typing import Any

from codegraph.core.graph import CodeGraph


class JsonExporter:
    """Serialize CodeGraph to dict / file."""

    def export(self, graph: CodeGraph, mode: str = "graph") -> dict[str, Any]:
        meta = {
            "repo": graph.repo,
            "repo_root": graph.repo_root,
            "git_hash": graph.git_hash,
            "parsed_at": graph.parsed_at,
            "node_count": len(graph.nodes),
            "edge_count": 0,
            "language_summary": dict(graph.language_summary),
            "parse_errors": list(graph.parse_errors),
        }
        edges_out: list[dict[str, Any]] = []
        for n in graph.nodes:
            for e in n.edges:
                edges_out.append(
                    {
                        "source": n.id,
                        "target": e.target_id,
                        "type": e.edge_type.value,
                        "confidence": e.confidence,
                        "resolved": e.resolved,
                    }
                )
        meta["edge_count"] = len(edges_out)
        if mode == "flat":
            return {
                "meta": meta,
                "nodes": [n.to_dict() for n in graph.nodes],
            }
        nodes_map = {n.id: n.to_dict() for n in graph.nodes}
        return {"meta": meta, "nodes": nodes_map, "edges": edges_out}

    def to_file(self, graph: CodeGraph, output_path: str, mode: str = "graph", indent: int = 2) -> None:
        d = self.export(graph, mode=mode)
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=indent)
