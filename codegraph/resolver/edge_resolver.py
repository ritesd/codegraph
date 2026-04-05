"""Resolves unresolved call edges using ImportTracer and a symbol index.

Operates only on in-memory node lists. Does not touch storage.
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from codegraph.core.node import (
    BaseNode,
    ClassNode,
    Edge,
    EdgeType,
    ExternalNode,
    Language,
    MethodNode,
    NodeType,
)
from codegraph.config import CONFIG
from codegraph.core.parser_base import ImportRecord
from codegraph.resolver.import_tracer import ImportTracer

log = logging.getLogger("codegraph")

UNRESOLVED_PREFIX = "unresolved::"


class EdgeResolver:
    """Replace temporary edge targets with real node or external IDs."""

    def __init__(
        self,
        nodes: list[BaseNode],
        repo_root: str,
        all_imports: list[ImportRecord],
    ) -> None:
        self.nodes = nodes
        self.repo_root = os.path.abspath(repo_root)
        self.all_imports = all_imports
        self._externals: dict[tuple[Optional[str], str], str] = {}

    def resolve(self) -> list[BaseNode]:
        symbol_by_file_name: dict[str, list[BaseNode]] = {}
        by_name: dict[str, list[BaseNode]] = {}

        for n in self.nodes:
            key = f"{n.file_path}::{n.name}"
            symbol_by_file_name.setdefault(key, []).append(n)
            by_name.setdefault(n.name, []).append(n)

        tracer = ImportTracer(self.repo_root, self.all_imports)
        tracer.build()

        for node in self.nodes:
            new_edges: list[Edge] = []
            for e in node.edges:
                if not e.target_id.startswith(UNRESOLVED_PREFIX):
                    new_edges.append(e)
                    continue
                sym = e.target_id[len(UNRESOLVED_PREFIX) :]
                short_sym = sym.split(".")[-1]
                same_key = f"{os.path.abspath(node.file_path)}::{short_sym}"
                if same_key in symbol_by_file_name and symbol_by_file_name[same_key]:
                    tid = symbol_by_file_name[same_key][0].id
                    new_edges.append(
                        Edge(
                            target_id=tid,
                            edge_type=e.edge_type,
                            confidence=1.0,
                            resolved=True,
                        )
                    )
                    continue
                if sym.startswith("struct::"):
                    new_edges.append(
                        Edge(
                            target_id=e.target_id,
                            edge_type=e.edge_type,
                            confidence=0.0,
                            resolved=False,
                        )
                    )
                    continue
                res = tracer.resolve(node.file_path, sym.split(".")[-1] if "." in sym else sym)
                if res.is_external and res.found and CONFIG.include_external_nodes:
                    ext_id = self._external_id(res.library_name, res.target_symbol)
                    new_edges.append(
                        Edge(
                            target_id=ext_id,
                            edge_type=e.edge_type,
                            confidence=res.confidence,
                            resolved=True,
                        )
                    )
                    continue
                if res.is_external and res.found and not CONFIG.include_external_nodes:
                    new_edges.append(
                        Edge(
                            target_id=e.target_id,
                            edge_type=e.edge_type,
                            confidence=res.confidence,
                            resolved=False,
                        )
                    )
                    continue
                if res.found and res.target_file:
                    tgt_key = f"{os.path.abspath(res.target_file)}::{res.target_symbol}"
                    candidates = symbol_by_file_name.get(tgt_key) or by_name.get(res.target_symbol, [])
                    if candidates:
                        tid = candidates[0].id
                        new_edges.append(
                            Edge(
                                target_id=tid,
                                edge_type=e.edge_type,
                                confidence=res.confidence,
                                resolved=True,
                            )
                        )
                    else:
                        new_edges.append(
                            Edge(
                                target_id=e.target_id,
                                edge_type=e.edge_type,
                                confidence=0.0,
                                resolved=False,
                            )
                        )
                else:
                    new_edges.append(
                        Edge(
                            target_id=e.target_id,
                            edge_type=e.edge_type,
                            confidence=0.0 if not res.found else res.confidence,
                            resolved=False,
                        )
                    )
            node.edges = new_edges

        self._add_called_by()
        self._fill_adjacency()
        self._add_contains()
        self._add_inherits(symbol_by_file_name, by_name, tracer)
        return self.nodes

    def _external_id(self, library: Optional[str], symbol: str) -> str:
        key = (library, symbol)
        if key in self._externals:
            return self._externals[key]
        ext = ExternalNode(
            id=str(uuid4()),
            name=f"{library or 'ext'}:{symbol}",
            node_type=NodeType.EXTERNAL,
            language=Language.UNKNOWN,
            file_path="",
            repo="",
            git_hash="",
            library_name=library,
            symbol_name=symbol,
        )
        self._externals[key] = ext.id
        self.nodes.append(ext)
        return ext.id

    def _add_called_by(self) -> None:
        extra: list[tuple[BaseNode, Edge]] = []
        for node in self.nodes:
            for e in node.edges:
                if e.edge_type != EdgeType.CALLS or not e.resolved:
                    continue
                tgt = self._find_node(e.target_id)
                if tgt is None:
                    continue
                rev = Edge(
                    target_id=node.id,
                    edge_type=EdgeType.CALLED_BY,
                    confidence=e.confidence,
                    resolved=True,
                )
                extra.append((tgt, rev))
        for tgt, rev in extra:
            tgt.edges.append(rev)

    def _find_node(self, node_id: str) -> Optional[BaseNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def _fill_adjacency(self) -> None:
        for n in self.nodes:
            n.calls = [e.target_id for e in n.edges if e.edge_type == EdgeType.CALLS]
            n.called_by = [e.target_id for e in n.edges if e.edge_type == EdgeType.CALLED_BY]

    def _add_contains(self) -> None:
        for n in self.nodes:
            if not isinstance(n, MethodNode):
                continue
            if not n.parent_id:
                continue
            parent = self._find_node(n.parent_id)
            if parent is None:
                continue
            parent.edges.append(
                Edge(target_id=n.id, edge_type=EdgeType.CONTAINS, confidence=1.0, resolved=True)
            )

    def _add_inherits(
        self,
        symbol_by_file_name: dict[str, list[BaseNode]],
        by_name: dict[str, list[BaseNode]],
        tracer: ImportTracer,
    ) -> None:
        for n in self.nodes:
            if not isinstance(n, ClassNode):
                continue
            for base in n.bases:
                if base.startswith("interface:"):
                    bname = base[len("interface:") :]
                else:
                    bname = base.split(".")[-1]
                cands = by_name.get(bname, [])
                conf = 1.0
                if not cands:
                    conf = 0.8
                    continue
                tid = cands[0].id
                n.edges.append(
                    Edge(target_id=tid, edge_type=EdgeType.INHERITS, confidence=conf, resolved=True)
                )
