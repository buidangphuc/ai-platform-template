# LangChain, LangGraph, and LlamaIndex Runtime Convention Design

Date: 2026-05-20
Status: Superseded by 2026-05-20-simplified-runtime-and-db-session-design.md
Scope: Architecture amendment for the AI runtime layer after phases 1-4.

Current note: this document records the earlier direction. The accepted current
implementation removes the template-owned adapter registry, skips app
observability in this phase, uses LangChain/LlamaIndex directly where useful,
and treats SQLAlchemy `DbSession` as the database extension point.

## 1. Context

The current template rebuilt a clean FastAPI foundation, adapter registry, RAG module, eval smoke path, research workspace, feedback capture, observability contracts, and local MLOps tools.

The first implementation deliberately used internal Protocol/Pydantic contracts for LLM calls, embeddings, RAG, agents, and evals. That made the template stable, but it also introduced a custom AI workflow convention. For an AI solution engineer, this is friction: real project work commonly uses LangChain and LangGraph conventions directly, including chat models, messages, prompt templates, tools, runnables, retrievers, and graph state.

The template should not become a custom AI framework. It should be a FastAPI, MLOps, and LLMOps shell around the conventions AI engineers already expect.

## 2. Decision

Use LangChain, LangGraph, and LlamaIndex conventions as the native convention
inside the AI runtime layer.

Custom Pydantic and Protocol contracts remain valuable at boundaries:

- API request and response payloads.
- Settings and registry configuration.
- Feedback records.
- Usage, latency, cost, and trace event records.
- Cache-key metadata.
- Eval reports and artifact manifests.
- Persistence schemas.
- Infrastructure adapters.

Inside AI workflow code, prefer native ecosystem types:

- `BaseChatModel`
- `init_chat_model`
- LangChain messages such as `HumanMessage`, `AIMessage`, and `ToolMessage`
- `ChatPromptTemplate` and `PromptTemplate`
- `Runnable`
- LangChain `Embeddings`
- LangGraph `StateGraph`, `MessagesState`, compiled graphs, and graph state
- LlamaIndex `Document`
- LlamaIndex `VectorStoreIndex`
- LlamaIndex node parsers, retrievers, and query/LLM primitives for RAG

## 3. LangSmith Decision

Do not use LangSmith in this template.

This means:

- No direct LangSmith dependency chosen by this template.
- No `LANGSMITH_*` environment variables in `.env.example`.
- No LangSmith tracing profile.
- No LangSmith eval upload path.
- No template code imports or calls `langsmith`.
- No LangSmith-specific runtime assumptions.

The template can learn from the ecosystem conventions, but observability and evaluation remain owned by this repository.

Dependency note: if a LangChain package includes LangSmith as a transitive implementation dependency, the template still treats LangSmith as unused. There should be no LangSmith configuration, imports, runtime calls, or golden-path behavior.

## 4. Goals

1. Make AI workflow code familiar to engineers who already know LangChain and LangGraph.
2. Avoid building and teaching a custom LLM framework.
3. Keep the FastAPI app, auth, rate limits, feedback, observability, eval, and research promotion pieces independent from LangSmith or any SaaS tool.
4. Keep the local golden path runnable without cloud accounts.
5. Preserve existing phase 1-4 behavior while migrating internal AI modules incrementally.
6. Keep adapters where they add value: infrastructure, observability export, cache storage, experiment tracking, and artifact promotion.
7. Avoid template-owned adapter-on-adapter layers when LangChain or LlamaIndex already provides the runtime abstraction.

## 5. Non-Goals

1. Do not use LangSmith.
2. Do not require cloud model credentials for tests or local smoke runs.
3. Do not rewrite the entire app around LangChain abstractions.
4. Do not expose LangChain objects in public HTTP API schemas.
5. Do not remove current local fake behavior until LangChain-native fake/test equivalents exist.
6. Do not build a deployment pipeline.
7. Do not build a complete production agent platform.

## 6. Architecture

The architecture has three layers:

```text
API / App Boundary
  FastAPI routes, Pydantic schemas, auth, rate limit, error envelope

AI Runtime Layer
  LangChain models, messages, prompts, tools, runnables
  LangGraph graph factories, compiled graphs, state schemas
  LlamaIndex documents, node parsers, indexes, retrievers, RAG LLM calls

Template Control Plane
  registry, settings, observability adapters, eval runner, feedback,
  usage/cost tracking, cache policy, artifact manifests, research workspace
```

The key rule is:

> LangChain, LangGraph, and LlamaIndex are native inside the AI runtime layer,
> but not at every app boundary.

Routes should accept and return stable Pydantic schemas. Internally, services can
convert those payloads into LangChain messages/runnables, LangGraph state, or
LlamaIndex documents/nodes.

## 7. Registry Changes

The registry should build AI runtime primitives directly:

```python
runtime.chat_model          # BaseChatModel
runtime.langchain_embeddings # Embeddings
runtime.agent_graph         # compiled LangGraph graph or Runnable
```

Current custom contracts such as `LLMClient`, `EmbeddingClient`, and
`VectorStore` should not be runtime adapter boundaries. Request/response schemas
and cache-key schemas can remain where they preserve API flow or cross-cutting
policy, but the template should not wrap LangChain or LlamaIndex with another
provider abstraction by default.

Provider configuration should use LangChain conventions where possible:

```env
CHAT_MODEL=openai:gpt-4.1-mini
EMBEDDING_MODEL=openai:text-embedding-3-small
```

Exact model naming should follow LangChain's `init_chat_model` and `init_embeddings`
conventions. Provider-specific API keys stay in environment variables expected by
the relevant provider package.

## 8. Prompt Convention

Prompt governance stays custom, but prompt execution uses LangChain.

The prompt registry should store:

- prompt name
- version
- template type: `chat` or `string`
- messages for chat prompts
- variables
- metadata
- owner/risk notes where useful

At runtime it should return:

- `ChatPromptTemplate` for chat prompts
- `PromptTemplate` for string prompts

Rendering should use LangChain prompt rendering, not a custom `.format()` path, except for legacy compatibility.

This keeps prompt versioning and promotion in the template while letting AI engineers compose prompts naturally with runnables.

## 9. Knowledge Retrieval Addon Convention

RAG is not a standalone answer flow in this template. LlamaIndex is an advanced
retrieval addon that feeds LangChain/LangGraph agents:

- input documents become LlamaIndex `Document`
- metadata stays plain dictionaries
- splitting uses LlamaIndex node parsers
- indexing uses `VectorStoreIndex`
- retrieval uses LlamaIndex retrievers and `NodeWithScore`
- optional LlamaIndex LLM calls are limited to retrieval-specific transforms such
  as query rewrite, decomposition, HyDE, metadata extraction, and reranking

The API exposes ingestion and search/debug endpoints. It should not expose
`/rag/answer`; final user-facing answers belong to the LangGraph agent, usually
through a LangChain `knowledge_search` tool backed by the LlamaIndex retriever.

The template still owns:

- redaction policy before storage/tracing
- usage/cost/latency recording
- feedback capture
- local eval reports
- artifact manifests
- quality gates

## 10. Agent Convention

Agents should use LangGraph as the primary orchestration convention.

The default local agent should be a small graph, not a separate custom runtime loop. It can remain simple:

```text
START -> model_node -> END
```

Project-specific agents can provide graph factories that return compiled graphs. The adapter should normalize:

- API `AgentRequest` into graph input state
- graph output into API `AgentResponse`
- graph events into custom observability events
- usage and latency into the template usage tracker

Use LangChain's `create_agent` only when a prebuilt agent loop is enough. Use custom `StateGraph` when the workflow needs explicit nodes, state, branching, human review, memory, or long-running behavior.

## 11. Tools Convention

Tools should use LangChain's tool convention.

Preferred:

- `@tool`
- structured tool schemas
- `ToolMessage`
- runtime/context injection where needed

The template should not invent a separate tool schema unless an API boundary requires one.

The app can still wrap sensitive tools with its own policies:

- auth context
- rate limits
- redaction
- audit metadata
- allowed tool registry

## 12. Observability Without LangSmith

Observability remains custom.

The template should capture LangChain and LangGraph activity through callbacks, stream events, or runnable wrappers, then map it into `ObservabilityClient`.

The custom event model should support:

- `ai.operation`
- `ai.model`
- `ai.provider`
- `ai.prompt.name`
- `ai.prompt.version`
- token usage
- latency
- tool call name and status
- graph node name
- graph run id or thread id when available
- redaction status
- cache hit/miss

Backends remain adapter-driven:

- debug in-memory
- OTel debug
- future Datadog, Grafana, Phoenix, or other team-owned profiles

No LangSmith tracing is included.

## 13. Evaluation Without LangSmith

Evaluation remains custom and local-first.

Eval targets should accept LangChain-native objects:

- `Runnable`
- compiled LangGraph graph
- callable target function

Evaluator functions should return custom metric records:

```python
{
    "key": "grounding",
    "score": 0.83,
    "passed": True,
    "comment": "All cited facts were present in retrieved context."
}
```

Supported evaluator categories:

- keyword and regex checks
- retrieval hit rate
- grounding checks
- output schema validation
- latency and cost gates
- tool trajectory checks
- LLM-as-judge using a prompt and model configured by this template

LLM-as-judge is allowed, but the judge prompt, judge model, output parser, and metrics are controlled by this repository. No LangSmith upload path is included.

## 14. Caching

The existing cross-cutting LLM response cache contract should remain, but it must support LangChain-native calls.

Cache keys should be derived from:

- provider and model
- messages, including tool calls and content blocks where practical
- prompt name/version
- generation parameters
- tool definitions or tool policy identity
- tenant/user scope
- safety settings
- redaction/cache policy

The default remains no-op.

## 15. Migration Plan

This is an incremental refactor, not a rewrite.

### Phase A: Dependencies and Registry

- Add LangChain, LangGraph, and LlamaIndex dependencies.
- Add LangChain chat model factory.
- Add LangChain embedding factory.
- Add runtime registry fields for chat model, embeddings, and agent runtime.
- Remove template-owned LangChain bridge wrappers from the registry.

### Phase B: Prompt Registry

- Store prompt templates in a LangChain-compatible shape.
- Return `ChatPromptTemplate` for chat prompts.
- Keep prompt versioning and artifact manifests custom.

### Phase C: Knowledge Retrieval Runtime

- Convert ingestion/search internals to LlamaIndex `Document`, `VectorStoreIndex`,
  node parser, and retriever conventions.
- Remove standalone `/rag/answer`.
- Add a LangChain `knowledge_search` tool for agent use.
- Preserve redaction, usage tracking, eval smoke, and local fake path.

### Phase D: Agent Runtime

- Replace custom simple agent loop with a small LangGraph graph.
- Keep `AgentRequest` and `AgentResponse` API payloads.
- Add graph factory extension points.
- Emit graph node events through custom observability.

### Phase E: Eval Runner

- Let eval targets be runnables, compiled graphs, or callables.
- Add custom evaluator function contract.
- Keep local reports and quality gates.
- Do not add LangSmith.

## 16. Acceptance Criteria

1. Local golden path still runs without cloud credentials.
2. No direct LangSmith package selection, env var, code import, tracing profile, or eval upload path exists.
3. AI modules use LangChain, LangGraph, and LlamaIndex conventions internally.
4. Public API schemas remain stable Pydantic models.
5. Prompt registry can return LangChain prompt templates.
6. Knowledge indexing/search uses LlamaIndex primitives directly.
7. There is no standalone `/rag/answer` product endpoint.
8. Default agent runtime is backed by a compiled LangGraph graph and can call
   the `knowledge_search` tool.
9. Custom observability captures model, prompt, token, tool, and graph-node events.
10. Custom eval runner can evaluate retrieval quality or a compiled graph.
11. Current fake/local smoke tests still pass.
12. Docker build still passes.
13. Existing feedback, usage, cache, and artifact manifest contracts still work.

## 17. Risks and Mitigations

Risk: LangChain and LangGraph APIs can change.

Mitigation: Keep public HTTP schemas and template control-plane contracts independent from LangChain. Isolate direct framework usage inside AI runtime modules and adapter factories.

Risk: Provider integration packages can increase dependency weight.

Mitigation: Keep the default dependency set minimal. Add provider packages deliberately, or document optional install groups.

Risk: LangChain-native internals may leak into API schemas.

Mitigation: Route handlers convert at the boundary. API models remain Pydantic and stable.

Risk: Replacing current custom contracts in one pass can break phase 1-4 stability.

Mitigation: Keep Pydantic API schemas stable and migrate one runtime surface at a
time.

## 18. Reference Sources

- LangChain models: https://docs.langchain.com/oss/python/langchain/models
- LangChain chat model factory reference: https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model
- LlamaIndex vector index: https://docs.llamaindex.ai/en/stable/module_guides/indexing/vector_store_index/
- LlamaIndex embeddings: https://docs.llamaindex.ai/en/stable/module_guides/models/embeddings/
- LangChain messages: https://docs.langchain.com/oss/python/langchain/messages
- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- LangChain runtime context: https://docs.langchain.com/oss/python/langchain/runtime
- LangChain tools: https://docs.langchain.com/oss/python/langchain/tools
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph
- LangGraph StateGraph reference: https://reference.langchain.com/python/langgraph/graph/state/StateGraph
