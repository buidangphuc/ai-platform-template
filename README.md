# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, local data services, and feedback/evaluation capture points clean so project-specific AI product code can be added without inheriting old business coupling.

## Scope

This repository currently covers the local application foundation:

- Import-safe FastAPI app factory.
- Pydantic settings and `.env` workflow.
- Health/readiness endpoints.
- Request ID middleware, logging context, and standard error envelope.
- API key bootstrap and authentication.
- Fixed-window rate limiting foundation.
- Feedback capture schema and endpoint.
- Adapter contracts for LLM, embeddings, vector store, storage, jobs, observability, and LLM response caching.
- Fake/local default adapters for local development and tests.
- Prompt registry, RAG, RAG evaluation, usage tracking, redaction policy, and simple agent runtime.
- Research workspace with sample datasets, artifact manifests, smoke evals, and local experiment tracking.
- PostgreSQL model metadata with Alembic.
- Local Docker build/run path.

Deployment pipelines are intentionally out of scope. Each team or client environment can bring its own deployment platform.

## Requirements

- Python 3.12+
- uv
- Docker and Docker Compose for local container checks

## Quickstart

```bash
cp .env.example .env
uv sync --dev
make test
make dev
```

The API starts on `http://localhost:8000`.

Useful endpoints:

- `GET /health`
- `GET /ready`
- `POST /api/v1/auth/api-keys`
- `GET /api/v1/auth/me`
- `POST /api/v1/feedback`
- `POST /api/v1/rag/index`
- `POST /api/v1/rag/search`
- `POST /api/v1/rag/answer`
- `POST /api/v1/evals/rag`
- `POST /api/v1/agents/run`

All `/api/v1/*` platform endpoints except health and API-key bootstrap require
`Authorization: Bearer <api-key>`.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-run
```

The Docker path is a local golden path only. It builds the API image and runs the API, PostgreSQL, and Redis with `docker-compose.local.yaml`.

## Project Layout

```text
app/
  api/                  Versioned FastAPI routers
  adapters/             Fake/local and provider adapter implementations
  bootstrap/            App factory and service wiring
  contracts/            typing.Protocol adapter contracts and payload models
  core/                 Settings, database, Redis, errors, logging, health
  modules/
    feedback/           Feedback schema, model, and repository
    identity/           API key identity model, repository, auth dependency
    prompts/            In-memory prompt registry and default RAG prompt
    rag/                Chunking, ingestion, retrieval, answer generation
    evals/              Local RAG evaluation service
    usage/              In-memory usage/cost/latency records
    rate_limit/         Rate limit service contracts and implementations
alembic/                Migration environment
research/               Datasets, evals, training templates, artifact manifests
ops/                    Local observability and MLOps profile examples
scripts/                Local helper scripts
tests/                  Unit and integration tests
```

## Local Commands

```bash
make dev          # run local API with uvicorn reload
make test         # run full pytest suite
make eval-smoke   # run local RAG evaluation smoke test
make hygiene      # check stale template coupling
```

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git.

## Adapter Defaults

The template boots without cloud credentials. Default providers are fake/local:

- `LLM_PROVIDER=fake`
- `EMBEDDING_PROVIDER=fake`
- `VECTOR_STORE=in_memory`
- `STORAGE_BACKEND=local`
- `JOB_BACKEND=in_process`
- `OBSERVABILITY_BACKEND=debug`
- `LLM_CACHE_BACKEND=noop`
- `AGENT_RUNTIME=simple`
- `EXPERIMENT_TRACKER_BACKEND=local`

To use an OpenAI-compatible API, set `LLM_PROVIDER=openai_compatible` or `EMBEDDING_PROVIDER=openai_compatible`, then provide `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` if that endpoint requires one, and the model setting. `OPENAI_API_KEY` and `OPENAI_BASE_URL` remain supported as OpenAI defaults. The LLM cache wrapper is always wired, but `LLM_CACHE_ENABLED=false` and `LLM_CACHE_BACKEND=noop` by default so cache policy can be added later without changing call sites.

The local OpenTelemetry collector debug profile lives at `ops/observability/otel-collector.debug.yaml`. Set `OBSERVABILITY_BACKEND=otel_debug` and `OTEL_EXPORTER_OTLP_ENDPOINT` to emit OpenTelemetry-style debug records through the app adapter without coupling app code to Grafana, Datadog, Phoenix, or a custom collector.

The default experiment tracker writes JSON records under `research/experiments/local`. The optional MLflow profile is documented in `ops/mlops/mlflow.local.env.example`; it is import-safe and only requires MLflow when a downstream project enables that adapter.

## Research Workspace

Phase 4 adds a local-first `research/` workspace:

- `research/datasets/samples/rag_smoke.jsonl`
- `research/datasets/schemas/rag_eval_case.schema.json`
- `research/evaluation/run_rag_smoke.py`
- `research/evaluation/metrics/keyword_hit_rate.py`
- `research/training/train_template.py`
- `research/artifacts/sample_prompt_manifest.yaml`

Run the local smoke eval with:

```bash
make eval-smoke
```

The smoke command uses fake/local adapters, writes a report under `research/evaluation/reports/`, and logs a local experiment under `research/experiments/local/`. Generated reports and local tracker runs are ignored by Git.

## AI Capability Smoke

The Phase 3 app includes local-only AI capability endpoints backed by fake/local adapters:

```bash
curl -X POST http://localhost:8000/api/v1/rag/index \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"documents":[{"id":"doc-1","text":"Phase three adds RAG support."}]}'

curl -X POST http://localhost:8000/api/v1/rag/answer \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does phase three add?","top_k":1}'
```

`AGENT_RUNTIME=simple` uses the configured LLM adapter. `AGENT_RUNTIME=langgraph` is import-safe but intentionally requires a downstream project to provide a LangGraph runner.

## API Key Bootstrap

Set `API_KEY_BOOTSTRAP_TOKEN` in `.env`, then create an API key:

```bash
curl -X POST http://localhost:8000/api/v1/auth/api-keys \
  -H "Content-Type: application/json" \
  -H "X-Bootstrap-Token: $API_KEY_BOOTSTRAP_TOKEN" \
  -d '{"name":"local"}'
```

Use the returned key with:

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <api-key>"
```

## Feedback Capture

The feedback endpoint stores lightweight records through an in-memory repository for now. The SQLAlchemy model is present so database persistence can be added later without changing the public payload contract.

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_1",
    "trace_id": "trace_1",
    "target_type": "llm_response",
    "target_id": "resp_1",
    "rating": "negative",
    "labels": ["hallucination"],
    "comment": "Answer cited the wrong source"
  }'
```
