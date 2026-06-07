from __future__ import annotations

import time

from graph.entity_resolver import EntityResolver
from graph.redis_graph_repository import RedisGraphRepository
from vector.embeddings import embed
from vector.opensearch_repository import OpenSearchRepository
from core.models import SearchResult
from observability.metrics import search_duration
from observability.tracing import get_tracer


class RetrievalService:
    def __init__(
        self,
        graph_repo: RedisGraphRepository,
        vector_repo: OpenSearchRepository,
        entity_resolver: EntityResolver,
    ):
        self.graph = graph_repo
        self.vector = vector_repo
        self.resolver = entity_resolver

    def search(self, query: str, limit: int = 10) -> SearchResult:
        tracer = get_tracer()
        t0 = time.time()
        with tracer.start_as_current_span("retrieval.search") as span:
            span.set_attribute("query.length", len(query))

            entities = self.resolver.extract_and_resolve(query)
            span.set_attribute("entities.count", len(entities))

            related_ids: list[str] = []
            for entity in entities:
                expanded = self.graph.expand_entity(entity.id)
                related_ids.extend(e.id for e in expanded)

            if not related_ids:
                related_ids = [e.id for e in entities]

            embedding = embed(query)

            if related_ids:
                docs = self.vector.search_by_entities(related_ids, embedding, k=limit)
            else:
                docs = self.vector.search(embedding, k=limit)

            span.set_attribute("docs.returned", len(docs))
            search_duration.record(time.time() - t0)
            return SearchResult(query=query, entities=entities, documents=docs)
