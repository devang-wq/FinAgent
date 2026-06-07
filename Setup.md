# FinAgent — Setup Guide

## Operation Types

| Operation | When to run |
| --- | --- |
| **First-time setup** | Once on a new machine or after a full teardown (`down -v`) |
| **Pull LLM models** | Once — models persist in the `ollama_data` volume |
| **Sanctions ingest** | Once, then only to refresh the OpenSanctions dataset |
| **Document ingest** | Once for the initial corpus, then periodically (weekly/monthly) |
| **Start the stack** | Every time you want to run FinAgent |

---

## Prerequisites

| Requirement | Minimum | Notes |
| --- | --- | --- |
| Docker Desktop | 4.x | Enable WSL 2 backend on Windows |
| Docker Compose | v2 (`docker compose`) | Included with Docker Desktop |
| RAM | 16 GB | 24 GB recommended for qwen3:30b-a3b |
| Disk | 40 GB free | Models ~27 GB + data volumes ~5 GB |
| GPU | Optional | Ollama uses CPU if no CUDA GPU is detected |

---

## Scripts

All operational scripts live in `scripts/`. Make them executable once:

```bash
chmod +x scripts/*.sh
```

| Script | Purpose |
| --- | --- |
| `scripts/setup.sh` | **First-time setup** — builds images, starts services, pulls models, runs both ingestors |
| `scripts/start.sh` | **Regular startup** — full stack, skips one-shot containers |
| `scripts/stop.sh` | Stop services (`--reset` to wipe volumes, `--chat` / `--api` for partial stop) |
| `scripts/start-chat.sh` | Chat UI only — WebUI + LiteLLM + Ollama (no compliance tools) |
| `scripts/start-api.sh` | API + backend — compliance API without the chat UI |
| `scripts/start-infra.sh` | Infrastructure only — data stores + Ollama, no app layer |
| `scripts/pull-models.sh` | Pull Ollama models (`--embed-only` for nomic-embed-text only) |
| `scripts/ingest-sanctions.sh` | Run the OpenSanctions → FalkorDB pipeline |
| `scripts/ingest-docs.sh` | Run the 5-source → OpenSearch pipeline |
| `scripts/ingest-all.sh` | Run both pipelines in order (`--sanctions-only` / `--docs-only` flags) |

---

## Service Groups

| Group | Services included | Use when |
| --- | --- | --- |
| **Chat only** | postgres, ollama, litellm, open-webui | You just want to chat with local LLMs |
| **API + backend** | + redis-stack, opensearch, litellm, api, dashboards | You need the compliance agent and API |
| **Full stack** | All of the above + open-webui | Day-to-day use |
| **Infra only** | redis-stack, opensearch, postgres, ollama | Developing locally or running ingestors |

---

## First-Time Setup

### Quick path (automated)

```bash
cp .env.example .env
# Edit .env — set SEC_USER_AGENT and WEBUI_ADMIN_PASSWORD at minimum
bash scripts/setup.sh
```

`setup.sh` runs all steps below in order. Pass `--skip-ingest` to stop after starting services and run ingestion separately later.

---

### Manual steps

#### 1. Create `.env`

```bash
cp .env.example .env
```

Minimum required values:

```bash
LITELLM_MASTER_KEY=sk-finagent-local       # any string — API key for LiteLLM
WEBUI_ADMIN_PASSWORD=change-me-now         # Open WebUI admin login
SEC_USER_AGENT=FinAgent/1.0 you@email.com  # SEC requires a real contact email
```

Optional:

```bash
ANTHROPIC_API_KEY=sk-ant-...       # enables Claude models via LiteLLM
COURTLISTENER_TOKEN=...            # raises CourtListener API rate limit
```

#### 2. Build Docker images

```bash
docker compose build
```

Builds `Dockerfile.api` and `Dockerfile.worker`. The worker image pre-downloads GLiNER model weights (~500 MB) at build time.

> Only needed again if `requirements.txt` or a Dockerfile changes.

#### 3. Start infrastructure

```bash
bash scripts/start-infra.sh
```

Starts FalkorDB, OpenSearch, Postgres, and Ollama. Waits for all health checks.

#### 4. Pull LLM models *(one-time, ~27 GB)*

```bash
bash scripts/pull-models.sh
```

Downloads into the `ollama_data` volume:

- `qwen3:30b-a3b` — primary chat model (~19 GB)
- `gemma3:12b` — fallback (~8 GB)
- `nomic-embed-text` — embeddings (~270 MB)

> Models persist across restarts. If only the embedding model is missing, use `bash scripts/pull-models.sh --embed-only`.

#### 5. Start LiteLLM and app services

```bash
docker compose up -d litellm
# wait for healthy, then:
docker compose up -d opensearch-dashboards api open-webui
```

#### 6. Ingest sanctions graph *(one-time, ~30–60 min)*

```bash
bash scripts/ingest-sanctions.sh
```

Downloads the OpenSanctions dataset (~2 GB JSONL) and loads it into FalkorDB. The file is cached in `sanctions_data` — re-runs skip the download.

> Re-run only when you want a fresh copy of the OpenSanctions dataset.

#### 7. Ingest document corpus *(one-time, ~20–40 min)*

```bash
bash scripts/ingest-docs.sh
```

Fetches from SEC EDGAR, CourtListener, ICIJ, USASpending, and GDELT in parallel. Chunks, embeds, and indexes into OpenSearch. Idempotent — already-indexed documents are skipped.

> Re-run periodically (weekly/monthly) to pick up new filings and news.

---

## Regular Startup

```bash
bash scripts/start.sh          # full stack
# or specific groups:
bash scripts/start-chat.sh     # chat UI only
bash scripts/start-api.sh      # API + backend, no chat UI
bash scripts/start-infra.sh    # data stores only
```

## Shutdown

```bash
bash scripts/stop.sh           # stop all, keep data
bash scripts/stop.sh --reset   # stop all AND delete volumes (full wipe)
bash scripts/stop.sh --chat    # stop chat services only
bash scripts/stop.sh --api     # stop API + backend only
```

---

## Service URLs

| Service | URL | Credentials |
| --- | --- | --- |
| Chat UI (Open WebUI) | <http://localhost:3001> | `admin@local.host` / `WEBUI_ADMIN_PASSWORD` |
| Compliance API (docs) | <http://localhost:8000/docs> | — |
| LiteLLM proxy | <http://localhost:4000> | Bearer `LITELLM_MASTER_KEY` |
| FalkorDB browser | <http://localhost:3000> | — |
| OpenSearch Dashboards | <http://localhost:5601> | — |
| Ollama | <http://localhost:11434> | — |
| **Grafana (observability)** | <http://localhost:3100> | anonymous / no login |

---

## Quick Reference

| Task | Command |
| --- | --- |
| First-time setup | `bash scripts/setup.sh` |
| Start full stack | `bash scripts/start.sh` |
| Stop everything | `bash scripts/stop.sh` |
| Full reset (wipe data) | `bash scripts/stop.sh --reset` then `bash scripts/setup.sh` |
| Refresh sanctions data | `bash scripts/ingest-sanctions.sh` |
| Refresh document corpus | `bash scripts/ingest-docs.sh` |
| Pull embedding model only | `bash scripts/pull-models.sh --embed-only` |
| View logs | `docker compose logs -f <service>` |
| Rebuild after code changes | `docker compose build && docker compose up -d api` |
| Open Grafana | <http://localhost:3100> |
| Run eval suite | `docker compose run --rm eval-runner` |
| Run evals locally | `python -m eval.runner` |
| Check chunk count in OpenSearch | `curl -s http://localhost:9200/fintech-docs/_count` |
| Check FalkorDB node/edge counts | See FalkorDB browser at <http://localhost:3000> |

---

## Observability

### Grafana dashboards

`otel-lgtm` runs Grafana, Prometheus, Loki, and Tempo in one container.  All Python
services send OTel traces, metrics, and logs to it automatically when running inside
Docker.

```bash
# Open Grafana (no login required — anonymous access enabled)
open http://localhost:3100
```

Two custom dashboards are pre-provisioned:

| Dashboard | URL path | What it shows |
| --- | --- | --- |
| FinAgent — Overview | `/d/finagent-overview` | LLM / embed / graph latency, ingest rate, circuit breaker events |
| FinAgent — Evals | `/d/finagent-evals` | RAGAS scores, hallucination rate, per-run history |

---

## Evals

Run the eval suite after ingestion to measure answer quality.  The eval runner calls
the live `/search` and `/chat` API endpoints, judges each response with an LLM, then
computes RAGAS metrics and exports scores to Grafana.

```bash
# Inside Docker (requires api + otel-lgtm running):
docker compose run --rm eval-runner

# Locally (requires venv with requirements.txt installed):
python -m eval.runner                        # all 17 test cases
python -m eval.runner --tag sanctions        # only sanctions cases
python -m eval.runner --tag hallucination_trap   # adversarial / no-context cases
python -m eval.runner --api http://api:8000  # point at Docker-network API
```

Scores are printed to stdout and exported to the `finagent.eval.score` OTel gauge,
visible on the **FinAgent — Evals** Grafana dashboard.

| Metric | Source | Healthy range |
| --- | --- | --- |
| Faithfulness | RAGAS | > 0.80 |
| Answer Relevancy | RAGAS | > 0.80 |
| Context Precision | RAGAS | > 0.70 |
| Context Recall | RAGAS | > 0.70 |
| Hallucination Rate | LLM-judge | < 0.10 |

---

## Troubleshooting

### `GRAPH.QUERY` unknown command

`redis/redis-stack:latest` dropped RedisGraph in v7.2. Switch to FalkorDB:

```bash
# docker-compose.yml should have: image: falkordb/falkordb:latest
docker compose rm -f redis-stack && docker compose up -d redis-stack
```

### `GLiNER._from_pretrained() missing proxies / resume_download`

`huggingface_hub >= 0.26` dropped those kwargs. Pin it in `requirements.txt`:

```text
huggingface_hub>=0.23,<0.26
```

Then rebuild: `docker compose build`.

### `ValidationError: extra inputs not permitted`

`.env` contains keys not declared in the `Settings` model. Ensure `core/config.py` has `extra = "ignore"` in its inner `Config` class.

### `Invalid space_type: cosine` (OpenSearch)

OpenSearch FAISS does not support `cosine`. The index mapping in `vector/index_setup.py` must use `engine: nmslib` + `space_type: cosinesimil`. Delete the bad index and recreate:

```bash
curl -X DELETE http://localhost:9200/fintech-docs
docker compose run --rm doc-ingestor
```

### `encoding_format: base64` not supported by Ollama

`drop_params` must be under `litellm_settings:` in `resources/litellm-config.yaml`, not under `general_settings:`. Restart LiteLLM after fixing:

```bash
docker compose restart litellm
```

### `404 Not Found` for `http://ollama:11434/api/embed`

The `nomic-embed-text` model is not pulled. Pull it directly:

```bash
docker exec finagent-ollama ollama pull nomic-embed-text
# or pull all models:
bash scripts/pull-models.sh
```

### ICIJ download returns 403

The ICIJ URL changed. Ensure `ingestion/sources/icij.py` uses `full-oldb.LATEST.zip` (not `full-oldb.zip`) and that the request includes browser-like `User-Agent` and `Referer` headers.

### OpenSearch container unhealthy

Needs `vm.max_map_count` increased (Linux / WSL2 only):

```bash
sudo sysctl -w vm.max_map_count=262144
# Make permanent:
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Ollama out of memory

`qwen3:30b-a3b` needs ~22 GB RAM + VRAM combined. Switch the primary model:

```bash
# In .env:
PRIMARY_MODEL=gemma3-12b
# In resources/litellm-config.yaml, move gemma3-12b to top of model_list
docker compose restart litellm api
```
