from __future__ import annotations

from pathlib import Path

from codegraph.core.node import NodeType
from codegraph.parsers.java_parser import JavaParser

FIX = Path(__file__).resolve().parent / "fixtures" / "java"


def test_java_parse_smoke():
    p = JavaParser()
    fp = str(FIX / "simple.java")
    nodes = p.parse_file(fp, "t", "g")
    assert any(n.name == "Main" for n in nodes)


def test_java_interface_at_file_scope():
    p = JavaParser()
    fp = str(FIX / "simple.java")
    nodes = {n.name: n for n in p.parse_file(fp, "t", "g")}
    assert "Util" in nodes
    util = nodes["Util"]
    assert util.node_type == NodeType.CLASS
    assert util.is_abstract is True
    assert util.metadata.get("java_kind") == "interface"


def test_java_enum_at_file_scope():
    p = JavaParser()
    fp = str(FIX / "simple.java")
    nodes = {n.name: n for n in p.parse_file(fp, "t", "g")}
    assert "Color" in nodes
    color = nodes["Color"]
    assert color.node_type == NodeType.CLASS
    assert color.metadata.get("java_kind") == "enum"
    assert "RED" in color.metadata.get("enum_constants", [])
    assert "lower" in {n.name for n in p.parse_file(fp, "t", "g")}
