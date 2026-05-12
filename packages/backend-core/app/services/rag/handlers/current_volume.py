"""CurrentVolumeHandler — restricts search to the current volume only."""
from __future__ import annotations

from typing import AsyncIterator

from app.services.rag.agent.handler import agent_rag_handler
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import is_current_volume_query


class CurrentVolumeHandler(QueryHandler):
    intent_name = "current_volume"
    priority = 41
    is_fast_handler = True

    def can_handle(self, ctx: QueryContext) -> bool:
        if ctx.is_global:
            return False
        return is_current_volume_query(ctx.question)

    async def handle(self, ctx: QueryContext) -> str:
        ctx.use_current_volume_only = True
        return await agent_rag_handler.handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        ctx.use_current_volume_only = True
        async for chunk in agent_rag_handler.handle_stream(ctx):
            yield chunk
