from typing import Any

from openai import AsyncOpenAI

from app.contracts.embeddings import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        dimensions: int | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        kwargs: dict[str, object] = {
            "model": request.model or self.model,
            "input": request.texts,
        }
        dimensions = request.dimensions or self.dimensions
        if dimensions is not None:
            kwargs["dimensions"] = dimensions

        raw_response = await self.client.embeddings.create(**kwargs)
        usage = getattr(raw_response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", input_tokens) or input_tokens)
        return EmbeddingResponse(
            vectors=[list(item.embedding) for item in raw_response.data],
            model=str(raw_response.model),
            usage=EmbeddingUsage(
                input_tokens=input_tokens,
                total_tokens=total_tokens,
            ),
        )
