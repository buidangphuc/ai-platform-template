from app.adapters.langchain.bridges import LangChainEmbeddingClient, LangChainLLMClient
from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm_cache.noop import NoOpLLMResponseCache
from app.adapters.mlops.local_tracker import LocalExperimentTracker
from app.adapters.observability.otel_debug import OTelDebugObservability
from app.adapters.storage.local import LocalObjectStorage
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.registry import build_runtime_adapters


def test_registry_builds_local_default_adapters(test_settings: Settings):
    adapters = build_runtime_adapters(test_settings)

    assert isinstance(adapters.llm, CachedLLMClient)
    assert adapters.llm.provider == "langchain"
    assert isinstance(adapters.llm.client, LangChainLLMClient)
    assert isinstance(adapters.embeddings, LangChainEmbeddingClient)
    assert adapters.chat_model is not None
    assert adapters.langchain_embeddings is not None
    assert isinstance(adapters.vector_store, InMemoryVectorStore)
    assert isinstance(adapters.storage, LocalObjectStorage)
    assert isinstance(adapters.llm_cache, NoOpLLMResponseCache)
    assert isinstance(adapters.experiment_tracker, LocalExperimentTracker)


def test_app_wires_runtime_adapters_into_state(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    assert app.state.adapters is not None
    assert isinstance(app.state.adapters.llm, CachedLLMClient)


def test_registry_builds_otel_debug_observability(test_settings: Settings):
    settings = test_settings.model_copy(
        update={
            "OBSERVABILITY_BACKEND": "otel_debug",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
        }
    )

    adapters = build_runtime_adapters(settings)

    assert isinstance(adapters.observability, OTelDebugObservability)
