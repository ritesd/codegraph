"""Export CodeGraph to JSON (flat or adjacency graph)."""

from __future__ import annotations

import json
import os
from typing import Any

from codegraph.core.graph import CodeGraph
from codegraph.output.export_labels import edge_export_dict, node_export_attrs


class JsonExporter:
    """Serialize CodeGraph to dict / file."""

    def export(
        self,
        graph: CodeGraph,
        mode: str = "graph",
        *,
        include_code: bool = True,
        readable: bool = True,
    ) -> dict[str, Any]:
        meta = {
            "repo": graph.repo,
            "repo_root": graph.repo_root,
            "git_hash": graph.git_hash,
            "parsed_at": graph.parsed_at,
            "node_count": len(graph.nodes),
            "edge_count": 0,
            "language_summary": dict(graph.language_summary),
            "parse_errors": list(graph.parse_errors),
            "export_readable": readable,
        }
        edges_out: list[dict[str, Any]] = []
        for n in graph.nodes:
            for e in n.edges:
                edges_out.append(
                    edge_export_dict(
                        n.id,
                        e.target_id,
                        e.edge_type.value,
                        e.confidence,
                        e.resolved,
                        include_provenance=readable,
                    )
                )
        meta["edge_count"] = len(edges_out)
        if mode == "flat":
            return {
                "meta": meta,
                "nodes": [node_export_attrs(n, include_code=include_code) for n in graph.nodes],
                "edges": edges_out,
            }
        nodes_map = {n.id: node_export_attrs(n, include_code=include_code) for n in graph.nodes}
        return {"meta": meta, "nodes": nodes_map, "edges": edges_out}

    def to_file(
        self,
        graph: CodeGraph,
        output_path: str,
        mode: str = "graph",
        indent: int = 2,
        *,
        include_code: bool = True,
        readable: bool = True,
    ) -> None:
        d = self.export(graph, mode=mode, include_code=include_code, readable=readable)
        parent = os.path.dirname(os.path.abspath(output_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=indent)
