from dataclasses import dataclass

from app.adapters.agents.langgraph import LangGraphAgentRuntime
from app.adapters.agents.simple import SimpleAgentRuntime
from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingClient
from app.adapters.jobs.in_process import InProcessJobQueue
from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm.fake import FakeLLMClient
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMClient
from app.adapters.llm_cache.noop import NoOpLLMResponseCache
from app.adapters.mlops.local_tracker import LocalExperimentTracker
from app.adapters.mlops.mlflow import MLflowExperimentTracker
from app.adapters.observability.debug import DebugObservability
from app.adapters.storage.local import LocalObjectStorage
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.contracts.agents import AgentRuntime
from app.contracts.embeddings import EmbeddingClient
from app.contracts.experiment_tracker import ExperimentTracker
from app.contracts.jobs import JobQueue
from app.contracts.llm import LLMClient
from app.contracts.llm_cache import LLMResponseCache
from app.contracts.observability import ObservabilityClient
from app.contracts.storage import ObjectStorage
from app.contracts.vector_store import VectorStore
from app.core.config import Settings
from app.core.redaction import RedactionPolicy


@dataclass(frozen=True)
class RuntimeAdapters:
    llm: LLMClient
    embeddings: EmbeddingClient
    vector_store: VectorStore
    storage: ObjectStorage
    jobs: JobQueue
    observability: ObservabilityClient
    llm_cache: LLMResponseCache
    agent_runtime: AgentRuntime
    experiment_tracker: ExperimentTracker


def build_runtime_adapters(settings: Settings) -> RuntimeAdapters:
    llm_cache = _build_llm_cache(settings)
    base_llm = _build_llm(settings)
    llm = CachedLLMClient(
        provider=settings.LLM_PROVIDER,
        client=base_llm,
        cache=llm_cache,
        enabled=settings.LLM_CACHE_ENABLED,
        default_model=settings.LLM_MODEL,
    )
    observability = _build_observability(settings)
    return RuntimeAdapters(
        llm=llm,
        embeddings=_build_embeddings(settings),
        vector_store=_build_vector_store(settings),
        storage=_build_storage(settings),
        jobs=_build_jobs(settings),
        observability=observability,
        llm_cache=llm_cache,
        agent_runtime=_build_agent_runtime(
            settings, llm=llm, observability=observability
        ),
        experiment_tracker=_build_experiment_tracker(settings),
    )


def _build_llm(settings: Settings) -> LLMClient:
    if settings.LLM_PROVIDER == "fake":
        return FakeLLMClient(model=settings.LLM_MODEL)
    if settings.LLM_PROVIDER == "openai_compatible":
        _require_openai_api_key(settings, setting_name="LLM_PROVIDER")
        return OpenAICompatibleLLMClient(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.LLM_MODEL,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")


def _build_embeddings(settings: Settings) -> EmbeddingClient:
    if settings.EMBEDDING_PROVIDER == "fake":
        return FakeEmbeddingClient(
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.FAKE_EMBEDDING_DIMENSIONS,
        )
    if settings.EMBEDDING_PROVIDER == "openai_compatible":
        _require_openai_api_key(settings, setting_name="EMBEDDING_PROVIDER")
        return OpenAICompatibleEmbeddingClient(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.EMBEDDING_MODEL,
        )
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")


def _build_vector_store(settings: Settings) -> VectorStore:
    if settings.VECTOR_STORE == "in_memory":
        return InMemoryVectorStore()
    raise ValueError(f"Unsupported VECTOR_STORE: {settings.VECTOR_STORE}")


def _build_storage(settings: Settings) -> ObjectStorage:
    if settings.STORAGE_BACKEND == "local":
        return LocalObjectStorage(root=settings.LOCAL_STORAGE_ROOT)
    raise ValueError(f"Unsupported STORAGE_BACKEND: {settings.STORAGE_BACKEND}")


def _build_jobs(settings: Settings) -> JobQueue:
    if settings.JOB_BACKEND == "in_process":
        return InProcessJobQueue()
    raise ValueError(f"Unsupported JOB_BACKEND: {settings.JOB_BACKEND}")


def _build_observability(settings: Settings) -> ObservabilityClient:
    if settings.OBSERVABILITY_BACKEND == "debug":
        return DebugObservability()
    raise ValueError(
        f"Unsupported OBSERVABILITY_BACKEND: {settings.OBSERVABILITY_BACKEND}"
    )


def _build_llm_cache(settings: Settings) -> LLMResponseCache:
    if settings.LLM_CACHE_BACKEND == "noop":
        return NoOpLLMResponseCache()
    raise ValueError(f"Unsupported LLM_CACHE_BACKEND: {settings.LLM_CACHE_BACKEND}")


def _build_agent_runtime(
    settings: Settings,
    *,
    llm: LLMClient,
    observability: ObservabilityClient,
) -> AgentRuntime:
    if settings.AGENT_RUNTIME == "simple":
        return SimpleAgentRuntime(
            llm=llm,
            observability=observability,
            redaction_policy=RedactionPolicy.from_trace_content(settings.TRACE_CONTENT),
        )
    if settings.AGENT_RUNTIME == "langgraph":
        return LangGraphAgentRuntime()
    raise ValueError(f"Unsupported AGENT_RUNTIME: {settings.AGENT_RUNTIME}")


def _build_experiment_tracker(settings: Settings) -> ExperimentTracker:
    if settings.EXPERIMENT_TRACKER_BACKEND == "local":
        return LocalExperimentTracker(root=settings.LOCAL_EXPERIMENT_TRACKER_ROOT)
    if settings.EXPERIMENT_TRACKER_BACKEND == "mlflow":
        return MLflowExperimentTracker(
            tracking_uri=settings.MLFLOW_TRACKING_URI,
            experiment_name=settings.MLFLOW_EXPERIMENT_NAME,
        )
    raise ValueError(
        f"Unsupported EXPERIMENT_TRACKER_BACKEND: {settings.EXPERIMENT_TRACKER_BACKEND}"
    )


def _require_openai_api_key(settings: Settings, *, setting_name: str) -> None:
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            f"OPENAI_API_KEY is required when {setting_name}=openai_compatible",
        )
