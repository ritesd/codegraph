from __future__ import annotations

from pathlib import Path

from codegraph.parsers.go_parser import GoParser

FIX = Path(__file__).resolve().parent / "fixtures" / "go"


def test_go_parse_smoke():
    p = GoParser()
    fp = str(FIX / "simple.go")
    nodes = p.parse_file(fp, "t", "g")
    assert any(n.name == "Point" for n in nodes)
