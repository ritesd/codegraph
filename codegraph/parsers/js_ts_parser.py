"""JavaScript/TypeScript parser via tree-sitter. Does not resolve cross-file edges."""

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


def _ts_lang(path: str) -> bool:
    return path.lower().endswith((".ts", ".tsx"))


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


def _path_in_repo(repo_root: str, mod: str) -> bool:
    if not mod or mod.startswith(".") or mod.startswith("/"):
        return True
    root = mod.split("/")[0]
    return os.path.isdir(os.path.join(repo_root, root))


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line_slice(path: str, start: int, end: int) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[max(0, start - 1) : min(len(lines), end)])
    except OSError:
        return ""


def _collect_call_edges(root, src: bytes) -> list[Edge]:
    edges: list[Edge] = []

    def walk(n) -> None:
        if n.type == "call_expression":
            func = n.child_by_field_name("function")
            conf = 1.0
            sym: Optional[str] = None
            if func:
                if func.type == "identifier":
                    sym = _text(func, src)
                elif func.type == "member_expression":
                    sym = _text(func, src)
                elif func.type == "subscript_expression":
                    conf = 0.2
                    sym = "dynamic"
            if sym:
                edges.append(
                    Edge(
                        target_id=f"unresolved::{sym}",
                        edge_type=EdgeType.CALLS,
                        confidence=conf,
                        resolved=False,
                    )
                )
        for c in n.children:
            walk(c)

    walk(root)
    return edges


def _formal_params(node, src: bytes) -> list[Param]:
    params: list[Param] = []
    plist = node.child_by_field_name("parameters")
    if plist is None:
        return params
    for ch in plist.children:
        if ch.type in ("required_parameter", "optional_parameter"):
            pat = ch.child_by_field_name("pattern")
            typ = ch.child_by_field_name("type")
            nm = _text(pat, src) if pat else "arg"
            ann = _text(typ, src) if typ else None
            params.append(Param(name=nm, annotation=ann))
        elif ch.type == "identifier":
            params.append(Param(name=_text(ch, src)))
    return params


def _return_type_ts(node, src: bytes) -> Optional[str]:
    typ = node.child_by_field_name("return_type") or node.child_by_field_name("type")
    if typ is not None:
        return _text(typ, src)
    for ch in node.children:
        if ch.type == "type_annotation":
            return _text(ch, src)
    return None


class JsTsParser(BaseParser):
    """Parse JS/TS with tree-sitter."""

    def __init__(self) -> None:
        self._ts_parser = None

    def _parser(self, path: str):
        if self._ts_parser is None:
            from tree_sitter_languages import get_parser as gp

            self._ts_parser = gp
        lang = "typescript" if _ts_lang(path) else "javascript"
        return self._ts_parser(lang)

    def can_parse(self, file_path: str) -> bool:
        lower = file_path.lower()
        return lower.endswith((".js", ".jsx", ".ts", ".tsx"))

    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        nodes: list[BaseNode] = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            p = self._parser(file_path)
            tree = p.parse(src)
        except Exception as ex:  # noqa: BLE001
            log.warning("JS/TS parse failed %s: %s", file_path, ex)
            return nodes

        lang = Language.TYPESCRIPT if _ts_lang(file_path) else Language.JAVASCRIPT
        root = tree.root_node
        for child in root.children:
            self._handle_top_level(child, src, file_path, repo, git_hash, lang, nodes, exported=False)
        return nodes

    def _handle_top_level(
        self,
        child,
        src: bytes,
        path: str,
        repo: str,
        git_hash: str,
        lang: Language,
        nodes: list[BaseNode],
        exported: bool,
    ) -> None:
        t = child.type
        if t == "class_declaration":
            self._parse_class(child, src, path, repo, git_hash, lang, nodes, exported=exported)
        elif t == "function_declaration":
            name_obj = child.child_by_field_name("name")
            nm = _text(name_obj, src) if name_obj else "fn"
            ls, le = child.start_point[0] + 1, child.end_point[0] + 1
            body = child.child_by_field_name("body")
            edges = _collect_call_edges(body, src) if body else []
            nodes.append(
                FunctionNode(
                    id=str(uuid4()),
                    name=nm,
                    node_type=NodeType.FUNCTION,
                    language=lang,
                    file_path=path,
                    repo=repo,
                    git_hash=git_hash,
                    line_start=ls,
                    line_end=le,
                    code_str=_line_slice(path, ls, le),
                    edges=edges,
                    params=_formal_params(child, src),
                    return_type=_return_type_ts(child, src),
                    metadata={"exported": exported},
                )
            )
        elif t == "export_statement":
            inner = None
            for c in child.children:
                if c.type in ("class_declaration", "function_declaration", "lexical_declaration"):
                    inner = c
                    break
            if inner is not None:
                self._handle_top_level(inner, src, path, repo, git_hash, lang, nodes, exported=True)
        elif t == "lexical_declaration":
            for ch in child.children:
                if ch.type == "variable_declarator":
                    name_n = ch.child_by_field_name("name")
                    val = ch.child_by_field_name("value")
                    if val and val.type in ("arrow_function", "function_expression", "function"):
                        nm = _text(name_n, src) if name_n else f"@line{val.start_point[0] + 1}"
                        ls, le = val.start_point[0] + 1, val.end_point[0] + 1
                        body = val.child_by_field_name("body")
                        edges = _collect_call_edges(body, src) if body else []
                        params = _formal_params(val, src)
                        nodes.append(
                            FunctionNode(
                                id=str(uuid4()),
                                name=nm,
                                node_type=NodeType.FUNCTION,
                                language=lang,
                                file_path=path,
                                repo=repo,
                                git_hash=git_hash,
                                line_start=ls,
                                line_end=le,
                                code_str=_line_slice(path, ls, le),
                                edges=edges,
                                params=params,
                                return_type=_return_type_ts(val, src),
                                metadata={"exported": exported},
                            )
                        )

    def _parse_class(
        self,
        node,
        src: bytes,
        path: str,
        repo: str,
        git_hash: str,
        lang: Language,
        nodes: list[BaseNode],
        exported: bool = False,
    ) -> None:
        name_id = node.child_by_field_name("name")
        name = _text(name_id, src) if name_id else "anonymous"
        ls, le = node.start_point[0] + 1, node.end_point[0] + 1
        bases: list[str] = []
        heritage = node.child_by_field_name("heritage")
        if heritage:
            for ch in heritage.children:
                if ch.type == "extends_clause":
                    for e in ch.children:
                        if e.type not in ("extends", ","):
                            bases.append(_text(e, src))
        class_id = str(uuid4())
        cls = ClassNode(
            id=class_id,
            name=name,
            node_type=NodeType.CLASS,
            language=lang,
            file_path=path,
            repo=repo,
            git_hash=git_hash,
            line_start=ls,
            line_end=le,
            code_str=_line_slice(path, ls, le),
            bases=bases,
            decorators=[],
            is_abstract=False,
            metadata={"exported": exported},
        )
        child_ids: list[str] = []
        body = node.child_by_field_name("body")
        methods: list[BaseNode] = []
        if body:
            for ch in body.children:
                if ch.type == "method_definition":
                    mname_n = ch.child_by_field_name("name")
                    mname = _text(mname_n, src) if mname_n else "method"
                    mls, mle = ch.start_point[0] + 1, ch.end_point[0] + 1
                    mb = ch.child_by_field_name("body")
                    edges = _collect_call_edges(mb, src) if mb else []
                    static = any(c.type == "static" for c in ch.children)
                    mn = MethodNode(
                        id=str(uuid4()),
                        name=mname,
                        node_type=NodeType.METHOD,
                        language=lang,
                        file_path=path,
                        repo=repo,
                        git_hash=git_hash,
                        line_start=mls,
                        line_end=mle,
                        code_str=_line_slice(path, mls, mle),
                        edges=edges,
                        parent_id=class_id,
                        params=_formal_params(ch, src),
                        return_type=_return_type_ts(ch, src),
                        is_static=static,
                        metadata={},
                    )
                    child_ids.append(mn.id)
                    methods.append(mn)
        cls.children_ids = child_ids
        nodes.append(cls)
        nodes.extend(methods)

    def extract_imports(self, file_path: str) -> list[ImportRecord]:
        records: list[ImportRecord] = []
        repo_root = _infer_repo_root(file_path)
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                src = f.read().encode("utf-8")
            tree = self._parser(file_path).parse(src)
        except Exception:  # noqa: BLE001
            return records

        def walk(n) -> None:
            if n.type == "import_statement":
                src_clause = n.child_by_field_name("source")
                mod = _text(src_clause, src).strip("'\"") if src_clause else ""
                syms: list[str] = []
                al: dict[str, str] = {}
                for ch in n.children:
                    if ch.type == "import_clause":
                        for sub in ch.children:
                            if sub.type == "named_imports":
                                for nm in sub.children:
                                    if nm.type == "import_specifier":
                                        orig = nm.child_by_field_name("name")
                                        alias = nm.child_by_field_name("alias")
                                        otxt = _text(orig, src) if orig else ""
                                        atxt = _text(alias, src) if alias else ""
                                        if otxt:
                                            syms.append(otxt)
                                            if atxt:
                                                al[otxt] = atxt
                            elif sub.type == "identifier":
                                syms.append(_text(sub, src))
                if not syms:
                    syms = ["*"]
                is_rel = mod.startswith(".")
                ext = not is_rel and not _path_in_repo(repo_root, mod)
                records.append(
                    ImportRecord(
                        source_file=file_path,
                        module_path=mod,
                        symbols=syms,
                        is_relative=is_rel,
                        is_external=ext,
                        alias=al,
                    )
                )
            elif n.type == "call_expression":
                func = n.child_by_field_name("function")
                args = n.child_by_field_name("arguments")
                if func and func.type == "identifier" and _text(func, src) == "require" and args:
                    for i, ac in enumerate(args.children):
                        if ac.type == "string":
                            mod = _text(ac, src).strip("'\"")
                            ext = not _path_in_repo(repo_root, mod)
                            records.append(
                                ImportRecord(
                                    source_file=file_path,
                                    module_path=mod,
                                    symbols=["*"],
                                    is_relative=False,
                                    is_external=ext,
                                    alias={},
                                )
                            )
                            break
            for ch in n.children:
                walk(ch)

        walk(tree.root_node)
        return records
