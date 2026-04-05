"""Python source parser using the stdlib ast module. Does not resolve cross-file edges."""

from __future__ import annotations

import ast
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


def _decorator_names(decs: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for d in decs:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            try:
                names.append(ast.unparse(d))
            except AttributeError:
                names.append(d.attr)
        elif isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                try:
                    names.append(ast.unparse(f))
                except AttributeError:
                    names.append(f.attr)
    return names


def _is_abc_base(name: str) -> bool:
    return name in ("ABC", "ABCMeta") or name.endswith(".ABC")


def _params_from_args(args: ast.arguments, skip: set[str]) -> list[Param]:
    params: list[Param] = []

    def add_arg(a: ast.arg, default: Optional[ast.expr]) -> None:
        if a.arg in skip:
            return
        ann: Optional[str] = None
        if a.annotation:
            try:
                ann = ast.unparse(a.annotation)
            except AttributeError:
                ann = None
        default_s: Optional[str] = None
        if default:
            try:
                default_s = ast.unparse(default)
            except AttributeError:
                default_s = None
        params.append(Param(name=a.arg, annotation=ann, default=default_s))

    num_defaults = len(args.defaults)
    num_pos = len(args.posonlyargs) + len(args.args)
    defaults_list = [None] * (num_pos - num_defaults) + list(args.defaults)

    idx = 0
    for a in args.posonlyargs:
        add_arg(a, defaults_list[idx] if idx < len(defaults_list) else None)
        idx += 1
    for a in args.args:
        d = defaults_list[idx] if idx < len(defaults_list) else None
        add_arg(a, d)
        idx += 1
    if args.vararg and args.vararg.arg not in skip:
        params.append(Param(name="*" + args.vararg.arg))
    for i, a in enumerate(args.kwonlyargs):
        d = args.kw_defaults[i] if i < len(args.kw_defaults) else None
        add_arg(a, d)
    if args.kwarg and args.kwarg.arg not in skip:
        params.append(Param(name="**" + args.kwarg.arg))
    return params


def _method_params(args: ast.arguments) -> list[Param]:
    return _params_from_args(args, skip={"self", "cls"})


def _read_source_lines(path: str, start: int, end: int) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        s, e = max(0, start - 1), min(len(lines), end)
        return "".join(lines[s:e])
    except OSError as ex:
        log.warning("Could not read %s: %s", path, ex)
        return ""


def _module_external(repo_root: str, module_path: str, is_relative: bool) -> bool:
    if is_relative:
        return False
    clean = module_path.split(".")[0]
    if not clean:
        return True
    root_pkg = os.path.join(repo_root, clean)
    if os.path.isdir(root_pkg) or os.path.isfile(root_pkg + ".py"):
        return False
    return True


class PythonParser(BaseParser):
    """Parse Python files into ClassNode, MethodNode, FunctionNode instances."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".py")

    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        nodes: list[BaseNode] = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)
        except (SyntaxError, OSError) as ex:
            log.warning("Python parse failed %s: %s", file_path, ex)
            return nodes

        for stmt in tree.body:
            if isinstance(stmt, ast.ClassDef):
                nodes.extend(self._parse_class(stmt, file_path, repo, git_hash, source))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = self._parse_function(
                    stmt, file_path, repo, git_hash, source, parent_id=None, is_method=False
                )
                nodes.append(fn)
        return nodes

    def _parse_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        repo: str,
        git_hash: str,
        source: str,
    ) -> list[BaseNode]:
        out: list[BaseNode] = []
        line_start = node.lineno
        line_end = getattr(node, "end_lineno", None) or node.lineno
        code_str = _read_source_lines(file_path, line_start, line_end)
        bases: list[str] = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except AttributeError:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(f"{b.value}.{b.attr}" if hasattr(b.value, "attr") else b.attr)
        dec_names = _decorator_names(node.decorator_list)
        method_abstract = False
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "abstractmethod" in _decorator_names(item.decorator_list):
                    method_abstract = True
                    break
        is_abstract = any(_is_abc_base(b) for b in bases) or "ABC" in bases
        is_abstract = is_abstract or method_abstract or any(
            "abstractmethod" in _decorator_names(getattr(n, "decorator_list", []))
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

        class_id = str(uuid4())
        cls_node = ClassNode(
            id=class_id,
            name=node.name,
            node_type=NodeType.CLASS,
            language=Language.PYTHON,
            file_path=file_path,
            repo=repo,
            git_hash=git_hash,
            line_start=line_start,
            line_end=line_end,
            code_str=code_str,
            docstring=ast.get_docstring(node),
            bases=bases,
            decorators=dec_names,
            is_abstract=is_abstract,
        )
        child_ids: list[str] = []
        for item in node.body:
            if isinstance(item, ast.ClassDef):
                out.extend(self._parse_class(item, file_path, repo, git_hash, source))
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                meth = self._parse_function(
                    item, file_path, repo, git_hash, source, parent_id=class_id, is_method=True
                )
                child_ids.append(meth.id)
                out.append(meth)
        cls_node.children_ids = child_ids
        out.insert(0, cls_node)
        return out

    def _parse_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        repo: str,
        git_hash: str,
        source: str,
        parent_id: Optional[str],
        is_method: bool,
    ) -> FunctionNode | MethodNode:
        line_start = node.lineno
        line_end = getattr(node, "end_lineno", None) or node.lineno
        code_str = _read_source_lines(file_path, line_start, line_end)
        dec_names = _decorator_names(node.decorator_list)
        ret: Optional[str] = None
        if node.returns:
            try:
                ret = ast.unparse(node.returns)
            except AttributeError:
                ret = None
        edges = self._call_edges(node.body, dec_names)

        common = dict(
            id=str(uuid4()),
            name=node.name,
            node_type=NodeType.METHOD if is_method else NodeType.FUNCTION,
            language=Language.PYTHON,
            file_path=file_path,
            repo=repo,
            git_hash=git_hash,
            line_start=line_start,
            line_end=line_end,
            code_str=code_str,
            docstring=ast.get_docstring(node),
            edges=edges,
            parent_id=parent_id,
        )

        if isinstance(node, ast.AsyncFunctionDef):
            meta = {"is_async": True}
        else:
            meta = {}

        if is_method:
            is_static = "staticmethod" in dec_names
            is_cls = "classmethod" in dec_names
            is_prop = "property" in dec_names
            is_abs = "abstractmethod" in dec_names
            m = MethodNode(
                **common,
                params=_method_params(node.args),
                return_type=ret,
                is_static=is_static,
                is_classmethod=is_cls,
                is_property=is_prop,
                is_abstract=is_abs,
            )
            m.metadata.update(meta)
            return m

        f = FunctionNode(
            **common,
            params=_method_params(node.args),
            return_type=ret,
        )
        f.metadata.update(meta)
        return f

    def _call_edges(self, body: list[ast.stmt], _dec_names: list[str]) -> list[Edge]:
        edges: list[Edge] = []

        class Visitor(ast.NodeVisitor):
            def visit_Call(self, call: ast.Call) -> None:  # noqa: N802
                func = call.func
                conf = 1.0
                sym: Optional[str] = None
                if isinstance(func, ast.Name):
                    sym = func.id
                elif isinstance(func, ast.Attribute):
                    try:
                        sym = ast.unparse(func)
                    except AttributeError:
                        sym = f"{getattr(func.value, 'id', '?')}.{func.attr}"
                elif isinstance(func, ast.Subscript):
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

            def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
                # getattr dynamic
                if isinstance(node.value, ast.Call):
                    f = node.value.func
                    if isinstance(f, ast.Name) and f.id == "getattr":
                        edges.append(
                            Edge(
                                target_id="unresolved::dynamic",
                                edge_type=EdgeType.CALLS,
                                confidence=0.2,
                                resolved=False,
                            )
                        )
                self.generic_visit(node)

        for b in body:
            Visitor().visit(b)
        return edges

    def extract_imports(self, file_path: str) -> list[ImportRecord]:
        repo_root = os.path.dirname(file_path)
        # caller should pass repo root; we walk up until we find .git or use heuristic
        # ImportRecord needs is_external — use dirname chain
        repo_root = self._infer_repo_root(file_path)
        records: list[ImportRecord] = []
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except (SyntaxError, OSError):
            return records

        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    mod = alias.name
                    sym = [mod]
                    al = {}
                    if alias.asname:
                        al[mod] = alias.asname
                    ext = _module_external(repo_root, mod, False)
                    records.append(
                        ImportRecord(
                            source_file=file_path,
                            module_path=mod,
                            symbols=sym,
                            is_relative=False,
                            is_external=ext,
                            alias=al,
                        )
                    )
            elif isinstance(stmt, ast.ImportFrom):
                level = stmt.level or 0
                mod = stmt.module or ""
                base = "." * level + (mod if mod else "")
                is_rel = level > 0
                syms = [a.name for a in stmt.names]
                al = {}
                for a in stmt.names:
                    if a.asname:
                        al[a.name] = a.asname
                if not is_rel:
                    ext = _module_external(repo_root, mod or syms[0] if syms else "", False)
                else:
                    ext = False
                records.append(
                    ImportRecord(
                        source_file=file_path,
                        module_path=base if is_rel else (mod or ""),
                        symbols=syms,
                        is_relative=is_rel,
                        is_external=ext,
                        alias=al,
                    )
                )
        return records

    def _infer_repo_root(self, file_path: str) -> str:
        cur = os.path.dirname(os.path.abspath(file_path))
        for _ in range(20):
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return cur
