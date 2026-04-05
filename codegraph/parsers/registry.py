"""Routes files to parsers by extension. Does not parse file contents itself."""

from __future__ import annotations

import logging
import os
from typing import Optional

from codegraph.config import CONFIG
from codegraph.core.node import BaseNode, Language
from codegraph.core.parser_base import BaseParser

EXTENSION_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".go": Language.GO,
    ".java": Language.JAVA,
}

log = logging.getLogger("codegraph.registry")


class ParserRegistry:
    """Maintains parsers and dispatches by file extension."""

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        for p in self._parsers:
            if p.can_parse(file_path):
                return p
        return None

    def detect_language(self, file_path: str) -> Language:
        _, ext = os.path.splitext(file_path)
        return EXTENSION_MAP.get(ext.lower(), Language.UNKNOWN)

    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        abs_path = os.path.abspath(file_path)
        try:
            size_kb = os.path.getsize(abs_path) // 1024
        except OSError:
            size_kb = 0
        if size_kb > CONFIG.max_file_size_kb:
            log.warning("Skipping %s: size %s KB exceeds max %s KB", abs_path, size_kb, CONFIG.max_file_size_kb)
            return []
        parser = self.get_parser(abs_path)
        if parser is None:
            log.warning("No parser for file: %s", abs_path)
            return []
        log.debug("Parsing file: %s", abs_path)
        return parser.parse_file(abs_path, repo, git_hash)
