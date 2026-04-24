from __future__ import annotations

from codegraph.core.graph import CodeGraph
from codegraph.core.node import Edge, EdgeType, ExternalNode, FunctionNode, Language, NodeType
from codegraph.output.networkx_exporter import NetworkXExporter


def test_networkx_export():
    n = FunctionNode(
        id="f1",
        name="f",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path="/x.py",
        repo="r",
        git_hash="h",
    )
    ext = ExternalNode(
        id="ext1",
        name="ext",
        node_type=NodeType.EXTERNAL,
        language=Language.PYTHON,
        file_path="",
        repo="r",
        git_hash="h",
        symbol_name="ext",
    )
    n.edges = [
        Edge(target_id="ext1", edge_type=EdgeType.CALLS, confidence=0.2, resolved=False),
    ]
    g = CodeGraph(
        repo="r",
        repo_root="/",
        git_hash="h",
        nodes=[n, ext],
        language_summary={},
        parse_errors=[],
        parsed_at="t",
    )
    G = NetworkXExporter().export(g)
    assert G.number_of_nodes() == 2
    assert G.nodes["f1"]["label"] == "f"
    assert "display_name" in G.nodes["f1"]
    assert G.number_of_edges() == 1
    assert G.edges["f1", "ext1"]["provenance"] == "AMBIGUOUS"
