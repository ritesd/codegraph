from __future__ import annotations

from pathlib import Path

from codegraph.core.node import ClassNode, Edge, EdgeType, FunctionNode, Language, MethodNode, NodeType
from codegraph.core.parser_base import ImportRecord
from codegraph.resolver.edge_resolver import EdgeResolver


def test_resolves_internal_call():
    repo = Path(__file__).resolve().parent / "fixtures" / "python"
    callee = FunctionNode(
        id="callee",
        name="helper_format",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path=str(repo / "simple.py"),
        repo="t",
        git_hash="g",
    )
    caller = MethodNode(
        id="caller",
        name="greet",
        node_type=NodeType.METHOD,
        language=Language.PYTHON,
        file_path=str(repo / "simple.py"),
        repo="t",
        git_hash="g",
        parent_id="cl",
        edges=[
            Edge("unresolved::helper_format", EdgeType.CALLS, 1.0, False),
        ],
    )
    cls = ClassNode(
        id="cl",
        name="Greeter",
        node_type=NodeType.CLASS,
        language=Language.PYTHON,
        file_path=str(repo / "simple.py"),
        repo="t",
        git_hash="g",
    )
    imports: list[ImportRecord] = []
    nodes = [cls, caller, callee]
    er = EdgeResolver(nodes, str(repo), imports)
    er.resolve()
    resolved = [e for e in caller.edges if e.edge_type == EdgeType.CALLS and e.resolved]
    assert resolved and resolved[0].target_id == "callee"


def test_called_by_reverse_edge():
    repo = Path(__file__).resolve().parent / "fixtures" / "python"
    fi = str(repo / "simple.py")
    a = FunctionNode(
        id="a",
        name="a",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path=fi,
        repo="t",
        git_hash="g",
        edges=[Edge("unresolved::b", EdgeType.CALLS, 1.0, False)],
    )
    b = FunctionNode(
        id="b",
        name="b",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path=fi,
        repo="t",
        git_hash="g",
    )
    EdgeResolver([a, b], str(repo), []).resolve()
    back = [e for e in b.edges if e.edge_type == EdgeType.CALLED_BY]
    assert back and back[0].target_id == "a"
