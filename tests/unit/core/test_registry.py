import pytest

from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.llm.cached import CachedLLMClient
from app.adapters.llm_cache.noop import NoOpLLMResponseCache
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


def test_registry_fails_fast_for_unknown_provider(test_settings: Settings):
    settings = test_settings.model_copy(update={"LLM_PROVIDER": "unknown"})

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        build_runtime_adapters(settings)


def test_app_wires_runtime_adapters_into_state(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    assert app.state.adapters is not None
    assert isinstance(app.state.adapters.llm, CachedLLMClient)
