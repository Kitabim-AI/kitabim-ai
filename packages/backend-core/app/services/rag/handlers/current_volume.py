"""CurrentVolumeHandler — restricts search to the current volume only."""
from __future__ import annotations

from typing import AsyncIterator

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import is_current_volume_query


class CurrentVolumeHandler(QueryHandler):
    intent_name = "current_volume"
    priority = 41

    def can_handle(self, ctx: QueryContext) -> bool:
        if ctx.is_global:
            return False
        return is_current_volume_query(ctx.question)

    async def handle(self, ctx: QueryContext) -> str:
        ctx.use_current_volume_only = True
        from app.services.rag.agent.handler import AgentRAGHandler
        return await AgentRAGHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        ctx.use_current_volume_only = True
        from app.services.rag.agent.handler import AgentRAGHandler
        async for chunk in AgentRAGHandler().handle_stream(ctx):
            yield chunk
