"""SQLite persistence for CodeGraph nodes using JSON blobs."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from codegraph.core.node import BaseNode, NodeType, make_node

log = logging.getLogger("codegraph")


DDL = """
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    node_type   TEXT NOT NULL,
    language    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    repo        TEXT NOT NULL,
    git_hash    TEXT NOT NULL,
    parent_id   TEXT,
    line_start  INTEGER,
    line_end    INTEGER,
    parsed_at   TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repo ON nodes(repo);
CREATE INDEX IF NOT EXISTS idx_file ON nodes(repo, file_path);
CREATE INDEX IF NOT EXISTS idx_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_parent ON nodes(parent_id);
"""


class SQLiteStore:
    """CRUD for nodes in SQLite."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(DDL)

    def upsert_node(self, node: BaseNode) -> None:
        self.upsert_many([node])

    def upsert_many(self, nodes: list[BaseNode]) -> None:
        if not nodes:
            return
        now = datetime.now(timezone.utc).isoformat()
        rows: list[tuple] = []
        for n in nodes:
            d = n.to_dict()
            blob = json.dumps(d)
            rows.append(
                (
                    n.id,
                    n.name,
                    n.node_type.value,
                    n.language.value,
                    n.file_path,
                    n.repo,
                    n.git_hash,
                    n.parent_id,
                    n.line_start,
                    n.line_end,
                    now,
                    blob,
                )
            )
        with self._lock, self._conn() as conn:
            conn.execute("BEGIN")
            try:
                conn.executemany(
                    """INSERT OR REPLACE INTO nodes
                    (id, name, node_type, language, file_path, repo, git_hash,
                     parent_id, line_start, line_end, parsed_at, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _deserialize_row(self, row: sqlite3.Row) -> BaseNode:
        data = json.loads(row["data"])
        nt = NodeType(data.pop("node_type"))
        return make_node(nt, **data)

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        with self._lock, self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
            r = cur.fetchone()
            if r is None:
                return None
            return self._deserialize_row(r)

    def get_by_repo(self, repo: str) -> list[BaseNode]:
        with self._lock, self._conn() as conn:
            cur = conn.execute("SELECT * FROM nodes WHERE repo = ?", (repo,))
            return [self._deserialize_row(r) for r in cur.fetchall()]

    def get_by_file(self, repo: str, file_path: str) -> list[BaseNode]:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM nodes WHERE repo = ? AND file_path = ?",
                (repo, file_path),
            )
            return [self._deserialize_row(r) for r in cur.fetchall()]

    def get_by_name(self, name: str, repo: Optional[str] = None) -> list[BaseNode]:
        with self._lock, self._conn() as conn:
            if repo:
                cur = conn.execute(
                    "SELECT * FROM nodes WHERE name = ? AND repo = ?",
                    (name, repo),
                )
            else:
                cur = conn.execute("SELECT * FROM nodes WHERE name = ?", (name,))
            return [self._deserialize_row(r) for r in cur.fetchall()]

    def get_by_type(self, node_type: NodeType, repo: Optional[str] = None) -> list[BaseNode]:
        with self._lock, self._conn() as conn:
            nt = node_type.value
            if repo:
                cur = conn.execute(
                    "SELECT * FROM nodes WHERE node_type = ? AND repo = ?",
                    (nt, repo),
                )
            else:
                cur = conn.execute("SELECT * FROM nodes WHERE node_type = ?", (nt,))
            return [self._deserialize_row(r) for r in cur.fetchall()]

    def delete_by_file(self, repo: str, file_path: str) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM nodes WHERE repo = ? AND file_path = ?",
                (repo, file_path),
            )
            return cur.rowcount

    def delete_by_repo(self, repo: str) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM nodes WHERE repo = ?", (repo,))
            return cur.rowcount

    def list_repos(self) -> list[str]:
        with self._lock, self._conn() as conn:
            cur = conn.execute("SELECT DISTINCT repo FROM nodes ORDER BY repo")
            return [r[0] for r in cur.fetchall()]

    def node_count(self, repo: Optional[str] = None) -> int:
        with self._lock, self._conn() as conn:
            if repo:
                cur = conn.execute("SELECT COUNT(*) FROM nodes WHERE repo = ?", (repo,))
            else:
                cur = conn.execute("SELECT COUNT(*) FROM nodes")
            return int(cur.fetchone()[0])
