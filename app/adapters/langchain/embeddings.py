from langchain_core.embeddings import Embeddings

from app.adapters.langchain.chat_models import stable_embedding
from app.core.config import Settings


class TemplateFakeEmbeddings(Embeddings):
    def __init__(self, *, model: str = "fake-embedding", dimensions: int = 16) -> None:
        self.model = model
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [stable_embedding(text, dimensions=self.dimensions) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return stable_embedding(text, dimensions=self.dimensions)


class OpenAICompatibleEmbeddings(Embeddings):
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "OpenAI-compatible LangChain embeddings support async invocation only"
        )

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError(
            "OpenAI-compatible LangChain embeddings support async invocation only"
        )

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.api_key or "not-needed", base_url=self.base_url
        )
        kwargs: dict[str, object] = {"model": self.model, "input": texts}
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        raw_response = await client.embeddings.create(**kwargs)
        return [list(item.embedding) for item in raw_response.data]

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]


def build_embeddings(settings: Settings) -> Embeddings:
    if settings.EMBEDDING_PROVIDER == "fake":
        return TemplateFakeEmbeddings(
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.FAKE_EMBEDDING_DIMENSIONS,
        )
    if settings.EMBEDDING_PROVIDER == "openai_compatible":
        return OpenAICompatibleEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENAI_COMPATIBLE_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL or settings.OPENAI_BASE_URL,
        )
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER}")
