"""Ingestion worker — run once (or on a schedule) to populate OpenSearch.

Runs all 5 sources in parallel then hands off to the profile builder.

Usage:
    python -m apps.worker.ingestion_worker
"""
from __future__ import annotations

import asyncio
import time

from opensearchpy import OpenSearch
from redis import Redis

from core.config import settings
from observability.setup import setup_telemetry
from observability.metrics import docs_ingested, chunks_indexed, ingest_duration
from observability.tracing import get_tracer
from ingestion.entity_extraction import HybridEntityExtractor
from ingestion.enrichment import EntityEnricher
from ingestion.pipeline import IngestionPipeline
from ingestion.sources.sec import fetch_sec_filings
from ingestion.sources.courtlistener import fetch_opinions
from ingestion.sources.icij import fetch_icij_documents
from ingestion.sources.procurement import fetch_contracts
from ingestion.sources.news import fetch_news_articles


def _build_pipeline() -> IngestionPipeline:
    redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )
    os_client = OpenSearch(
        [{"host": settings.opensearch_host, "port": settings.opensearch_port}]
    )
    extractor = HybridEntityExtractor(use_gliner=True)
    enricher = EntityEnricher(redis, extractor)

    print("Warming entity name cache from graph…")
    enricher.warm_cache()

    return IngestionPipeline(redis, os_client, enricher)


async def run() -> None:
    setup_telemetry("finagent-worker")
    tracer = get_tracer()

    pipeline = _build_pipeline()
    t0 = time.time()

    with tracer.start_as_current_span("ingestion.fetch_all"):
        print("Fetching from all 5 sources in parallel…")
        sec_docs, court_docs, icij_docs, procurement_docs, news_docs = await asyncio.gather(
            fetch_sec_filings(days_back=180, max_docs=300),
            fetch_opinions(max_docs=200),
            fetch_icij_documents(max_docs=3_000),
            fetch_contracts(max_docs=500),
            fetch_news_articles(max_docs=500),
        )

    sources = [
        ("sec",            sec_docs),
        ("courtlistener",  court_docs),
        ("icij",           icij_docs),
        ("procurement",    procurement_docs),
        ("news",           news_docs),
    ]

    total = 0
    for source_name, docs in sources:
        print(f"[{source_name}] Ingesting {len(docs)} documents…")
        docs_ingested.add(len(docs), {"source": source_name})
        t_src = time.time()
        with tracer.start_as_current_span(
            "ingestion.run_source", attributes={"source": source_name}
        ):
            n = await pipeline.run_source(source_name, docs)
        chunks_indexed.add(n, {"source": source_name})
        ingest_duration.record(time.time() - t_src, {"source": source_name})
        print(f"[{source_name}] Indexed {n} chunks.")
        total += n

    elapsed = time.time() - t0
    print(f"\nIngestion complete: {total} chunks in {elapsed/60:.1f} minutes.")

    # Build entity + exposure profiles after ingestion
    from apps.worker.profile_builder import ProfileBuilder
    builder = ProfileBuilder(
        Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True),
        OpenSearch([{"host": settings.opensearch_host, "port": settings.opensearch_port}]),
    )
    print("Building entity and exposure profiles…")
    await builder.run()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(run())
