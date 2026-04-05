from __future__ import annotations

from codegraph.core.graph import CodeGraph
from codegraph.core.node import FunctionNode, Language, NodeType
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
    g = CodeGraph(
        repo="r",
        repo_root="/",
        git_hash="h",
        nodes=[n],
        language_summary={},
        parse_errors=[],
        parsed_at="t",
    )
    G = NetworkXExporter().export(g)
    assert G.number_of_nodes() == 1
