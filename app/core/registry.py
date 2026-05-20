from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from app.adapters.agents.langgraph import LangGraphAgentRuntime
from app.adapters.agents.simple import SimpleAgentRuntime
from app.adapters.jobs.in_process import InProcessJobQueue
from app.adapters.langchain.bridges import LangChainEmbeddingClient, LangChainLLMClient
from app.adapters.langchain.chat_models import LOCAL_CHAT_MODEL_NAME, build_chat_model
from app.adapters.langchain.embeddings import (
    LOCAL_EMBEDDING_MODEL_NAME,
    build_embeddings,
)
from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm_cache.noop import NoOpLLMResponseCache
from app.adapters.mlops.local_tracker import LocalExperimentTracker
from app.adapters.mlops.mlflow import MLflowExperimentTracker
from app.adapters.observability.debug import DebugObservability
from app.adapters.observability.otel_debug import OTelDebugObservability
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
    chat_model: BaseChatModel
    embeddings: EmbeddingClient
    langchain_embeddings: Embeddings
    vector_store: VectorStore
    storage: ObjectStorage
    jobs: JobQueue
    observability: ObservabilityClient
    llm_cache: LLMResponseCache
    agent_runtime: AgentRuntime
    experiment_tracker: ExperimentTracker


def build_runtime_adapters(
    settings: Settings, *, usage_tracker=None
) -> RuntimeAdapters:
    llm_cache = _build_llm_cache(settings)
    chat_model = _build_chat_model(settings)
    langchain_embeddings = _build_langchain_embeddings(settings)
    base_llm = LangChainLLMClient(
        chat_model=chat_model,
        default_model=settings.CHAT_MODEL or LOCAL_CHAT_MODEL_NAME,
    )
    llm = CachedLLMClient(
        provider="langchain",
        client=base_llm,
        cache=llm_cache,
        enabled=settings.LLM_CACHE_ENABLED,
        default_model=settings.CHAT_MODEL or LOCAL_CHAT_MODEL_NAME,
    )
    observability = _build_observability(settings)
    return RuntimeAdapters(
        llm=llm,
        chat_model=chat_model,
        embeddings=LangChainEmbeddingClient(
            embeddings=langchain_embeddings,
            default_model=settings.EMBEDDING_MODEL or LOCAL_EMBEDDING_MODEL_NAME,
        ),
        langchain_embeddings=langchain_embeddings,
        vector_store=_build_vector_store(settings),
        storage=_build_storage(settings),
        jobs=_build_jobs(settings),
        observability=observability,
        llm_cache=llm_cache,
        agent_runtime=_build_agent_runtime(
            settings,
            chat_model=chat_model,
            observability=observability,
            usage_tracker=usage_tracker,
        ),
        experiment_tracker=_build_experiment_tracker(settings),
    )


def _build_chat_model(settings: Settings) -> BaseChatModel:
    return build_chat_model(settings)


def _build_langchain_embeddings(settings: Settings) -> Embeddings:
    return build_embeddings(settings)


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
    if settings.OBSERVABILITY_BACKEND == "otel_debug":
        return OTelDebugObservability(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
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
    chat_model: BaseChatModel,
    observability: ObservabilityClient,
    usage_tracker=None,
) -> AgentRuntime:
    if settings.AGENT_RUNTIME == "simple":
        return SimpleAgentRuntime(
            chat_model=chat_model,
            observability=observability,
            redaction_policy=RedactionPolicy.from_trace_content(settings.TRACE_CONTENT),
            usage_tracker=usage_tracker,
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
