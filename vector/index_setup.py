from opensearchpy import OpenSearch

from core.config import settings


def create_fintech_index(client: OpenSearch) -> None:
    """Idempotent — safe to call on every startup."""
    if client.indices.exists(index=settings.opensearch_index):
        return

    client.indices.create(
        index=settings.opensearch_index,
        body={
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 512,
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                }
            },
            "mappings": {
                "properties": {
                    "chunk_id":      {"type": "keyword"},
                    "document_id":   {"type": "keyword"},
                    "doc_type":      {"type": "keyword"},
                    "source":        {"type": "keyword"},
                    "date":          {"type": "date", "format": "yyyy-MM-dd||epoch_millis||strict_date_optional_time"},
                    "title":         {"type": "text"},
                    "text":          {"type": "text", "analyzer": "english"},
                    "entity_ids":    {"type": "keyword"},
                    "entity_names":  {"type": "keyword"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": settings.embedding_dimensions,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {"m": 16, "ef_construction": 256},
                        },
                    },
                    # span offsets for UI entity highlighting
                    "mentions": {
                        "type": "nested",
                        "properties": {
                            "start":       {"type": "integer"},
                            "end":         {"type": "integer"},
                            "entity_id":   {"type": "keyword"},
                            "entity_name": {"type": "keyword"},
                        },
                    },
                }
            },
        },
    )
    print(f"Created OpenSearch index: {settings.opensearch_index}")
