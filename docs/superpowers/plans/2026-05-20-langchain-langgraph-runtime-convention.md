# LangChain LangGraph Runtime Convention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the AI runtime layer toward native LangChain and LangGraph conventions while preserving the current API, local smoke path, custom observability, custom eval, and no-LangSmith runtime stance.

**Architecture:** Add LangChain/LangGraph dependencies and registry primitives, then migrate prompts, RAG, and the default agent runtime internally. Keep current custom LLM/embedding contracts as bridge wrappers so existing cache/tests remain stable during this phase.

**Tech Stack:** FastAPI, Pydantic, uv, LangChain, LangGraph, pytest, local fake chat/embedding implementations, existing vector store and observability adapters.

---

## File Map

- Create `app/adapters/langchain/__init__.py`: package marker for LangChain-native adapter factories.
- Create `app/adapters/langchain/chat_models.py`: build `BaseChatModel` instances from settings, including a deterministic local fake model and `init_chat_model` provider path.
- Create `app/adapters/langchain/embeddings.py`: build LangChain `Embeddings`, including deterministic local fake embeddings.
- Create `app/adapters/langchain/bridges.py`: compatibility wrappers from LangChain chat/embedding primitives to existing `LLMClient` and `EmbeddingClient` contracts.
- Create `app/adapters/langgraph/default_graph.py`: compile the default local agent graph.
- Modify `app/core/config.py`: add LangChain-native model settings.
- Modify `app/core/registry.py`: expose LangChain-native primitives while keeping bridge fields.
- Modify `app/bootstrap/application.py`: pass LangChain-native primitives into RAG and agent wiring.
- Modify `app/modules/prompts/schemas.py`: add chat prompt structure fields without breaking existing prompt records.
- Modify `app/modules/prompts/registry.py`: return LangChain `ChatPromptTemplate`/`PromptTemplate`.
- Modify `app/modules/rag/ingestion.py`, `app/modules/rag/retrievers.py`, `app/modules/rag/service.py`: use LangChain `Document`, `Embeddings`, `BaseChatModel`, and prompt templates internally.
- Modify `app/adapters/agents/simple.py`: run the default compiled LangGraph graph instead of a bespoke LLM loop.
- Modify tests under `tests/unit` and `tests/integration`: assert LangChain/LangGraph-native behavior and preserve local smoke.

## Task 1: Dependencies and LangChain Runtime Factories

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `app/core/config.py`
- Modify: `app/core/registry.py`
- Create: `app/adapters/langchain/chat_models.py`
- Create: `app/adapters/langchain/embeddings.py`
- Create: `app/adapters/langchain/bridges.py`
- Test: `tests/unit/adapters/test_langchain_runtime.py`
- Test: `tests/unit/core/test_registry.py`

- [ ] **Step 1: Write failing tests**

Add tests that import the future runtime factories, verify default fake chat/embedding objects satisfy LangChain interfaces, verify registry exposes `chat_model` and `langchain_embeddings`, and verify no `LANGSMITH_*` setting is introduced.

- [ ] **Step 2: Run tests and verify red**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/adapters/test_langchain_runtime.py tests/unit/core/test_registry.py -v`

Expected: fail because `app.adapters.langchain` modules and LangChain dependencies are not present.

- [ ] **Step 3: Add dependencies and implementation**

Add `langchain>=1.0,<2.0` and `langgraph>=1.0,<2.0`. Implement deterministic local fake `BaseChatModel` and `Embeddings` classes. Add bridge wrappers so current `LLMClient`/`EmbeddingClient` consumers still work.

- [ ] **Step 4: Run tests and verify green**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/adapters/test_langchain_runtime.py tests/unit/core/test_registry.py -v`

Expected: pass.

## Task 2: Prompt Registry Returns LangChain Prompt Templates

**Files:**
- Modify: `app/modules/prompts/schemas.py`
- Modify: `app/modules/prompts/registry.py`
- Test: `tests/unit/modules/test_prompt_registry.py`

- [ ] **Step 1: Write failing tests**

Add tests for `registry.get_langchain_prompt("rag.answer")` returning `ChatPromptTemplate`, and for string prompts returning LangChain `PromptTemplate`.

- [ ] **Step 2: Run tests and verify red**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/modules/test_prompt_registry.py -v`

Expected: fail because the new LangChain prompt accessors do not exist.

- [ ] **Step 3: Implement prompt schema and registry support**

Add `template_type` and optional `messages` fields to prompt records. Keep existing `render()` compatibility. Add methods returning LangChain prompt templates.

- [ ] **Step 4: Run tests and verify green**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/modules/test_prompt_registry.py -v`

Expected: pass.

## Task 3: RAG Uses LangChain Documents, Embeddings, Chat Model, and Runnable Prompt Flow

**Files:**
- Modify: `app/modules/rag/ingestion.py`
- Modify: `app/modules/rag/retrievers.py`
- Modify: `app/modules/rag/service.py`
- Modify: `app/bootstrap/application.py`
- Modify: `research/evaluation/run_rag_smoke.py`
- Test: `tests/unit/modules/test_rag.py`
- Test: `tests/unit/modules/test_eval.py`
- Test: `tests/integration/test_ai_capabilities.py`

- [ ] **Step 1: Write failing tests**

Add tests that RAG stores LangChain `Document` metadata shape, uses LangChain `Embeddings`, and exposes a `rag.answer_chain` runnable. Preserve tests for redaction, reranking, usage, and API output shape.

- [ ] **Step 2: Run tests and verify red**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/modules/test_rag.py tests/unit/modules/test_eval.py tests/integration/test_ai_capabilities.py -v`

Expected: fail because RAG still depends on custom embedding and LLM contracts internally.

- [ ] **Step 3: Implement LangChain-native RAG internals**

Use LangChain `Document` for chunk payloads, `Embeddings.aembed_documents` and `Embeddings.aembed_query`, `ChatPromptTemplate` for prompt construction, and `BaseChatModel.ainvoke` for answer generation. Keep existing Pydantic API schemas and vector store adapter.

- [ ] **Step 4: Run tests and verify green**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/modules/test_rag.py tests/unit/modules/test_eval.py tests/integration/test_ai_capabilities.py -v`

Expected: pass.

## Task 4: Default Agent Runtime Uses a Compiled LangGraph Graph

**Files:**
- Create: `app/adapters/langgraph/default_graph.py`
- Modify: `app/adapters/agents/simple.py`
- Modify: `app/core/registry.py`
- Test: `tests/unit/adapters/test_agent_runtimes.py`

- [ ] **Step 1: Write failing tests**

Add tests that the default simple agent runtime has a compiled graph and returns `AgentResponse` through graph invocation.

- [ ] **Step 2: Run tests and verify red**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/adapters/test_agent_runtimes.py -v`

Expected: fail because the simple runtime still runs a custom loop.

- [ ] **Step 3: Implement default graph**

Create a small `StateGraph` with one model node. The graph receives messages/task/input, calls the configured LangChain chat model, and returns normalized output. Keep custom usage tracking and observability in the runtime wrapper.

- [ ] **Step 4: Run tests and verify green**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/adapters/test_agent_runtimes.py -v`

Expected: pass.

## Task 5: No-LangSmith Guardrails and Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/unit/test_langsmith_absence.py`

- [ ] **Step 1: Write failing guardrail tests**

Add tests asserting no `LANGSMITH` env vars appear in `.env.example` or README and no first-party source imports `langsmith`.

- [ ] **Step 2: Run guardrail test**

Run: `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/test_langsmith_absence.py -v`

Expected: pass once the codebase has no LangSmith configuration or imports.

- [ ] **Step 3: Run full verification**

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run ruff check .
make test
make eval-smoke
UV_CACHE_DIR=.uv-cache uv run pre-commit run --all-files
UV_CACHE_DIR=.uv-cache uv lock --check
UV_CACHE_DIR=.uv-cache uv run python -m compileall app tests research alembic
make docker-build
```

Expected: all commands pass.

- [ ] **Step 4: Commit**

Commit message: `feat: adopt langchain runtime conventions`
