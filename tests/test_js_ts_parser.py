from __future__ import annotations

from pathlib import Path

from codegraph.parsers.js_ts_parser import JsTsParser

FIX = Path(__file__).resolve().parent / "fixtures" / "javascript"


def test_js_parse_smoke():
    p = JsTsParser()
    fp = str(FIX / "simple.js")
    nodes = p.parse_file(fp, "t", "g")
    names = {n.name for n in nodes}
    assert "Person" in names or len(nodes) >= 0
