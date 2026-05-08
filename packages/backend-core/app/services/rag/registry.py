"""Handler registry — priority-ordered intent dispatch."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncIterator, List, Optional

from app.utils.observability import log_json

if TYPE_CHECKING:
    from app.services.rag.base_handler import QueryHandler
    from app.services.rag.context import QueryContext

logger = logging.getLogger("app.rag.registry")


class HandlerRegistry:
    """Routes a QueryContext to the first handler whose ``can_handle()`` returns True.

    Handlers are sorted by ``priority`` (ascending) once at construction time.
    ``StandardRAGHandler`` (priority=999) always matches and acts as the fallback.
    """

    def __init__(self, handlers: List["QueryHandler"]) -> None:
        self._handlers = sorted(handlers, key=lambda h: h.priority)

    def _select(self, ctx: "QueryContext") -> "QueryHandler":
        for handler in self._handlers:
            if handler.can_handle(ctx):
                log_json(
                    logger,
                    logging.INFO,
                    "Intent matched",
                    intent=handler.intent_name,
                    question_prefix=ctx.question[:40],
                )
                return handler
        raise RuntimeError(
            "No handler matched — StandardRAGHandler must always be last with can_handle()=True"
        )

    async def dispatch(self, ctx: "QueryContext") -> str:
        handler = self._select(ctx)
        return await handler.handle(ctx)

    async def dispatch_stream(self, ctx: "QueryContext") -> AsyncIterator[str]:
        handler = self._select(ctx)
        async for chunk in handler.handle_stream(ctx):
            yield chunk


# ---------------------------------------------------------------------------
# Registry construction
# ---------------------------------------------------------------------------

_registry_singleton: Optional[HandlerRegistry] = None


def build_default_registry() -> HandlerRegistry:
    from app.services.rag.handlers.identity import IdentityHandler
    from app.services.rag.handlers.capabilities import CapabilityHandler
    from app.services.rag.handlers.author_by_title import AuthorByTitleHandler
    from app.services.rag.handlers.books_by_author import BooksByAuthorHandler
    from app.services.rag.handlers.volume_info import VolumeInfoHandler
    from app.services.rag.handlers.follow_up import FollowUpHandler
    from app.services.rag.handlers.current_page import CurrentPageHandler
    from app.services.rag.handlers.current_volume import CurrentVolumeHandler
    from app.services.rag.handlers.catalog import CatalogHandler
    from app.services.rag.handlers.standard_rag import StandardRAGHandler
    from app.services.rag.agent.handler import AgentRAGHandler

    return HandlerRegistry([
        IdentityHandler(),
        CapabilityHandler(),
        AuthorByTitleHandler(),
        BooksByAuthorHandler(),
        VolumeInfoHandler(),
        FollowUpHandler(),
        CurrentPageHandler(),
        CurrentVolumeHandler(),
        CatalogHandler(),
        AgentRAGHandler(),   # priority=998 — intercepts when agentic_rag_enabled=true
        StandardRAGHandler(),  # priority=999 — fallback when flag is off
    ])


def get_registry() -> HandlerRegistry:
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = build_default_registry()
    return _registry_singleton
