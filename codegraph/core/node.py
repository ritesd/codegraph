"""Dataclass schema for CodeGraph nodes, edges, and enums.

Defines all node types and serialization helpers. Does NOT parse code or touch the filesystem.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class NodeType(str, Enum):
    CLASS = "CLASS"
    METHOD = "METHOD"
    FUNCTION = "FUNCTION"
    EXTERNAL = "EXTERNAL"


class EdgeType(str, Enum):
    CALLS = "CALLS"
    CALLED_BY = "CALLED_BY"
    CONTAINS = "CONTAINS"
    INHERITS = "INHERITS"
    IMPORTS = "IMPORTS"


class Language(str, Enum):
    PYTHON = "PYTHON"
    JAVASCRIPT = "JAVASCRIPT"
    TYPESCRIPT = "TYPESCRIPT"
    GO = "GO"
    JAVA = "JAVA"
    UNKNOWN = "UNKNOWN"


@dataclass
class Param:
    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None


@dataclass
class Edge:
    target_id: str
    edge_type: EdgeType
    confidence: float = 1.0
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "edge_type": self.edge_type.value if isinstance(self.edge_type, EdgeType) else self.edge_type,
            "confidence": self.confidence,
            "resolved": self.resolved,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Edge:
        return Edge(
            target_id=d["target_id"],
            edge_type=EdgeType(d["edge_type"]) if isinstance(d["edge_type"], str) else d["edge_type"],
            confidence=float(d.get("confidence", 1.0)),
            resolved=bool(d.get("resolved", False)),
        )


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class BaseNode:
    id: str
    name: str
    node_type: NodeType
    language: Language
    file_path: str
    repo: str
    git_hash: str
    line_start: int = 0
    line_end: int = 0
    code_str: str = ""
    docstring: Optional[str] = None
    edges: list[Edge] = field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class ClassNode(BaseNode):
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    is_abstract: bool = False

    def __post_init__(self) -> None:
        self.node_type = NodeType.CLASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "language": self.language.value,
            "file_path": self.file_path,
            "repo": self.repo,
            "git_hash": self.git_hash,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_str": self.code_str,
            "docstring": self.docstring,
            "edges": [e.to_dict() for e in self.edges],
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "calls": list(self.calls),
            "called_by": list(self.called_by),
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "bases": list(self.bases),
            "decorators": list(self.decorators),
            "is_abstract": self.is_abstract,
        }


@dataclass
class MethodNode(BaseNode):
    params: list[Param] = field(default_factory=list)
    return_type: Optional[str] = None
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    is_abstract: bool = False

    def __post_init__(self) -> None:
        self.node_type = NodeType.METHOD

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "language": self.language.value,
            "file_path": self.file_path,
            "repo": self.repo,
            "git_hash": self.git_hash,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_str": self.code_str,
            "docstring": self.docstring,
            "edges": [e.to_dict() for e in self.edges],
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "calls": list(self.calls),
            "called_by": list(self.called_by),
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "params": [{"name": p.name, "annotation": p.annotation, "default": p.default} for p in self.params],
            "return_type": self.return_type,
            "is_static": self.is_static,
            "is_classmethod": self.is_classmethod,
            "is_property": self.is_property,
            "is_abstract": self.is_abstract,
        }


@dataclass
class FunctionNode(BaseNode):
    params: list[Param] = field(default_factory=list)
    return_type: Optional[str] = None

    def __post_init__(self) -> None:
        self.node_type = NodeType.FUNCTION

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "language": self.language.value,
            "file_path": self.file_path,
            "repo": self.repo,
            "git_hash": self.git_hash,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_str": self.code_str,
            "docstring": self.docstring,
            "edges": [e.to_dict() for e in self.edges],
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "calls": list(self.calls),
            "called_by": list(self.called_by),
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "params": [{"name": p.name, "annotation": p.annotation, "default": p.default} for p in self.params],
            "return_type": self.return_type,
        }


@dataclass
class ExternalNode(BaseNode):
    library_name: Optional[str] = None
    symbol_name: str = ""

    def __post_init__(self) -> None:
        self.node_type = NodeType.EXTERNAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "language": self.language.value,
            "file_path": self.file_path,
            "repo": self.repo,
            "git_hash": self.git_hash,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_str": self.code_str,
            "docstring": self.docstring,
            "edges": [e.to_dict() for e in self.edges],
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "calls": list(self.calls),
            "called_by": list(self.called_by),
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "library_name": self.library_name,
            "symbol_name": self.symbol_name,
        }


def make_node(node_type: NodeType, **kwargs: Any) -> BaseNode:
    """Construct the appropriate node subclass from type and keyword arguments."""
    nt = node_type if isinstance(node_type, NodeType) else NodeType(node_type)
    kwargs.pop("node_type", None)
    edges_raw = kwargs.pop("edges", None) or []
    edges = [Edge.from_dict(e) if isinstance(e, dict) else e for e in edges_raw]
    params_raw = kwargs.pop("params", None) or []
    params: list[Param] = []
    for p in params_raw:
        if isinstance(p, Param):
            params.append(p)
        elif isinstance(p, dict):
            params.append(Param(name=p["name"], annotation=p.get("annotation"), default=p.get("default")))

    common = {
        "id": kwargs.get("id", _new_id()),
        "name": kwargs["name"],
        "node_type": nt,
        "language": Language(kwargs["language"]) if isinstance(kwargs["language"], str) else kwargs["language"],
        "file_path": kwargs["file_path"],
        "repo": kwargs["repo"],
        "git_hash": kwargs["git_hash"],
        "line_start": int(kwargs.get("line_start", 0)),
        "line_end": int(kwargs.get("line_end", 0)),
        "code_str": kwargs.get("code_str", ""),
        "docstring": kwargs.get("docstring"),
        "edges": edges,
        "parent_id": kwargs.get("parent_id"),
        "children_ids": list(kwargs.get("children_ids", []) or []),
        "calls": list(kwargs.get("calls", []) or []),
        "called_by": list(kwargs.get("called_by", []) or []),
        "summary": kwargs.get("summary"),
        "metadata": dict(kwargs.get("metadata", {}) or {}),
    }

    if nt == NodeType.CLASS:
        return ClassNode(
            **common,
            bases=list(kwargs.get("bases", []) or []),
            decorators=list(kwargs.get("decorators", []) or []),
            is_abstract=bool(kwargs.get("is_abstract", False)),
        )
    if nt == NodeType.METHOD:
        return MethodNode(
            **common,
            params=params,
            return_type=kwargs.get("return_type"),
            is_static=bool(kwargs.get("is_static", False)),
            is_classmethod=bool(kwargs.get("is_classmethod", False)),
            is_property=bool(kwargs.get("is_property", False)),
            is_abstract=bool(kwargs.get("is_abstract", False)),
        )
    if nt == NodeType.FUNCTION:
        return FunctionNode(
            **common,
            params=params,
            return_type=kwargs.get("return_type"),
        )
    if nt == NodeType.EXTERNAL:
        return ExternalNode(
            **common,
            library_name=kwargs.get("library_name"),
            symbol_name=kwargs.get("symbol_name", kwargs["name"]),
        )
    raise ValueError(f"Unknown node type: {nt}")
