from __future__ import annotations

from codegraph.core.graph import CodeGraph
from codegraph.core.node import Edge, EdgeType, FunctionNode, Language, NodeType
from codegraph.output.json_exporter import JsonExporter


def test_json_export_graph_mode():
    n = FunctionNode(
        id="f1",
        name="f",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path="/x.py",
        repo="r",
        git_hash="h",
    )
    n.edges = [
        Edge(target_id="ext1", edge_type=EdgeType.CALLS, confidence=1.0, resolved=True),
    ]
    g = CodeGraph(
        repo="r",
        repo_root="/",
        git_hash="h",
        nodes=[n],
        language_summary={"python": 1},
        parse_errors=[],
        parsed_at="t",
    )
    d = JsonExporter().export(g, mode="graph")
    assert "nodes" in d and isinstance(d["nodes"], dict)
    assert d["meta"]["node_count"] == 1
    assert d["meta"].get("export_readable") is True
    assert d["nodes"]["f1"]["label"] == "f"
    assert "display_name" in d["nodes"]["f1"]
    assert len(d["edges"]) == 1
    assert d["edges"][0]["provenance"] == "EXTRACTED"

    slim = JsonExporter().export(g, mode="graph", include_code=False)
    node = slim["nodes"]["f1"]
    assert "edge_count" in node and node["edge_count"] == 1
    assert "code_str" not in node
    assert node["label"] == "f"

    raw = JsonExporter().export(g, mode="graph", include_code=False, readable=False)
    assert "provenance" not in raw["edges"][0]
    assert raw["meta"].get("export_readable") is False
