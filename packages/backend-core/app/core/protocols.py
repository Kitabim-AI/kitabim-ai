from __future__ import annotations

from typing import Protocol, List, Optional, Any, AsyncIterator


class EmbeddingProvider(Protocol):
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    async def aembed_query(self, text: str) -> List[float]:
        ...

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_query(self, text: str) -> List[float]:
        ...


class LLMProvider(Protocol):
    async def ainvoke(
        self, input: Any, config: Any | None = None, **kwargs: Any
    ) -> Any:
        ...

    async def astream(
        self, input: Any, config: Any | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        ...


class VectorStore(Protocol):
    async def similarity_search(
        self,
        query_embedding: List[float],
        book_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        limit: int = 12,
        threshold: float = 0.35,
    ) -> List[dict]:
        ...
