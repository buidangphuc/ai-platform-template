import pytest

from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddingClient
from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMClient
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
    assert isinstance(adapters.embeddings, FakeEmbeddingClient)
    assert isinstance(adapters.vector_store, InMemoryVectorStore)
    assert isinstance(adapters.storage, LocalObjectStorage)
    assert isinstance(adapters.llm_cache, NoOpLLMResponseCache)
    assert isinstance(adapters.experiment_tracker, LocalExperimentTracker)


def test_registry_fails_fast_for_unknown_provider(test_settings: Settings):
    settings = test_settings.model_copy(update={"LLM_PROVIDER": "unknown"})

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_runtime_adapters(settings)


def test_app_wires_runtime_adapters_into_state(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    assert app.state.adapters is not None
    assert isinstance(app.state.adapters.llm, CachedLLMClient)


def test_registry_allows_openai_compatible_local_endpoint_without_vendor_key(
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={
            "LLM_PROVIDER": "openai_compatible",
            "EMBEDDING_PROVIDER": "openai_compatible",
            "OPENAI_COMPATIBLE_API_KEY": "",
            "OPENAI_COMPATIBLE_BASE_URL": "http://localhost:11434/v1",
        }
    )

    adapters = build_runtime_adapters(settings)

    assert isinstance(adapters.llm.client, OpenAICompatibleLLMClient)
    assert isinstance(adapters.embeddings, OpenAICompatibleEmbeddingClient)


def test_registry_builds_otel_debug_observability(test_settings: Settings):
    settings = test_settings.model_copy(
        update={
            "OBSERVABILITY_BACKEND": "otel_debug",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
        }
    )

    adapters = build_runtime_adapters(settings)

    assert isinstance(adapters.observability, OTelDebugObservability)
