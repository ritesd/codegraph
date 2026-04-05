"""Abstract base class for language-specific parsers.

Defines the parser interface and ImportRecord. Does NOT implement parsing or resolution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from codegraph.core.node import BaseNode


@dataclass
class ImportRecord:
    source_file: str
    module_path: str
    symbols: list[str]
    is_relative: bool
    is_external: bool
    alias: dict[str, str]


class BaseParser(ABC):
    """Minimal interface every language parser implements."""

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Return True if this parser handles the given file extension."""

    @abstractmethod
    def parse_file(self, file_path: str, repo: str, git_hash: str) -> list[BaseNode]:
        """
        Parse a single file. Return flat list of ALL nodes found in the file
        (classes, methods inside classes, standalone functions).
        Do NOT resolve cross-file edges here — that is the resolver's job.
        Each node's `edges` list may contain unresolved call edges with
        target_id set to a TEMPORARY string "unresolved::<symbol_name>".
        The edge resolver will replace these with real node IDs later.
        """

    @abstractmethod
    def extract_imports(self, file_path: str) -> list[ImportRecord]:
        """
        Return all import statements in the file as ImportRecord objects.
        This is called by the edge resolver separately from parse_file.
        """
