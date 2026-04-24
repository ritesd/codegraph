"""Export CodeGraph to NetworkX DiGraph (optional dependency)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from codegraph.core.graph import CodeGraph
from codegraph.output.edge_provenance import edge_provenance
from codegraph.output.export_labels import node_display_name

if TYPE_CHECKING:
    import networkx as nx


_GEXF_SAFE = (str, int, float, bool)


class NetworkXExporter:
    """Build a directed graph with node and edge attributes."""

    @staticmethod
    def _sanitize(attrs: dict[str, Any]) -> dict[str, Any]:
        """Keep only GEXF-safe scalar values; drop None, lists, dicts."""
        return {k: v for k, v in attrs.items() if isinstance(v, _GEXF_SAFE) and v is not None}

    def _node_viz_attrs(self, n: Any) -> dict[str, Any]:
        """Scalars for GEXF/Gephi: human label + filters."""
        return {
            "id": n.id,
            "label": n.name,
            "display_name": node_display_name(n),
            "name": n.name,
            "node_type": n.node_type.value,
            "language": n.language.value,
            "file_path": n.file_path or "",
            "repo": n.repo,
            "line_start": int(n.line_start),
            "line_end": int(n.line_end),
        }

    def export(self, graph: CodeGraph) -> Any:
        import networkx as nx  # noqa: PLC0415 — lazy import

        G = nx.DiGraph()
        for n in graph.nodes:
            base = self._sanitize(self._node_viz_attrs(n))
            G.add_node(n.id, **base)
        for n in graph.nodes:
            for e in n.edges:
                G.add_edge(
                    n.id,
                    e.target_id,
                    edge_type=e.edge_type.value,
                    confidence=float(e.confidence),
                    resolved=bool(e.resolved),
                    provenance=edge_provenance(e.confidence),
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
