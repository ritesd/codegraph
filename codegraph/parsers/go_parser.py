"""Go source parser via tree-sitter. Does not resolve cross-file edges."""

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
    FunctionNode,
    Language,
    MethodNode,
    NodeType,
    Param,
)
from codegraph.core.parser_base import BaseParser, ImportRecord

log = logging.getLogger("codegraph")

GO_STDLIB = frozenset(
    "fmt os io net http strings strconv errors context sync time math sort log path bufio bytes "
    "encoding crypto regexp reflect runtime testing".split()
)


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


def _collect_calls(body, src: bytes) -> list[Edge]:
    edges: list[Edge] = []

    def walk(n) -> None:
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            sym: Optional[str] = None
            if fn and fn.type == "identifier":
                sym = _text(fn, src)
            elif fn and fn.type == "selector_expression":
                sym = _text(fn, src)
            if sym:
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


def _params_from_signature(sig, src: bytes) -> tuple[list[Param], Optional[str]]:
    params: list[Param] = []
    plist = sig.child_by_field_name("parameters") if sig else None
    if plist:
        for ch in plist.children:
            if ch.type == "parameter_declaration":
                names = [c for c in ch.children if c.type == "identifier"]
                typ_n = ch.child_by_field_name("type")
                typ = _text(typ_n, src) if typ_n else None
                for nm in names:
                    params.append(Param(name=_text(nm, src), annotation=typ))
    ret_txt: Optional[str] = None
    if sig:
        rt = sig.child_by_field_name("result")
        if rt:
            if rt.type == "type_identifier" or rt.type == "qualified_type":
                ret_txt = _text(rt, src)
            elif rt.type == "parameter_list":
                parts = []
                for ch in rt.children:
                    if ch.type == "parameter_declaration":
                        t = ch.child_by_field_name("type")
                        if t:
                            parts.append(_text(t, src))
                ret_txt = ", ".join(parts) if parts else None
            else:
                ret_txt = _text(rt, src)
    return params, ret_txt


class GoParser(BaseParser):
    """Parse Go files: structs/interfaces as ClassNode, methods as MethodNode."""

    def __init__(self) -> None:
        self._parser = None

    def _get(self):
        if self._parser is None:
            from tree_sitter_languages import get_parser as gp

            self._parser = gp("go")
        return self._parser

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".go")

    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        nodes: list[BaseNode] = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            tree = self._get().parse(src)
        except Exception as ex:  # noqa: BLE001
            log.warning("Go parse failed %s: %s", file_path, ex)
            return nodes

        recv_map: dict[str, str] = {}

        def decl_name(typ_n) -> Optional[str]:
            if typ_n is None:
                return None
            if typ_n.type == "type_identifier":
                return _text(typ_n, src)
            if typ_n.type == "pointer_type":
                inner = typ_n.child_by_field_name("type")
                return decl_name(inner)
            return None

        for child in tree.root_node.children:
            if child.type == "type_declaration":
                for spec in child.children:
                    if spec.type != "type_spec":
                        continue
                    name_n = spec.child_by_field_name("name")
                    typ = spec.child_by_field_name("type")
                    nm = _text(name_n, src) if name_n else "type"
                    if typ is None:
                        continue
                    ls, le = spec.start_point[0] + 1, spec.end_point[0] + 1
                    if typ.type == "struct_type":
                        cid = str(uuid4())
                        recv_map[nm] = cid
                        nodes.append(
                            ClassNode(
                                id=cid,
                                name=nm,
                                node_type=NodeType.CLASS,
                                language=Language.GO,
                                file_path=file_path,
                                repo=repo,
                                git_hash=git_hash,
                                line_start=ls,
                                line_end=le,
                                code_str=_line_slice(file_path, ls, le),
                                metadata={"go_kind": "struct"},
                                is_abstract=False,
                            )
                        )
                    elif typ.type == "interface_type":
                        cid = str(uuid4())
                        recv_map[nm] = cid
                        nodes.append(
                            ClassNode(
                                id=cid,
                                name=nm,
                                node_type=NodeType.CLASS,
                                language=Language.GO,
                                file_path=file_path,
                                repo=repo,
                                git_hash=git_hash,
                                line_start=ls,
                                line_end=le,
                                code_str=_line_slice(file_path, ls, le),
                                is_abstract=True,
                                metadata={"go_kind": "interface"},
                            )
                        )
            elif child.type == "function_declaration":
                name_n = child.child_by_field_name("name")
                recv = child.child_by_field_name("receiver")
                outer_sig = child
                body = child.child_by_field_name("body")
                fname = _text(name_n, src) if name_n else "func"
                ls, le = child.start_point[0] + 1, child.end_point[0] + 1
                params, ret = _params_from_signature(outer_sig, src)
                edges = _collect_calls(body, src) if body else []
                parent_id: Optional[str] = None
                if recv:
                    rtype = recv.child_by_field_name("type")
                    rname = decl_name(rtype)
                    if rname and rname in recv_map:
                        parent_id = recv_map[rname]
                    elif rname:
                        parent_id = f"unresolved::struct::{rname}"
                if recv:
                    nodes.append(
                        MethodNode(
                            id=str(uuid4()),
                            name=fname,
                            node_type=NodeType.METHOD,
                            language=Language.GO,
                            file_path=file_path,
                            repo=repo,
                            git_hash=git_hash,
                            line_start=ls,
                            line_end=le,
                            code_str=_line_slice(file_path, ls, le),
                            edges=edges,
                            parent_id=parent_id,
                            params=params,
                            return_type=ret,
                            metadata={},
                        )
                    )
                else:
                    nodes.append(
                        FunctionNode(
                            id=str(uuid4()),
                            name=fname,
                            node_type=NodeType.FUNCTION,
                            language=Language.GO,
                            file_path=file_path,
                            repo=repo,
                            git_hash=git_hash,
                            line_start=ls,
                            line_end=le,
                            code_str=_line_slice(file_path, ls, le),
                            edges=edges,
                            parent_id=None,
                            params=params,
                            return_type=ret,
                            metadata={},
                        )
                    )
        return nodes

    def extract_imports(self, file_path: str) -> list[ImportRecord]:
        out: list[ImportRecord] = []
        repo_root = _infer_repo_root(file_path)
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            tree = self._get().parse(src)
        except Exception:  # noqa: BLE001
            return out

        def walk(n) -> None:
            if n.type == "import_spec":
                path_n = n.child_by_field_name("path")
                mod = _text(path_n, src).strip('"') if path_n else ""
                base = mod.split("/")[0] if mod else ""
                is_ext = not mod.startswith(".") and base not in GO_STDLIB and "." in mod
                out.append(
                    ImportRecord(
                        source_file=file_path,
                        module_path=mod,
                        symbols=["*"],
                        is_relative=mod.startswith("."),
                        is_external=is_ext,
                        alias={},
                    )
                )
            for c in n.children:
                walk(c)

        walk(tree.root_node)
        return out