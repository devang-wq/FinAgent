# FinAgent — Compliance Intelligence Platform

AML / PEP / sanctions investigation platform combining a knowledge graph
(RedisGraph), a vector store (OpenSearch), and a local LLM (Ollama) into a
single chat-driven research tool.

---

## What it does

- **Entity graph** — OpenSanctions data (PEPs, sanctions, aliases,
  relationships) loaded into RedisGraph as a traversable knowledge graph.
- **Document corpus** — Five external sources (SEC filings, court opinions,
  ICIJ Offshore Leaks, government procurement, news) chunked and embedded
  into OpenSearch with entity span offsets for UI highlighting.
- **Hybrid retrieval** — queries go graph-first (entity extraction → 2-hop
  graph expansion → entity-filtered vector search), not vector-first.
- **Local LLM** — Qwen3-30B-A3B via Ollama, routed through LiteLLM. No
  cloud API required.
- **Chat UI** — Open WebUI connected to LiteLLM so any pulled Ollama model
  is immediately available.

---

## Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                          Browser / Client                        │
└───────────────────────────────┬──────────────────────────────────┘
                                │ HTTP
                ┌───────────────▼───────────────┐
                │          Open WebUI           │  chat frontend
                └───────────────┬───────────────┘
                                │ OpenAI-compatible API
                ┌───────────────▼───────────────┐
                │           LiteLLM             │  model router / proxy
                │  qwen3-30b-a3b (primary)      │
                │  gemma3-12b    (fallback)      │
                │  nomic-embed-text (embeddings) │
                └──────────┬────────────────────┘
                           │
              ┌────────────▼────────────┐
              │     FinAgent API        │  FastAPI
              │   POST /chat            │
              │   POST /search          │
              │   GET  /entity/{id}     │
              │   GET  /entity/{id}/    │
              │         exposure        │
              └──────┬──────────┬───────┘
                     │          │
        ┌────────────▼──┐  ┌────▼──────────────┐
        │ PydanticAI    │  │  RetrievalService  │
        │ ComplianceAgent│  │                   │
        │               │  │ 1. extract entities│
        │  tools:       │  │ 2. graph expand    │
        │  search_docs  │  │ 3. vector search   │
        │  get_entity   │  └──────┬─────────────┘
        │  get_exposure │         │
        │  expand_entity│    ┌────┴──────────────────────┐
        └───────────────┘    │                           │
                             │                           │
              ┌──────────────▼───┐         ┌────────────▼──────────┐
              │   RedisGraph     │         │      OpenSearch        │
              │                  │         │   (kNN vector store)   │
              │  Entity nodes    │         │                        │
              │  Relationships   │         │  source chunks         │
              │  PEP paths       │         │  entity_profile docs   │
              │  Sanction paths  │         │  exposure_profile docs │
              └──────────────────┘         └───────────────────────┘
                       ▲                              ▲
                       │                              │
        ┌──────────────┴──────────┐   ┌──────────────┴──────────────┐
        │  sanctions-ingestor     │   │      doc-ingestor            │
        │                         │   │                              │
        │  OpenSanctions FTM JSON │   │  SEC EDGAR    (10-K/10-Q)   │
        │  → RedisGraph nodes     │   │  CourtListener (opinions)    │
        │    + edges via          │   │  ICIJ Offshore Leaks (CSV)   │
        │    UNWIND Cypher        │   │  USASpending  (contracts)    │
        └─────────────────────────┘   │  GDELT News   (articles)    │
                                      │                              │
                                      │  + profile_builder           │
                                      │    entity_profile docs       │
                                      │    exposure_profile docs     │
                                      └──────────────────────────────┘
```

---

## Tech stack

| Layer             | Technology                | Role                                                        |
| ----------------- | ------------------------- | ----------------------------------------------------------- |
| Chat UI           | Open WebUI                | Browser-based chat, connects to LiteLLM                     |
| LLM gateway       | LiteLLM                   | Routes requests to Ollama; swap models without code changes |
| Chat model        | Qwen3-30B-A3B (Ollama)    | MoE, 3B active params, Apache 2.0, runs on RTX 4060 8 GB    |
| Fallback model    | Gemma-3-12B (Ollama)      | Fits fully in 8 GB VRAM at Q3_K_M                           |
| Embedding model   | nomic-embed-text (Ollama) | Local 768-dim embeddings, no API key                        |
| Agent framework   | PydanticAI                | Thin tool-calling agent, no LangChain                       |
| API               | FastAPI                   | Three routers: chat, entity, search                         |
| Graph DB          | Redis Stack (RedisGraph)  | Entity relationships, PEP/sanction paths                    |
| Vector DB         | OpenSearch 2.13           | kNN HNSW index, entity_ids filter field                     |
| Entity extraction | spaCy + GLiNER            | Hybrid NER; GLiNER higher precision for financial entities  |
| Entity resolution | RapidFuzz                 | Fuzzy match extracted mentions to graph canonical IDs       |

---

## Directory structure

```text
FinAgent/
│
├── apps/
│   ├── api/                    FastAPI application
│   │   ├── main.py             App factory — registers routers
│   │   ├── dependencies.py     lru_cache'd service factories for DI
│   │   └── routers/
│   │       ├── chat.py         POST /chat
│   │       ├── entity.py       GET  /entity/{id}, /entity/{id}/exposure
│   │       └── search.py       POST /search
│   └── worker/
│       ├── ingestion_worker.py Runs all 5 sources, then profile builder
│       └── profile_builder.py  Generates entity/exposure profile documents
│
├── core/
│   ├── config.py               Pydantic-settings — all config from env
│   └── models.py               Shared Pydantic models (Entity, Document, …)
│
├── graph/
│   ├── redis_graph_repository.py  expand_entity, get_pep_paths, …
│   ├── entity_resolver.py         spaCy extract → exact graph lookup → fuzzy
│   └── exposure_service.py        aggregates PEP/sanction paths + risk level
│
├── vector/
│   ├── embeddings.py              embed() via LiteLLM proxy
│   ├── opensearch_repository.py   index_chunk, search, search_by_entities
│   ├── retriever.py               RetrievalService (graph-first hybrid)
│   └── index_setup.py             creates kNN index on first run
│
├── llm/
│   ├── litellm_client.py          Thin OpenAI-compatible client
│   └── agent.py                   PydanticAI Agent + AgentDeps + ComplianceAgent
│
├── tools/                         Pure functions (callable outside agent)
│   ├── search_documents.py
│   ├── get_entity.py
│   ├── get_exposure.py
│   └── expand_entity.py
│
├── ingestion/                     Document corpus pipeline
│   ├── chunking.py                Sentence-boundary chunker (1200 chars, 200 overlap)
│   ├── entity_extraction.py       spaCy + GLiNER hybrid extractor
│   ├── enrichment.py              Resolves mentions → graph IDs, adds span offsets
│   ├── pipeline.py                Async batch pipeline with checkpointing
│   └── sources/
│       ├── sec.py                 SEC EDGAR full-text search (10-K/10-Q/8-K)
│       ├── courtlistener.py       CourtListener REST API
│       ├── icij.py                ICIJ Offshore Leaks bulk CSV
│       ├── procurement.py         USASpending.gov contracts API
│       └── news.py                GDELT Doc API
│
├── ingestion-pipelines/           OpenSanctions → RedisGraph (standalone)
│   ├── sanctions-pipeline/
│   │   ├── downloader.py          Downloads entities.ftm.json
│   │   ├── sanctionsParser.py     Parses FTM JSON → nodes + edges
│   │   └── main.py                Streams entities, batches into RedisGraph
│   └── utils/
│       ├── config.py              Env-driven config
│       └── redisWriter.py         UNWIND-batch Cypher writer
│
├── docker/
│   ├── Dockerfile.api             python:3.12-slim + spaCy model
│   └── Dockerfile.worker          same + GLiNER weights pre-downloaded
│
├── resources/
│   └── litellm-config.yaml        Model list + router + global settings
│
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Data pipeline

### 1 — OpenSanctions → RedisGraph

Loads PEP, sanctions, and alias data as a traversable graph.

```text
OpenSanctions FTM JSON
        │
        ▼
sanctionsParser.py         parses entity schema, caption, datasets, properties
        │
        ▼
redisWriter.py             UNWIND-batch GRAPH.QUERY (500 entities per call)
        │
        ▼
RedisGraph "entities"      Entity nodes + typed relationship edges
```

Relationship types written: `OWNS`, `DIRECTOR_OF`, `ASSOCIATED_WITH`,
`PARENT_OF`, `SUBSIDIARY_OF`, `FAMILY_OF`, `MEMBER_OF`, `EMPLOYEE_OF`,
`OPERATES`.

### 2 — 5 sources → OpenSearch

Each source produces `{document_id, title, text, date}` dicts. The pipeline
then:

```text
raw document text
        │
chunking.py                sentence-boundary split, 1200 chars, 200 overlap
        │
entity_extraction.py       spaCy NER merged with GLiNER (financial labels)
        │                  GLiNER degrades to spaCy-only if not installed
enrichment.py              exact graph lookup → fuzzy (RapidFuzz 80%) → create
        │                  adds entity_ids list + mentions [{start,end,id}]
embed()                    nomic-embed-text via LiteLLM → 768-dim vector
        │
OpenSearch bulk index      chunk + embedding + entity_ids + mentions stored
```

Checkpointing: each `document_id` is recorded in Redis
(`ingestion:checkpoints:{source}`). Re-running the worker skips
already-indexed documents.

### 3 — Entity and exposure profiles

After source ingestion, `profile_builder.py` iterates the graph and writes
two additional document types into OpenSearch:

| `doc_type`         | Content                                     | Purpose                                                         |
| ------------------ | ------------------------------------------- | --------------------------------------------------------------- |
| `entity_profile`   | Name, type, datasets, all relationships     | Powers "Tell me about Elon Musk" before any filing mentions him |
| `exposure_profile` | 3-hop connected entities, PEP/sanction flag | Pre-built exposure chain for fast compliance queries            |

---

## Query flow

### Semantic + graph hybrid (typical)

```text
User: "Show all documents related to Elon Musk"
        │
EntityResolver.extract_and_resolve()
        │  spaCy → "Elon Musk" (PERSON)
        │  exact graph lookup → person:elon_musk
        │
RedisGraphRepository.expand_entity(hops=2)
        │  returns: Tesla, SpaceX, xAI, Neuralink, X
        │
OpenSearchRepository.search_by_entities(entity_ids, embedding, k=20)
        │  filter: entity_ids IN [person:elon_musk, org:tesla, org:spacex, …]
        │  rank:   kNN cosine similarity
        │
ComplianceAgent synthesises answer
```

### PEP exposure (graph-only)

```text
User: "What is the PEP exposure of Global Capital Holdings?"
        │
get_exposure tool → ExposureService.get_exposure()
        │
RedisGraph: MATCH p=(e)-[*1..4]-(n {schema:'Position'}) RETURN p
        │
risk_level: HIGH / MEDIUM / LOW   (sanctions → HIGH, PEP path → MEDIUM)
```

### Entity click-through (UI)

Every indexed chunk stores `mentions` — character-offset spans with
`entity_id`. The frontend can render:

```html
<span data-entity-id="person:elon_musk">Elon Musk</span>
```

Clicking calls `GET /entity/person:elon_musk` which returns the full profile
and `GET /entity/person:elon_musk/exposure` for the exposure chain.

---

## Setup

### Prerequisites

- Docker + Docker Compose
- 8 GB VRAM (RTX 4060 or equivalent) + 32 GB RAM
- ~50 GB free disk (models + data)

### 1 — Environment

```bash
cp .env.example .env
# Edit .env:
#   LITELLM_MASTER_KEY — any secret string
#   SEC_USER_AGENT     — your real email (SEC fair-use policy)
#   WEBUI_ADMIN_PASSWORD
```

### 2 — Start infrastructure

```bash
docker compose up -d redis-stack opensearch postgres ollama
```

### 3 — Pull models (one-time, ~20 GB download)

```bash
docker compose run --rm ollama-init
# Pulls: qwen3:30b-a3b, gemma3:12b, nomic-embed-text
```

### 4 — Start LiteLLM proxy

```bash
docker compose up -d litellm
```

### 5 — Ingest OpenSanctions into RedisGraph

```bash
docker compose run --rm sanctions-ingestor
# Downloads entities.ftm.json (~2 GB) and writes to RedisGraph
# Takes 20–40 minutes depending on disk speed
```

### 6 — Ingest document corpus into OpenSearch

```bash
docker compose run --rm doc-ingestor
# Fetches from SEC, CourtListener, ICIJ, USASpending, GDELT
# Builds entity + exposure profiles
# Takes 60–120 minutes
```

### 7 — Start API and UI

```bash
docker compose up -d api open-webui
```

| Service               | URL                                     |
| --------------------- | --------------------------------------- |
| Chat UI (Open WebUI)  | <http://localhost:3001>                 |
| FinAgent API          | <http://localhost:8000>                 |
| API docs (Swagger)    | <http://localhost:8000/docs>            |
| LiteLLM proxy         | <http://localhost:4000>                 |
| RedisInsight          | <http://localhost:8001>                 |
| OpenSearch Dashboards | <http://localhost:5601>                 |

---

## API reference

### `POST /chat`

Natural language query. The agent decides which tools to call.

```json
// request
{ "message": "Show me all documents related to Elon Musk" }

// response
{ "answer": "..." }
```

### `POST /search`

Direct hybrid retrieval — bypasses the agent.

```json
// request
{ "query": "OFAC sanctions violation 2024", "limit": 10 }

// response
{
  "query": "...",
  "entities": [{ "id": "...", "name": "...", "schema_type": "..." }],
  "documents": [{ "id": "...", "text": "...", "entity_ids": [], "score": 0.91 }]
}
```

### `GET /entity/{entity_id}`

Full graph profile for an entity.

```json
{ "entity_id": "person:elon_musk", "data": {} }
```

### `GET /entity/{entity_id}/exposure`

PEP and sanctions exposure chain.

```json
{
  "entity_id": "person:elon_musk",
  "related_entities": [],
  "pep_exposure": [],
  "sanction_exposure": [],
  "risk_level": "LOW"
}
```

---

## Model configuration

All model routing goes through LiteLLM (`resources/litellm-config.yaml`).
No code changes are needed to swap models — only config + env.

### Current setup (zero-cost)

| Purpose    | Model              | VRAM usage                      |
| ---------- | ------------------ | ------------------------------- |
| Chat       | `qwen3:30b-a3b`    | ~8 GB GPU + ~22 GB RAM offload  |
| Fallback   | `gemma3:12b`       | ~6 GB GPU (fully resident)      |
| Embeddings | `nomic-embed-text` | < 1 GB                          |

### To use Claude instead (requires Anthropic API key)

1. Add `ANTHROPIC_API_KEY=sk-ant-...` to `.env`
2. Uncomment the Claude entries in `resources/litellm-config.yaml`
3. Set `PRIMARY_MODEL=claude-haiku` in `.env`
4. Restart: `docker compose restart litellm api`

---

## Re-running ingestion

The document ingestor checkpoints each `document_id` in Redis. Re-running
skips already-indexed documents and only processes new ones.

```bash
# Force full re-ingestion (clears checkpoints)
docker compose run --rm -e FORCE_REINGEST=1 doc-ingestor

# Re-run only profile builder
docker compose run --rm doc-ingestor python -m apps.worker.profile_builder
```

---

## Design decisions

**Graph-first retrieval, not vector-first.**
Vector search alone cannot discover that a query about "Elon Musk" should
also return documents about Tesla, SpaceX, and xAI. The graph expansion step
runs before vector search so the filter set is semantically complete.

**Entity profiles as synthetic documents.**
Profile documents (generated from graph data) are stored in OpenSearch
alongside source chunks. This means the LLM can answer "Tell me about X"
even before any filed document explicitly names X's connections.

**LiteLLM as the only LLM boundary.**
All model calls — chat completions and embeddings — go through LiteLLM.
Swapping from local Ollama to Claude or vice versa is a one-line env change.

**PydanticAI instead of LangChain.**
The agent is ~60 lines. Tools are plain Python functions injected via
`AgentDeps`. No chains, no memory objects, no LCEL.

**GLiNER is optional.**
If the GLiNER package is not installed, `entity_extraction.py` falls back to
spaCy-only NER without raising an error.
