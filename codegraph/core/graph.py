"""Orchestrates parsing, resolution, and CodeGraph construction.

Loads optional SQLite for incremental mode. Does not start network servers.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from codegraph.config import CodeGraphConfig
from codegraph.core.node import BaseNode, NodeType
from codegraph.core.parser_base import ImportRecord
from codegraph.parsers.go_parser import GoParser
from codegraph.parsers.java_parser import JavaParser
from codegraph.parsers.js_ts_parser import JsTsParser
from codegraph.parsers.python_parser import PythonParser
from codegraph.parsers.registry import EXTENSION_MAP, ParserRegistry
from codegraph.resolver.edge_resolver import EdgeResolver
from codegraph.storage.sqlite_store import SQLiteStore

log = logging.getLogger("codegraph")

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "build", "dist"}


@dataclass
class CodeGraph:
    repo: str
    repo_root: str
    git_hash: str
    nodes: list[BaseNode]
    language_summary: dict[str, int]
    parse_errors: list[dict]
    parsed_at: str

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_by_name(self, name: str) -> list[BaseNode]:
        return [n for n in self.nodes if n.name == name]

    def get_by_file(self, file_path: str) -> list[BaseNode]:
        ap = os.path.abspath(file_path)
        return [n for n in self.nodes if os.path.abspath(n.file_path) == ap]

    def get_by_type(self, node_type: NodeType) -> list[BaseNode]:
        return [n for n in self.nodes if n.node_type == node_type]

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "repo_root": self.repo_root,
            "git_hash": self.git_hash,
            "parsed_at": self.parsed_at,
            "language_summary": dict(self.language_summary),
            "parse_errors": list(self.parse_errors),
            "nodes": [n.to_dict() for n in self.nodes],
        }


class GraphBuilder:
    """Walk a repository, parse files, resolve edges, optionally persist."""

    def __init__(self, config: CodeGraphConfig) -> None:
        self.config = config
        self.registry = ParserRegistry()
        for p in (PythonParser(), JsTsParser(), GoParser(), JavaParser()):
            self.registry.register(p)

    def build(self, repo_root: str, mode: str = "full") -> CodeGraph:
        repo_root = os.path.abspath(repo_root)
        repo_name = os.path.basename(repo_root.rstrip(os.sep)) or repo_root
        gh = self._get_git_hash(repo_root)
        parsed_at = datetime.now(timezone.utc).isoformat()
        errors: list[dict] = []
        all_nodes: list[BaseNode] = []
        all_imports: list[ImportRecord] = []

        if mode == "incremental":
            store = SQLiteStore(self.config.sqlite_path)
            store.init_db()
            existing = store.get_by_repo(repo_name)
            changed_paths = [os.path.abspath(p) for p in self._get_changed_files(repo_root)]
            changed = set(changed_paths)
            for ap in changed_paths:
                store.delete_by_file(repo_name, ap)
            kept = [n for n in existing if os.path.abspath(n.file_path) not in changed]
            all_nodes.extend(kept)
            files_to_parse = [p for p in self._walk_repo(repo_root) if os.path.abspath(p) in changed]
        else:
            files_to_parse = self._walk_repo(repo_root)

        for fp in files_to_parse:
            language = self.registry.detect_language(fp)
            parser = self.registry.get_parser(fp)
            if parser is None:
                continue
            try:
                nodes = self.registry.parse_file(fp, repo_name, gh)
                for n in nodes:
                    n.repo = repo_name
                    if not n.git_hash:
                        n.git_hash = gh
                all_nodes.extend(nodes)
                all_imports.extend(parser.extract_imports(fp))
            except Exception as ex:  # noqa: BLE001
                log.warning("Parse error %s: %s", fp, ex)
                errors.append({"file": fp, "error": str(ex), "traceback": ""})

        resolver = EdgeResolver(all_nodes, repo_root, all_imports)
        resolver.resolve()

        lang_summary: dict[str, int] = {}
        for n in all_nodes:
            lang_summary[n.language.value.lower()] = lang_summary.get(n.language.value.lower(), 0) + 1

        cg = CodeGraph(
            repo=repo_name,
            repo_root=repo_root,
            git_hash=gh,
            nodes=all_nodes,
            language_summary=lang_summary,
            parse_errors=errors,
            parsed_at=parsed_at,
        )

        store = SQLiteStore(self.config.sqlite_path)
        store.init_db()
        store.upsert_many(all_nodes)
        return cg

    def _get_git_hash(self, repo_root: str) -> str:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return out.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return "unknown"

    def _get_changed_files(self, repo_root: str) -> list[str]:
        try:
            out = subprocess.run(
                ["git", "diff", "HEAD~1", "--name-only"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            paths = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
            return [os.path.join(repo_root, p) for p in paths]
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return []

    def _walk_repo(self, repo_root: str) -> list[str]:
        out: list[str] = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                _, ext = os.path.splitext(fn)
                if ext.lower() not in EXTENSION_MAP:
                    continue
                try:
                    if os.path.getsize(fp) > self.config.max_file_size_kb * 1024:
                        log.warning("Skipping large file %s", fp)
                        continue
                except OSError:
                    continue
                out.append(fp)
        return out
