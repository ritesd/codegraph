from __future__ import annotations

from codegraph.core.graph import CodeGraph
from codegraph.core.node import FunctionNode, Language, NodeType
from codegraph.output.graph_report import generate_graph_report_markdown


def test_graph_report_contains_sections():
    n = FunctionNode(
        id="f1",
        name="hello",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path="/proj/x.py",
        repo="myrepo",
        git_hash="abc",
        line_start=10,
    )
    g = CodeGraph(
        repo="myrepo",
        repo_root="/proj",
        git_hash="abc",
        nodes=[n],
        language_summary={"python": 1},
        parse_errors=[],
        parsed_at="t",
    )
    md = generate_graph_report_markdown(g)
    assert "# CodeGraph report: `myrepo`" in md
    assert "## Hub symbols" in md
    assert "## Suggested MCP queries" in md
    assert "hello" in md
