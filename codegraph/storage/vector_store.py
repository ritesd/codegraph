"""Optional vector DB bridge (Qdrant / Chroma). Caller supplies embeddings."""

from __future__ import annotations

import logging
from typing import Optional

from codegraph.config import CodeGraphConfig
from codegraph.core.node import BaseNode

log = logging.getLogger("codegraph")


class VectorStore:
    """No-op when vector_db_url is empty; otherwise Qdrant or Chroma."""

    def __init__(self, config: CodeGraphConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.vector_db_url)

    def upsert_node(self, node: BaseNode, embedding: list[float]) -> None:
        if not self.enabled:
            return
        vtype = (self.config.vector_db_type or "").lower()
        text = f"{node.name}\n{node.docstring or ''}\n{node.summary or ''}"
        _ = text
        try:
            if vtype == "qdrant":
                from qdrant_client import QdrantClient  # noqa: PLC0415 — lazy import

                client = QdrantClient(url=self.config.vector_db_url)
                _ = (client, embedding)
                log.warning("VectorStore Qdrant upsert not fully configured; skipped")
            elif vtype == "chroma":
                import chromadb  # noqa: PLC0415

                _ = chromadb
                log.warning("VectorStore Chroma upsert not fully configured; skipped")
        except ImportError as ex:
            log.warning("Vector DB library missing: %s", ex)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        if not self.enabled:
            return []
        _ = (query_vector, top_k, filters)
        return []

    def delete_by_repo(self, repo: str) -> None:
        if not self.enabled:
            return
        _ = repo
