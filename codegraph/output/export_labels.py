"""Human-readable labels for graph exports (Gephi, JSON, MCP)."""

from __future__ import annotations

import os
from typing import Any

from codegraph.core.node import BaseNode


def node_display_name(node: BaseNode) -> str:
    """Short location-qualified name for humans and LLMs."""
    base = os.path.basename(node.file_path) if node.file_path else ""
    if base and node.line_start:
        return f"{node.name} — {base}:{node.line_start}"
    if base:
        return f"{node.name} — {base}"
    return node.name


def node_export_attrs(node: BaseNode, *, include_code: bool) -> dict[str, Any]:
    """Build node dict for export: slim or full plus label/display_name."""
    d = node.to_dict() if include_code else node.to_slim_dict()
    d["label"] = node.name
    d["display_name"] = node_display_name(node)
    return d


def edge_export_dict(
    source_id: str,
    target_id: str,
    edge_type: str,
    confidence: float,
    resolved: bool,
    *,
    include_provenance: bool,
) -> dict[str, Any]:
    from codegraph.output.edge_provenance import edge_provenance

    out: dict[str, Any] = {
        "source": source_id,
        "target": target_id,
        "type": edge_type,
        "confidence": confidence,
        "resolved": resolved,
    }
    if include_provenance:
        out["provenance"] = edge_provenance(confidence)
    return out
