from __future__ import annotations

from codegraph.core.node import (
    ClassNode,
    Edge,
    EdgeType,
    FunctionNode,
    Language,
    MethodNode,
    NodeType,
    Param,
    make_node,
)


def test_make_node_roundtrip_class():
    c = ClassNode(
        id="1",
        name="C",
        node_type=NodeType.CLASS,
        language=Language.PYTHON,
        file_path="/x.py",
        repo="r",
        git_hash="h",
        bases=["object"],
    )
    d = c.to_dict()
    nt = NodeType(d.pop("node_type"))
    c2 = make_node(nt, **d)
    assert isinstance(c2, ClassNode)
    assert c2.name == "C"


def test_make_node_function():
    f = FunctionNode(
        id="2",
        name="f",
        node_type=NodeType.FUNCTION,
        language=Language.PYTHON,
        file_path="/x.py",
        repo="r",
        git_hash="h",
        params=[Param(name="a", annotation="int")],
    )
    d = f.to_dict()
    nt = NodeType(d.pop("node_type"))
    f2 = make_node(nt, **d)
    assert isinstance(f2, FunctionNode)
    assert f2.params[0].name == "a"


def test_edge_to_dict():
    e = Edge(target_id="z", edge_type=EdgeType.CALLS, confidence=0.5, resolved=True)
    e2 = Edge.from_dict(e.to_dict())
    assert e2.target_id == "z"
    assert e2.edge_type == EdgeType.CALLS
