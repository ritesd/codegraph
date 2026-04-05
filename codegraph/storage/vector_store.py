"""Optional vector DB bridge (Qdrant / Chroma). Caller supplies embeddings."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from codegraph.config import CodeGraphConfig
from codegraph.core.node import BaseNode

log = logging.getLogger("codegraph")

EMBEDDING_DIM = 768


class VectorStore:
    """Upsert / search / delete node embeddings in Qdrant or Chroma."""

    def __init__(self, config: CodeGraphConfig) -> None:
        self.config = config
        self._qdrant_client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.vector_db_url)

    def _get_qdrant(self) -> Any:
        if self._qdrant_client is None:
            from qdrant_client import QdrantClient  # noqa: PLC0415

            self._qdrant_client = QdrantClient(url=self.config.vector_db_url)
        return self._qdrant_client

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams  # noqa: PLC0415

        client = self._get_qdrant()
        name = self.config.vector_collection
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            log.info("Created Qdrant collection '%s' (dim=%d)", name, EMBEDDING_DIM)

    @staticmethod
    def _node_payload(node: BaseNode) -> dict[str, Any]:
        return {
            "node_id": node.id,
            "name": node.name,
            "node_type": node.node_type.value,
            "language": node.language.value,
            "file_path": node.file_path,
            "repo": node.repo,
            "docstring": node.docstring or "",
            "summary": node.summary or "",
        }

    def upsert_node(self, node: BaseNode, embedding: list[float]) -> None:
        if not self.enabled:
            return
        vtype = (self.config.vector_db_type or "").lower()
        try:
            if vtype == "qdrant":
                self._upsert_qdrant(node, embedding)
            elif vtype == "chroma":
                log.warning("Chroma upsert not yet implemented; skipped")
            else:
                log.warning("Unknown vector_db_type '%s'; skipped", vtype)
        except ImportError as ex:
            log.warning("Vector DB library missing: %s", ex)
        except Exception as ex:  # noqa: BLE001
            log.warning("Vector upsert failed for node %s: %s", node.id, ex)

    def _upsert_qdrant(self, node: BaseNode, embedding: list[float]) -> None:
        from qdrant_client.models import PointStruct  # noqa: PLC0415

        self._ensure_collection()
        client = self._get_qdrant()
        point = PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, node.id)),
            vector=embedding,
            payload=self._node_payload(node),
        )
        client.upsert(
            collection_name=self.config.vector_collection,
            points=[point],
        )

    def upsert_batch(self, nodes: list[BaseNode], embeddings: list[list[float]]) -> int:
        """Bulk upsert; returns count of successfully stored vectors."""
        if not self.enabled:
            return 0
        vtype = (self.config.vector_db_type or "").lower()
        if vtype != "qdrant":
            log.warning("Batch upsert only implemented for qdrant; skipped")
            return 0
        try:
            from qdrant_client.models import PointStruct  # noqa: PLC0415

            self._ensure_collection()
            client = self._get_qdrant()
            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, n.id)),
                    vector=emb,
                    payload=self._node_payload(n),
                )
                for n, emb in zip(nodes, embeddings)
                if emb is not None
            ]
            if points:
                client.upsert(
                    collection_name=self.config.vector_collection,
                    points=points,
                )
            return len(points)
        except Exception as ex:  # noqa: BLE001
            log.warning("Batch vector upsert failed: %s", ex)
            return 0

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        if not self.enabled:
            return []
        vtype = (self.config.vector_db_type or "").lower()
        if vtype != "qdrant":
            return []
        try:
            client = self._get_qdrant()
            query_filter = None
            if filters:
                from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

                conditions = [
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filters.items()
                ]
                query_filter = Filter(must=conditions)

            results = client.query_points(
                collection_name=self.config.vector_collection,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
            )
            return [
                {
                    "score": hit.score,
                    "node_id": hit.payload.get("node_id", ""),
                    "name": hit.payload.get("name", ""),
                    "node_type": hit.payload.get("node_type", ""),
                    "file_path": hit.payload.get("file_path", ""),
                    "repo": hit.payload.get("repo", ""),
                }
                for hit in results.points
            ]
        except Exception as ex:  # noqa: BLE001
            log.warning("Vector search failed: %s", ex)
            return []

    def delete_by_repo(self, repo: str) -> None:
        if not self.enabled:
            return
        vtype = (self.config.vector_db_type or "").lower()
        if vtype != "qdrant":
            return
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

            client = self._get_qdrant()
            client.delete(
                collection_name=self.config.vector_collection,
                points_selector=Filter(
                    must=[FieldCondition(key="repo", match=MatchValue(value=repo))]
                ),
            )
            log.info("Deleted vectors for repo '%s'", repo)
        except Exception as ex:  # noqa: BLE001
            log.warning("Vector delete_by_repo failed: %s", ex)

    def collection_info(self) -> dict[str, Any]:
        """Return collection stats (useful for diagnostics)."""
        if not self.enabled:
            return {"enabled": False}
        vtype = (self.config.vector_db_type or "").lower()
        if vtype != "qdrant":
            return {"enabled": True, "type": vtype, "status": "not implemented"}
        try:
            client = self._get_qdrant()
            name = self.config.vector_collection
            if not client.collection_exists(name):
                return {"enabled": True, "type": "qdrant", "collection": name, "exists": False}
            info = client.get_collection(name)
            return {
                "enabled": True,
                "type": "qdrant",
                "collection": name,
                "exists": True,
                "points_count": info.points_count,
                "vectors_count": info.indexed_vectors_count,
                "status": info.status.value if hasattr(info.status, "value") else str(info.status),
            }
        except Exception as ex:  # noqa: BLE001
            return {"enabled": True, "type": "qdrant", "error": str(ex)}
