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
    ``StandardRAGHandler`` uses priority=999 as the guaranteed fallback.
    """

    intent_name: str = "base"
    priority: int = 50

    def can_handle(self, ctx: "QueryContext") -> bool:
        """Sync, fast check — must NOT perform I/O.

        Return True if this handler should process the request.
        """
        return False

    @abstractmethod
    async def handle(self, ctx: "QueryContext") -> str:
        """Return a complete answer string."""
        ...

    @abstractmethod
    async def handle_stream(self, ctx: "QueryContext") -> AsyncIterator[str]:
        """Yield answer string chunks."""
        ...
        yield ""  # pragma: no cover
