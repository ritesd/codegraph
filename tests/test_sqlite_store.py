from __future__ import annotations

import tempfile
from pathlib import Path

from codegraph.core.graph import GraphBuilder
from codegraph.core.node import ClassNode, Language, NodeType
from codegraph.storage.sqlite_store import SQLiteStore
from codegraph.config import load_config


def test_sqlite_roundtrip_all_types():
    cfg = load_config()
    db = tempfile.mktemp(suffix=".db")
    cfg = type(cfg)(**{**cfg.__dict__, "sqlite_path": db})
    root = Path(__file__).resolve().parent / "fixtures" / "python"
    gb = GraphBuilder(cfg)
    g = gb.build(str(root))
    store = SQLiteStore(db)
    for n in g.nodes:
        got = store.get_node(n.id)
        assert got is not None
        assert got.name == n.name


def test_delete_by_file():
    cfg = load_config()
    db = tempfile.mktemp(suffix=".db")
    store = SQLiteStore(db)
    store.init_db()
    n = ClassNode(
        id="c1",
        name="C",
        node_type=NodeType.CLASS,
        language=Language.PYTHON,
        file_path="/a.py",
        repo="r",
        git_hash="h",
    )
    store.upsert_node(n)
    assert store.delete_by_file("r", "/a.py") >= 1
    assert store.get_node("c1") is None
