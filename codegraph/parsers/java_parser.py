"""Java source parser via tree-sitter. Does not resolve cross-file edges."""

from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import uuid4

from codegraph.core.node import (
    BaseNode,
    ClassNode,
    Edge,
    EdgeType,
    Language,
    MethodNode,
    NodeType,
    Param,
)
from codegraph.core.parser_base import BaseParser, ImportRecord

log = logging.getLogger("codegraph")


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line_slice(path: str, start: int, end: int) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[max(0, start - 1) : min(len(lines), end)])
    except OSError:
        return ""


def _infer_repo_root(file_path: str) -> str:
    cur = os.path.dirname(os.path.abspath(file_path))
    for _ in range(20):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return cur


def _pkg_root_java(repo_root: str) -> str:
    for base in ("src/main/java", "src", repo_root):
        p = os.path.join(repo_root, base) if base != repo_root else repo_root
        if os.path.isdir(p):
            return p
    return repo_root


def _collect_calls(body, src: bytes) -> list[Edge]:
    edges: list[Edge] = []

    def walk(n) -> None:
        if n.type == "method_invocation":
            obj = n.child_by_field_name("object")
            name = n.child_by_field_name("name")
            if name:
                sym = _text(name, src)
                if obj:
                    sym = f"{_text(obj, src)}.{sym}"
                edges.append(
                    Edge(
                        target_id=f"unresolved::{sym}",
                        edge_type=EdgeType.CALLS,
                        confidence=1.0,
                        resolved=False,
                    )
                )
        for c in n.children:
            walk(c)

    if body:
        walk(body)
    return edges


class JavaParser(BaseParser):
    """Parse Java compilation units into ClassNode / MethodNode."""

    def __init__(self) -> None:
        self._parser = None

    def _get(self):
        if self._parser is None:
            from tree_sitter_languages import get_parser as gp

            self._parser = gp("java")
        return self._parser

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".java")

    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        nodes: list[BaseNode] = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            tree = self._get().parse(src)
        except Exception as ex:  # noqa: BLE001
            log.warning("Java parse failed %s: %s", file_path, ex)
            return nodes

        def parse_type_body(body, class_id: str, class_name: str) -> list[BaseNode]:
            inner: list[BaseNode] = []
            if not body:
                return inner
            members = list(body.children)
            for ch in body.children:
                if ch.type == "enum_body_declarations":
                    members.extend(ch.children)
            for ch in members:
                if ch.type == "method_declaration":
                    name_n = ch.child_by_field_name("name")
                    mname = _text(name_n, src) if name_n else "method"
                    mls, mle = ch.start_point[0] + 1, ch.end_point[0] + 1
                    blk = ch.child_by_field_name("body")
                    edges = _collect_calls(blk, src) if blk else []
                    params = _java_params(ch, src)
                    ret = _java_return(ch, src)
                    static = _has_mod(ch, "static")
                    anns = _annotations(ch, src)
                    inner.append(
                        MethodNode(
                            id=str(uuid4()),
                            name=mname,
                            node_type=NodeType.METHOD,
                            language=Language.JAVA,
                            file_path=file_path,
                            repo=repo,
                            git_hash=git_hash,
                            line_start=mls,
                            line_end=mle,
                            code_str=_line_slice(file_path, mls, mle),
                            edges=edges,
                            parent_id=class_id,
                            params=params,
                            return_type=ret,
                            is_static=static,
                            metadata={"annotations": anns},
                        )
                    )
                elif ch.type == "constructor_declaration":
                    mls, mle = ch.start_point[0] + 1, ch.end_point[0] + 1
                    blk = ch.child_by_field_name("body")
                    edges = _collect_calls(blk, src) if blk else []
                    inner.append(
                        MethodNode(
                            id=str(uuid4()),
                            name=class_name,
                            node_type=NodeType.METHOD,
                            language=Language.JAVA,
                            file_path=file_path,
                            repo=repo,
                            git_hash=git_hash,
                            line_start=mls,
                            line_end=mle,
                            code_str=_line_slice(file_path, mls, mle),
                            edges=edges,
                            parent_id=class_id,
                            params=_java_params(ch, src),
                            return_type=None,
                            metadata={"is_constructor": True},
                        )
                    )
            return inner

        _TYPE_DECLS = {"class_declaration", "interface_declaration", "enum_declaration"}
        for root_child in tree.root_node.children:
            if root_child.type not in _TYPE_DECLS:
                continue
            kind = {
                "class_declaration": "class",
                "interface_declaration": "interface",
                "enum_declaration": "enum",
            }[root_child.type]
            result = _parse_java_type(
                root_child, file_path, repo, git_hash, src, parse_type_body, kind,
            )
            if result:
                nodes.extend(result)
        return nodes

    def extract_imports(self, file_path: str) -> list[ImportRecord]:
        out: list[ImportRecord] = []
        repo_root = _infer_repo_root(file_path)
        pkg_root = _pkg_root_java(repo_root)
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            tree = self._get().parse(src)
        except Exception:  # noqa: BLE001
            return out

        for ch in tree.root_node.children:
            if ch.type != "import_declaration":
                continue
            scoped = ch.child_by_field_name("name")
            if scoped is None:
                continue
            txt = _text(scoped, src).rstrip(";").strip()
            if txt.endswith(".*"):
                mod = txt[:-2].rsplit(".", 1)[0] if "." in txt else txt[:-2]
                sym = ["*"]
            else:
                parts = txt.split(".")
                mod = ".".join(parts[:-1]) if len(parts) > 1 else parts[0]
                sym = [parts[-1]] if parts else ["*"]
            rel_path = os.path.join(pkg_root, *mod.split("."))
            ext = not (os.path.isfile(rel_path + ".java") or os.path.isdir(rel_path))
            out.append(
                ImportRecord(
                    source_file=file_path,
                    module_path=mod,
                    symbols=sym,
                    is_relative=False,
                    is_external=ext,
                    alias={},
                )
            )
        return out


def _has_mod(node, mod: str) -> bool:
    return any(c.type == mod for c in node.children)


def _annotations(node, src: bytes) -> list[str]:
    anns: list[str] = []
    for c in node.children:
        if c.type == "modifiers":
            for m in c.children:
                if m.type == "annotation":
                    n = m.child_by_field_name("name")
                    if n:
                        anns.append(_text(n, src))
    return anns


def _java_params(node, src: bytes) -> list[Param]:
    params: list[Param] = []
    plist = node.child_by_field_name("parameters")
    if not plist:
        return params
    for ch in plist.children:
        if ch.type == "formal_parameter":
            typ = ch.child_by_field_name("type")
            name = ch.child_by_field_name("name")
            if name:
                params.append(
                    Param(
                        name=_text(name, src),
                        annotation=_text(typ, src) if typ else None,
                    )
                )
    return params


def _java_return(node, src: bytes) -> Optional[str]:
    typ = node.child_by_field_name("type")
    if typ:
        return _text(typ, src)
    return None


def _parse_java_type(
    root,
    file_path: str,
    repo: str,
    git_hash: str,
    src: bytes,
    parse_type_body,
    kind: str,
) -> Optional[list[BaseNode]]:
    """Parse a class, interface, or enum declaration."""
    name_n = root.child_by_field_name("name")
    cname = _text(name_n, src) if name_n else kind.capitalize()
    ls, le = root.start_point[0] + 1, root.end_point[0] + 1
    bases: list[str] = []
    sup = root.child_by_field_name("superclass")
    if sup:
        for c in sup.children:
            if c.type == "type_identifier":
                bases.append(_text(c, src))
    iface = root.child_by_field_name("interfaces")
    if iface:
        for c in iface.children:
            if c.type == "type_list":
                for t in c.children:
                    if t.type == "type_identifier":
                        bases.append(f"interface:{_text(t, src)}")
    decs = _annotations(root, src)

    is_abstract = kind == "interface" or _has_mod(root, "abstract")
    meta: dict = {"java_kind": kind}

    if kind == "enum":
        enum_constants: list[str] = []
        body = root.child_by_field_name("body")
        if body:
            for ch in body.children:
                if ch.type == "enum_constant":
                    ec_name = ch.child_by_field_name("name")
                    if ec_name:
                        enum_constants.append(_text(ec_name, src))
        meta["enum_constants"] = enum_constants

    cid = str(uuid4())
    body = root.child_by_field_name("body")
    methods = parse_type_body(body, cid, cname) if body else []

    if kind == "interface":
        for m in methods:
            if isinstance(m, MethodNode):
                m.is_abstract = True

    cls = ClassNode(
        id=cid,
        name=cname,
        node_type=NodeType.CLASS,
        language=Language.JAVA,
        file_path=file_path,
        repo=repo,
        git_hash=git_hash,
        line_start=ls,
        line_end=le,
        code_str=_line_slice(file_path, ls, le),
        bases=bases,
        decorators=decs,
        is_abstract=is_abstract,
        children_ids=[m.id for m in methods],
        metadata=meta,
    )
    return [cls, *methods]
