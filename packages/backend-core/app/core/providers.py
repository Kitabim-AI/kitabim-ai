from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

if TYPE_CHECKING:
    from app.core.protocols import EmbeddingProvider, LLMProvider, VectorStore


def get_embedding_provider(model_name: str) -> EmbeddingProvider:
    if settings.embedding_provider == "gemini":
        from app.langchain.models import GeminiEmbeddings
        return GeminiEmbeddings(model_name)
    else:
        raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")


def get_llm_provider(model_name: str) -> LLMProvider:
    if settings.llm_provider == "gemini":
        from app.langchain.models import build_text_llm
        return build_text_llm(model_name)
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def get_vector_store(session: AsyncSession) -> VectorStore:
    if settings.vector_store_provider == "pgvector":
        from app.db.repositories.chunks import ChunksRepository
        return ChunksRepository(session)
    else:
        raise ValueError(f"Unknown vector store provider: {settings.vector_store_provider}")
