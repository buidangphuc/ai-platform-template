from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


async def embed_documents(
    embeddings: Embeddings,
    documents: list[Document],
) -> list[list[float]]:
    if not documents:
        return []
    return await embeddings.aembed_documents(
        [document.page_content for document in documents]
    )
