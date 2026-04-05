"""Maps imports and symbols to defining files for edge resolution.

Builds an in-memory import index. Does not mutate parser nodes.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

from codegraph.core.parser_base import ImportRecord

log = logging.getLogger("codegraph")

_JS_EXPORT_RE = re.compile(
    r"export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)"
)
_JS_REEXPORT_RE = re.compile(
    r"export\s*\{([^}]+)\}\s*from"
)


@dataclass
class ResolveResult:
    found: bool
    target_file: Optional[str]
    target_symbol: str
    confidence: float
    is_external: bool
    library_name: Optional[str]
    via_barrel: bool


class ImportTracer:
    """Resolve symbols used in a file to defining files using import records."""

    def __init__(self, repo_root: str, all_imports: list[ImportRecord]) -> None:
        self.repo_root = os.path.abspath(repo_root)
        self.all_imports = all_imports
        self._by_file: dict[str, list[ImportRecord]] = {}
        self._global_defs: dict[str, list[str]] = {}

    def build(self) -> None:
        for rec in self.all_imports:
            self._by_file.setdefault(rec.source_file, []).append(rec)
        for rec in self.all_imports:
            for sym in rec.symbols:
                if sym and sym != "*":
                    self._global_defs.setdefault(sym, []).append(rec.source_file)

    def resolve(self, source_file: str, symbol: str) -> ResolveResult:
        sf = os.path.abspath(source_file)
        if symbol == "dynamic":
            return ResolveResult(
                found=False,
                target_file=None,
                target_symbol=symbol,
                confidence=0.2,
                is_external=False,
                library_name=None,
                via_barrel=False,
            )

        for rec in self._by_file.get(sf, []):
            resolved_sym = rec.alias.get(symbol, symbol)
            if resolved_sym in rec.symbols or "*" in rec.symbols:
                path, via_barrel, conf = self._resolve_module(rec, resolved_sym)
                if path and os.path.isfile(path):
                    if "*" in rec.symbols and resolved_sym not in rec.symbols:
                        star_found = self._resolve_star(path, resolved_sym)
                        if star_found:
                            return ResolveResult(
                                found=True,
                                target_file=path,
                                target_symbol=resolved_sym,
                                confidence=0.5,
                                is_external=False,
                                library_name=None,
                                via_barrel=via_barrel,
                            )
                        continue
                    return ResolveResult(
                        found=True,
                        target_file=path,
                        target_symbol=resolved_sym,
                        confidence=conf,
                        is_external=False,
                        library_name=None,
                        via_barrel=via_barrel,
                    )
                if rec.is_external:
                    lib = rec.module_path.split(".")[0] if rec.module_path else rec.module_path
                    return ResolveResult(
                        found=True,
                        target_file=None,
                        target_symbol=resolved_sym,
                        confidence=1.0,
                        is_external=True,
                        library_name=lib,
                        via_barrel=False,
                    )

        matches = self._global_defs.get(symbol, [])
        uniq = list({os.path.abspath(m) for m in matches if m != sf})
        if len(uniq) == 1:
            return ResolveResult(
                found=True,
                target_file=uniq[0],
                target_symbol=symbol,
                confidence=0.5,
                is_external=False,
                library_name=None,
                via_barrel=False,
            )
        if len(uniq) > 1:
            return ResolveResult(
                found=True,
                target_file=uniq[0],
                target_symbol=symbol,
                confidence=0.3,
                is_external=False,
                library_name=None,
                via_barrel=False,
            )

        return ResolveResult(
            found=False,
            target_file=None,
            target_symbol=symbol,
            confidence=0.0,
            is_external=False,
            library_name=None,
            via_barrel=False,
        )

    # ------------------------------------------------------------------
    # Module path resolution
    # ------------------------------------------------------------------

    def _resolve_module(self, rec: ImportRecord, symbol: str) -> tuple[Optional[str], bool, float]:
        if rec.is_relative:
            return self._resolve_relative(rec, symbol)
        return self._resolve_absolute(rec, symbol)

    def _resolve_relative(self, rec: ImportRecord, symbol: str) -> tuple[Optional[str], bool, float]:
        base = os.path.dirname(rec.source_file)
        if rec.module_path.startswith(".."):
            parts = rec.module_path.split("/")
            cur = base
            for p in parts:
                if p == "..":
                    cur = os.path.dirname(cur)
                elif p and p != ".":
                    cur = os.path.join(cur, p)
            candidate = cur
        else:
            rel = rec.module_path.lstrip(".").replace("/", os.sep)
            candidate = os.path.normpath(os.path.join(base, rel))

        py = candidate + ".py"
        init_py = os.path.join(candidate, "__init__.py")
        if os.path.isfile(py):
            return py, False, 1.0
        if os.path.isdir(candidate) and os.path.isfile(init_py):
            barrel = self._is_python_barrel(init_py, symbol)
            return init_py, barrel, 0.8 if barrel else 1.0
        for ext in (".js", ".ts", ".tsx", ".jsx"):
            fe = candidate + ext
            if os.path.isfile(fe):
                return fe, False, 1.0
        for idx_name in ("index.ts", "index.js"):
            idx = os.path.join(candidate, idx_name)
            if os.path.isfile(idx):
                barrel = self._is_js_barrel(idx, symbol)
                if barrel:
                    return idx, True, 0.8
        return candidate + ".py", False, 0.5

    def _resolve_absolute(self, rec: ImportRecord, symbol: str) -> tuple[Optional[str], bool, float]:
        mod_parts = rec.module_path.replace("/", ".").split(".")
        pkg_dir = os.path.join(self.repo_root, *mod_parts)

        py = pkg_dir + ".py"
        if os.path.isfile(py):
            return py, False, 1.0

        init_f = os.path.join(pkg_dir, "__init__.py")
        if os.path.isfile(init_f):
            barrel = self._is_python_barrel(init_f, symbol)
            return init_f, barrel, 0.8 if barrel else 1.0

        for ext in (".js", ".ts", ".tsx", ".jsx"):
            if os.path.isfile(pkg_dir + ext):
                return pkg_dir + ext, False, 1.0
        for idx_name in ("index.ts", "index.js"):
            idx = os.path.join(pkg_dir, idx_name)
            if os.path.isfile(idx) and self._is_js_barrel(idx, symbol):
                return idx, True, 0.8

        top = mod_parts[0] if mod_parts else rec.module_path
        top_py = os.path.join(self.repo_root, top + ".py")
        if os.path.isfile(top_py):
            return top_py, False, 1.0

        return None, False, 0.0

    # ------------------------------------------------------------------
    # Barrel detection
    # ------------------------------------------------------------------

    def _is_python_barrel(self, init_path: str, symbol: str) -> bool:
        try:
            with open(init_path, encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=init_path)
        except (SyntaxError, OSError):
            return False
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    name = alias.asname or alias.name
                    if name == symbol or alias.name == symbol:
                        return True
                    if alias.name == "*":
                        return True
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if (alias.asname or alias.name) == symbol:
                        return True
        return False

    def _is_js_barrel(self, index_path: str, symbol: str) -> bool:
        try:
            with open(index_path, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            return False
        for m in _JS_EXPORT_RE.finditer(txt):
            if m.group(1) == symbol:
                return True
        for m in _JS_REEXPORT_RE.finditer(txt):
            names = [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",")]
            if symbol in names:
                return True
        return False

    # ------------------------------------------------------------------
    # Star-import symbol discovery
    # ------------------------------------------------------------------

    def _resolve_star(self, module_file: str, symbol: str) -> bool:
        lower = module_file.lower()
        if lower.endswith(".py"):
            return self._star_exports_python(module_file, symbol)
        if lower.endswith((".js", ".jsx", ".ts", ".tsx")):
            return self._star_exports_js(module_file, symbol)
        return False

    def _star_exports_python(self, path: str, symbol: str) -> bool:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=path)
        except (SyntaxError, OSError):
            return False
        all_list: list[str] | None = None
        top_names: set[str] = set()
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "__all__":
                        if isinstance(stmt.value, (ast.List, ast.Tuple)):
                            all_list = []
                            for elt in stmt.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_list.append(elt.value)
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                top_names.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                top_names.add(stmt.name)
        if all_list is not None:
            return symbol in all_list
        return symbol in top_names

    def _star_exports_js(self, path: str, symbol: str) -> bool:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            return False
        for m in _JS_EXPORT_RE.finditer(txt):
            if m.group(1) == symbol:
                return True
        return False
