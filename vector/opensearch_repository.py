from __future__ import annotations

from opensearchpy import OpenSearch

from core.config import settings
from core.models import Document


class OpenSearchRepository:
    def __init__(self, client: OpenSearch):
        self.client = client
        self.index = settings.opensearch_index

    def index_chunk(
        self,
        doc_id: str,
        text: str,
        embedding: list[float],
        entity_ids: list[str],
    ) -> None:
        self.client.index(
            index=self.index,
            id=doc_id,
            body={"text": text, "embedding": embedding, "entity_ids": entity_ids},
        )

    def search(self, embedding: list[float], k: int = 10) -> list[Document]:
        body = {
            "size": k,
            "query": {"knn": {"embedding": {"vector": embedding, "k": k}}},
        }
        return self._hits(self.client.search(index=self.index, body=body))

    def search_by_entities(
        self,
        entity_ids: list[str],
        embedding: list[float],
        k: int = 20,
    ) -> list[Document]:
        body = {
            "size": k,
            "query": {
                "bool": {
                    "must": {"knn": {"embedding": {"vector": embedding, "k": k}}},
                    "filter": [{"terms": {"entity_ids": entity_ids}}],
                }
            },
        }
        return self._hits(self.client.search(index=self.index, body=body))

    def _hits(self, result: dict) -> list[Document]:
        return [
            Document(
                id=hit["_id"],
                text=hit["_source"].get("text", ""),
                entity_ids=hit["_source"].get("entity_ids", []),
                score=hit["_score"],
            )
            for hit in result["hits"]["hits"]
        ]
