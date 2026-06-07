# FinAgent — Architecture

FinAgent is a containerized AML/PEP/sanctions compliance research platform. It ingests documents from five public data sources, builds a knowledge graph of entities and relationships, indexes document chunks into a vector store, and exposes a conversational agent that answers compliance questions using hybrid semantic + graph retrieval.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Data Sources                          │
│  SEC EDGAR   CourtListener   ICIJ Offshore Leaks   USASpending   GDELT News │
└──────┬──────────────┬───────────────┬──────────────────┬──────────┬────────┘
       │              │               │                  │          │
       └──────────────┴───────────────┴──────────────────┴──────────┘
                                      │
                             ┌────────▼────────┐
                             │  doc-ingestor   │  (one-shot worker)
                             │  Dockerfile.worker
                             └────────┬────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
      ┌───────▼────────┐    ┌─────────▼──────────┐  ┌────────▼────────┐
      │  spaCy + GLiNER│    │ LiteLLM Proxy :4000│  │  Chunker        │
      │  Entity Extract│    │ (embed via Ollama) │  │  1200 chars     │
      └───────┬────────┘    └─────────┬──────────┘  │  200 overlap    │
              │                       │              └────────┬────────┘
              │              ┌────────▼────────┐             │
              │              │  Embeddings     │             │
              │              │  nomic-embed    │             │
              │              │  768-dim        │             │
              └──────────────┴────────┬────────┴─────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
           ┌────────▼────────┐                ┌────────▼────────┐
           │    FalkorDB     │                │   OpenSearch    │
           │  Graph :6379    │                │  Vector :9200   │
           │  "entities"     │                │  "fintech-docs" │
           │  Nodes + Edges  │                │  KNN HNSW/nmslib│
           └────────┬────────┘                └────────┬────────┘
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      │
                             ┌────────▼────────┐
                             │   FastAPI :8000 │
                             │  /chat          │
                             │  /entity/{id}   │
                             │  /search        │
                             └────────┬────────┘
                                      │
                             ┌────────▼────────┐
                             │ Pydantic-AI Agent│
                             │  4 tools:        │
                             │  search_docs     │
                             │  get_entity      │
                             │  get_exposure    │
                             │  expand_entity   │
                             └────────┬────────┘
                                      │
                             ┌────────▼────────┐
                             │ LiteLLM :4000   │
                             │ qwen3-30b-a3b   │◄── Ollama :11434
                             │ gemma3:12b      │    (local models)
                             │ + optional cloud│◄── Anthropic / etc.
                             └────────┬────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
           ┌────────▼────────┐                ┌────────▼────────┐
           │  Open WebUI     │                │  OpenSearch     │
           │  Chat UI :3001  │                │  Dashboards     │
           │                 │                │  :5601          │
           └─────────────────┘                └─────────────────┘

                    ┌─────────────────────────────────┐
                    │  sanctions-ingestor (one-shot)   │
                    │  OpenSanctions JSONL (~2 GB)     │
                    │  → FalkorDB graph "entities"     │
                    └─────────────────────────────────┘
```

---

## Services

| Service | Image / Build | Ports | Purpose | Lifecycle |
|---|---|---|---|---|
| `redis-stack` | `falkordb/falkordb:latest` | 6379, 3000 | Knowledge graph (FalkorDB) + browser UI | Always up |
| `opensearch` | `opensearchproject/opensearch:2.13.0` | 9200 | Vector store (KNN index) | Always up |
| `opensearch-dashboards` | `opensearchproject/opensearch-dashboards:2.13.0` | 5601 | Index/query visualization | Always up |
| `postgres` | `postgres:16-alpine` | 5432 | LiteLLM request metadata DB | Always up |
| `ollama` | `ollama/ollama:latest` | 11434 | Local LLM runtime | Always up |
| `ollama-init` | `ollama/ollama:latest` | — | Pull models on first start | One-shot |
| `litellm` | `ghcr.io/berriai/litellm:main-latest` | 4000 | LLM gateway (local + cloud) | Always up |
| `api` | `Dockerfile.api` | 8000 | FastAPI compliance API | Always up |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` | 3001 | Chat frontend | Always up |
| `sanctions-ingestor` | `Dockerfile.worker` | — | Load OpenSanctions into FalkorDB | One-shot |
| `doc-ingestor` | `Dockerfile.worker` | — | Fetch 5 sources → chunk → embed → index | One-shot / refresh |

---

## Service Groups

| Group | Services | Script |
|---|---|---|
| Infrastructure | redis-stack, opensearch, postgres, ollama | `start-infra.sh` |
| Chat only | postgres, ollama, litellm, open-webui | `start-chat.sh` |
| API + backend | redis-stack, opensearch, postgres, ollama, litellm, opensearch-dashboards, api | `start-api.sh` |
| Full stack | all of the above + open-webui | `start.sh` |
| Ingest sanctions | sanctions-ingestor | `ingest-sanctions.sh` |
| Ingest documents | doc-ingestor | `ingest-docs.sh` |

---

## Data Stores

### FalkorDB — Knowledge Graph (`entities` graph)

Stores the sanctions and relationship graph loaded from OpenSanctions (~millions of nodes).

| Element | Detail |
|---|---|
| Node label | `Entity` |
| Node properties | `id`, `name`, `schema` (Person/Organization/…), `datasets` |
| Relationship types | `OWNS`, `DIRECTOR_OF`, `ASSOCIATED_WITH`, `PARENT_OF`, `SUBSIDIARY_OF`, `FAMILY_OF`, `MEMBER_OF`, `EMPLOYEE_OF`, `OPERATES` |
| Primary use | Multi-hop expansion, PEP/sanctions path queries, entity enrichment during ingestion |
| Port | 6379 (Redis protocol) |
| Browser UI | http://localhost:3000 |

Sample queries:
```
GRAPH.QUERY entities "MATCH (n) RETURN count(n) AS nodes"
GRAPH.QUERY entities "MATCH ()-[r]->() RETURN count(r) AS edges"
GRAPH.QUERY entities "MATCH (n:Entity) RETURN n.schema, count(n) ORDER BY count(n) DESC"
GRAPH.QUERY entities "MATCH (n:Entity) WHERE toLower(n.name) CONTAINS 'abramovich' OPTIONAL MATCH (n)-[e]-(m) RETURN n,e,m LIMIT 100"
```

> **Note:** FalkorDB replaced `redis/redis-stack` which dropped the RedisGraph module in v7.2. FalkorDB is the community-maintained fork and is drop-in compatible — all `GRAPH.QUERY` commands work unchanged.

### OpenSearch — Vector Index (`fintech-docs`)

Stores document chunks with embeddings and entity annotations.

| Field | Type | Detail |
|---|---|---|
| `chunk_id` | keyword | Unique chunk identifier |
| `document_id` | keyword | Parent document ID |
| `doc_type` | keyword | `chunk`, `entity_profile`, `exposure_profile` |
| `source` | keyword | `sec`, `courtlistener`, `icij`, `procurement`, `news` |
| `title` | text | Document title |
| `text` | text | Chunk content (English analyzer) |
| `entity_ids` | keyword[] | Resolved entity IDs (for filtered KNN) |
| `entity_names` | keyword[] | Resolved entity names |
| `embedding` | knn_vector | 768-dim, cosinesimil, HNSW m=16, nmslib engine |
| `mentions` | nested | Char offset spans for UI highlighting |
| `date` | date | Document date |

Dashboards UI: http://localhost:5601

> **Note:** OpenSearch's FAISS engine does not support `cosine` as a space type. The index uses `nmslib` engine with `cosinesimil`.

---

## Ingestion Pipeline

### Sanctions Graph (one-shot, run before doc ingestion)

```
OpenSanctions JSONL (~2 GB)
  └── downloader.py          stream download via requests
  └── sanctionsParser.py     parse entity + extract relationships
  └── redisWriter.py         UNWIND-based batch Cypher MERGE (500/batch)
  └── FalkorDB               MERGE (e:Entity {id}) + relationship edges
```

### Document Ingestion (one-shot, periodic refresh)

Five sources run in parallel via `asyncio.gather`:

```
SEC EDGAR          10-K/10-Q/8-K, 6 AML search terms, 180 days back, max 300 docs, cap 60K chars
CourtListener      court opinions, 6 queries, optional auth token, max 200 docs, cap 60K chars
ICIJ Offshore Leaks  Panama + Paradise + Pandora Papers, CSV bulk ~250 MB, max 3000 synthetic docs
USASpending.gov    contracts, 5 compliance keywords, max 500 docs
GDELT Doc 2.0      news, 6 AML/sanctions queries, max 500 docs (title+snippet by default)
    │
    ▼
chunk_text()              1200-char sentence-boundary chunks, 200 overlap
    │
    ▼
HybridEntityExtractor     spaCy (7 labels) + GLiNER (8 financial labels)
                          merge: GLiNER preferred on overlap, 0.45 confidence threshold
    │
    ▼
EntityEnricher            exact-match → fuzzy (RapidFuzz 80%) → create new node
                          annotates chunk with entity_ids + mention char spans
    │
    ▼
embed()                   nomic-embed-text via LiteLLM proxy, batch=128
    │
    ▼
OpenSearch bulk index     HNSW KNN, cosinesimil (nmslib)
    │
    ▼
ProfileBuilder            synthetic entity + exposure profile docs
                          bridges graph ↔ semantic search
```

Redis checkpointing (`SADD fintech:ingested:{source}`) makes re-runs idempotent — already-processed document IDs are skipped.

**Approximate data sizes:**

| Source | Docs | Raw text | Chunks | OpenSearch |
| --- | --- | --- | --- | --- |
| SEC EDGAR | 300 | ~12 MB | ~10,000 | ~35 MB |
| CourtListener | 200 | ~9 MB | ~7,000 | ~25 MB |
| ICIJ Offshore Leaks | 3,000 | ~1 MB | ~3,000 | ~12 MB |
| USASpending | 500 | ~150 KB | ~500 | ~5 MB |
| GDELT News | 500 | ~75 KB | ~500 | ~3 MB |
| **Total** | **4,500** | **~22 MB** | **~21,000** | **~80 MB** |

Separate downloads (volumes, not in OpenSearch): ICIJ zip ~250 MB, OpenSanctions JSONL ~2 GB, FalkorDB graph ~500 MB–2 GB.

---

## Query / Chat Flow

```
User question
    │
    ▼
POST /chat  →  ComplianceAgent.answer()
    │
    ▼
Pydantic-AI agent  (system: "compliance analyst for AML/PEP/sanctions…")
    │
    ├── tool: search_documents(query)
    │     └── EntityResolver: spaCy NER → fuzzy graph lookup
    │     └── 2-hop graph expansion for matched entities
    │     └── KNN search filtered by related entity IDs
    │     └── Returns ranked document chunks
    │
    ├── tool: get_entity(entity_id)
    │     └── GRAPH.QUERY → entity node properties
    │
    ├── tool: get_exposure(entity_id)
    │     └── 3-hop expansion + PEP path (4-hop) + sanctions path (4-hop)
    │     └── risk_level: HIGH / MEDIUM / LOW
    │
    └── tool: expand_entity(entity_name)
          └── name → entity_id resolution → 2-hop neighborhood
    │
    ▼
LiteLLM proxy :4000
    └── primary: qwen3:30b-a3b (Ollama, MoE, 3B active params)
    └── fallback: gemma3:12b
    └── optional: claude-haiku / claude-sonnet (ANTHROPIC_API_KEY)
    │
    ▼
Answer text
```

**Sample queries:**

- *"Is Roman Abramovich on any sanctions list? Who are his known associates?"*
- *"What recent SEC filings mention OFAC violations or sanctions breaches?"*
- *"Find offshore entities connected to Oleg Deripaska in the Panama Papers."*
- *"Summarize AML risks disclosed in recent 10-K filings."*

---

## LLM Gateway (LiteLLM)

All model calls — chat completions and embeddings — route through a single LiteLLM proxy. Application code uses the OpenAI client pointed at `http://litellm:4000/v1`; no vendor-specific SDK is imported.

| Model alias | Backend | Notes |
|---|---|---|
| `qwen3-30b-a3b` | `ollama/qwen3:30b-a3b` | Primary. MoE, 30B total / 3B active params. Fits RTX 4060 8 GB + RAM offload. |
| `gemma3-12b` | `ollama/gemma3:12b` | Fallback. Fits 8 GB VRAM at Q3_K_M. |
| `nomic-embed-text` | `ollama/nomic-embed-text` | Embeddings. 768-dim. Fully local. |
| `claude-haiku` | Anthropic API | Optional. Requires `ANTHROPIC_API_KEY`. |
| `claude-sonnet` | Anthropic API | Optional. Requires `ANTHROPIC_API_KEY`. |

Config: `resources/litellm-config.yaml`

> **Note:** `drop_params: true` must be under `litellm_settings:` (not `general_settings:`) in the config. This drops `encoding_format: base64` which the OpenAI SDK sends by default but Ollama does not support.

---

## Code Layout

```
FinAgent/
├── apps/
│   ├── api/                    FastAPI app (routers: chat, entity, search)
│   └── worker/
│       ├── ingestion_worker.py 5-source parallel ingestion orchestrator
│       └── profile_builder.py  Synthetic entity/exposure doc builder
│
├── ingestion/
│   ├── pipeline.py             Chunk → enrich → embed → index loop
│   ├── entity_extraction.py    spaCy + GLiNER hybrid NER
│   ├── enrichment.py           Entity resolution + graph annotation
│   ├── chunking.py             Sentence-boundary chunker
│   └── sources/                One module per data source
│       ├── sec.py
│       ├── courtlistener.py
│       ├── icij.py             ICIJ bulk URL: full-oldb.LATEST.zip
│       ├── procurement.py
│       └── news.py
│
├── ingestion-pipelines/
│   └── sanctions-pipeline/     Standalone OpenSanctions → FalkorDB loader
│       ├── downloader.py
│       ├── sanctionsParser.py
│       └── main.py
│
├── graph/
│   ├── redis_graph_repository.py  Cypher query wrapper
│   ├── entity_resolver.py         NER + fuzzy name resolution
│   └── exposure_service.py        PEP/sanctions risk classification
│
├── vector/
│   ├── embeddings.py           embed() via LiteLLM
│   ├── index_setup.py          Idempotent OpenSearch index creation (nmslib/cosinesimil)
│   ├── opensearch_repository.py KNN search interface
│   └── retriever.py            Hybrid search orchestrator
│
├── llm/
│   ├── agent.py                Pydantic-AI compliance agent + 4 tools
│   └── litellm_client.py       OpenAI SDK wrapper for LiteLLM proxy
│
├── tools/                      Agent tool implementations
│   ├── search_documents.py
│   ├── get_entity.py
│   ├── get_exposure.py
│   └── expand_entity.py
│
├── core/
│   ├── config.py               Pydantic Settings (env-driven, extra="ignore")
│   └── models.py               Shared data models
│
├── docker/
│   ├── Dockerfile.api          python:3.12-slim + requirements
│   └── Dockerfile.worker       python:3.12-slim + gcc/lxml + GLiNER weights pre-cached
│
├── resources/
│   └── litellm-config.yaml     Model routing + fallback + drop_params config
│
└── scripts/                    Operational scripts
    ├── setup.sh                First-time setup (all steps)
    ├── start.sh                Regular full-stack startup
    ├── stop.sh                 Stop services (with --reset, --chat, --api modes)
    ├── start-chat.sh           Chat UI only (no compliance tools)
    ├── start-api.sh            API + backend (no chat UI)
    ├── start-infra.sh          Data stores + Ollama only
    ├── pull-models.sh          Pull Ollama models
    ├── ingest-sanctions.sh     Sanctions pipeline
    ├── ingest-docs.sh          Document pipeline
    └── ingest-all.sh           Both pipelines in sequence
```

---

## Key Design Decisions

**No LangChain.** The agent is built on Pydantic-AI with a plain OpenAI-compatible client. Tool calls are typed Python functions.

**LiteLLM as the only LLM boundary.** Swapping models (local ↔ cloud) requires only a change in `litellm-config.yaml`, not application code. `drop_params: true` in `litellm_settings` silently drops unsupported parameters (e.g. `encoding_format: base64`) so Ollama-backed models receive only what they understand.

**FalkorDB instead of redis-stack.** Redis removed RedisGraph from `redis-stack:latest` in version 7.2. FalkorDB is the actively-maintained community fork; `GRAPH.QUERY` commands are drop-in compatible.

**nmslib engine for KNN.** OpenSearch's FAISS engine does not support `cosine` as a space type. The index uses `nmslib` with `cosinesimil` which is semantically equivalent.

**Idempotent ingestion.** Redis sets track ingested document IDs per source. Re-running the worker skips already-processed documents and only indexes new ones.

**Graph-scoped vector search.** When an entity is resolved from the query, retrieval filters the KNN search to chunks already linked to that entity or its 2-hop neighbors — substantially reducing noise versus unfiltered semantic search.
