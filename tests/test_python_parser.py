from __future__ import annotations

from pathlib import Path

from codegraph.core.node import EdgeType, NodeType
from codegraph.parsers.python_parser import PythonParser

FIX = Path(__file__).resolve().parent / "fixtures" / "python"


def test_simple_class_and_methods():
    p = PythonParser()
    fp = str(FIX / "simple.py")
    nodes = {n.name: n for n in p.parse_file(fp, "t", "g")}
    assert "Greeter" in nodes
    assert nodes["Greeter"].node_type == NodeType.CLASS
    greet = nodes["greet"]
    assert greet.node_type == NodeType.METHOD
    assert any(p.name == "name" for p in greet.params)
    hf = nodes["helper_format"]
    assert hf.return_type is not None


def test_call_edges_unresolved_prefix():
    p = PythonParser()
    fp = str(FIX / "simple.py")
    nodes = {n.name: n for n in p.parse_file(fp, "t", "g")}
    greet = nodes["greet"]
    targets = [e.target_id for e in greet.edges if e.edge_type == EdgeType.CALLS]
    assert any(t.startswith("unresolved::") for t in targets)


def test_import_records():
    p = PythonParser()
    fp = str(FIX / "simple.py")
    recs = p.extract_imports(fp)
    assert isinstance(recs, list)


def test_async_metadata():
    src = FIX / "async_fix.py"
    src.write_text(
        "async def foo():\n    await bar()\n",
        encoding="utf-8",
    )
    try:
        p = PythonParser()
        nodes = p.parse_file(str(src), "t", "g")
        assert any(getattr(n, "metadata", {}).get("is_async") for n in nodes)
    finally:
        src.unlink(missing_ok=True)


def test_star_import():
    src = FIX / "star.py"
    src.write_text("from os import *\n", encoding="utf-8")
    try:
        p = PythonParser()
        recs = p.extract_imports(str(src))
        assert any("*" in r.symbols for r in recs)
    finally:
        src.unlink(missing_ok=True)
