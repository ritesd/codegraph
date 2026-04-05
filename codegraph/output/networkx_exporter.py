"""Export CodeGraph to NetworkX DiGraph (optional dependency)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from codegraph.core.graph import CodeGraph

if TYPE_CHECKING:
    import networkx as nx


_GEXF_SAFE = (str, int, float, bool)


class NetworkXExporter:
    """Build a directed graph with node and edge attributes."""

    @staticmethod
    def _sanitize(attrs: dict[str, Any]) -> dict[str, Any]:
        """Keep only GEXF-safe scalar values; drop None, lists, dicts."""
        return {k: v for k, v in attrs.items() if isinstance(v, _GEXF_SAFE)}

    def export(self, graph: CodeGraph) -> Any:
        import networkx as nx  # noqa: PLC0415 — lazy import

        G = nx.DiGraph()
        for n in graph.nodes:
            G.add_node(n.id, **self._sanitize(n.to_dict()))
        for n in graph.nodes:
            for e in n.edges:
                G.add_edge(
                    n.id,
                    e.target_id,
                    edge_type=e.edge_type.value,
                    confidence=e.confidence,
                    resolved=e.resolved,
                )
        return G

    def to_file(self, graph: CodeGraph, output_path: str, fmt: str = "gexf") -> None:
        G = self.export(graph)
        import networkx as nx  # noqa: PLC0415

        parent = os.path.dirname(os.path.abspath(output_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        if fmt == "gexf":
            nx.write_gexf(G, output_path)
        elif fmt == "graphml":
            nx.write_graphml(G, output_path)
        elif fmt == "json":
            data = nx.node_link_data(G)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
