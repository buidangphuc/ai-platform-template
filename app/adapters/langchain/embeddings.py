from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.embeddings.fake import DeterministicFakeEmbedding

from app.core.config import Settings

LOCAL_EMBEDDING_DIMENSIONS = 16
LOCAL_EMBEDDING_MODEL_NAME = "local-deterministic-embedding"


def build_embeddings(settings: Settings) -> Embeddings:
    if not settings.EMBEDDING_MODEL:
        return DeterministicFakeEmbedding(size=LOCAL_EMBEDDING_DIMENSIONS)
    return init_embeddings(model=settings.EMBEDDING_MODEL)
