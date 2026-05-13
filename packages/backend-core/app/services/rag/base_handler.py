"""Abstract base class for all RAG query handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from app.services.rag.context import QueryContext


class QueryHandler(ABC):
    """Base class for intent-specific query handlers.

    Handlers are stateless singletons.  All per-request state lives in
    ``QueryContext`` which is passed to every method.

    Priority ordering: lower value = higher priority.
    ``AgentRAGHandler`` uses priority=998 as the guaranteed fallback.
    """

    intent_name: str = "base"
    priority: int = 50
    is_fast_handler: bool = False

    def can_handle(self, ctx: "QueryContext") -> bool:
        """Sync, fast check — must NOT perform I/O.

        Return True if this handler should process the request.
        """
        return False

    @abstractmethod
    async def handle(self, ctx: "QueryContext") -> str:
        """Return a complete answer string."""
        ...

    async def handle_stream(self, ctx: "QueryContext") -> AsyncIterator[str]:
        """Yield answer string chunks.

        Default implementation calls ``handle()`` and yields the result as a
        single chunk.  Override in handlers that can stream token-by-token
        (e.g. those backed by ``generate_answer_stream``).
        """
        yield await self.handle(ctx)
