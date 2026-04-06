from __future__ import annotations

from codegraph.core.graph import CodeGraph
from codegraph.core.node import FunctionNode, Language, NodeType
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

    slim = JsonExporter().export(g, mode="graph", include_code=False)
    node = slim["nodes"]["f1"]
    assert "edge_count" in node and node["edge_count"] == 0
    assert "code_str" not in node
