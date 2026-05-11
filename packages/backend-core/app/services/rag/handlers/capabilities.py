"""CapabilityHandler — answers 'what can you do' questions with a static list."""
from __future__ import annotations

from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur

_CAPABILITY_KEYWORDS = [
    "نېمە قىلالايسەن", "نېمە قىلالايسىز",
    "نېمە ئىش قىلالايسەن", "نېمە ئىش قىلالايسىز",
    "قانداق ياردەم", "ياردەم بەرەلەمسەن", "ياردەم بەرەلەمسىز",
    "ئىقتىدارىڭ نېمە", "ئىقتىدارىڭىز نېمە",
    "نېمىلەرنى بىلىسەن", "نېمىلەرنى بىلىسىز",
    "نېمە ئۈچۈن ئىشلىتىلىدۇ", "سەن نېمە قىلىسەن",
]
_CAPABILITY_KEYWORDS_NORM = [normalize_uyghur(k) for k in _CAPABILITY_KEYWORDS]


class CapabilityHandler(QueryHandler):
    intent_name = "capabilities"
    priority = 11

    def can_handle(self, ctx: QueryContext) -> bool:
        q = normalize_uyghur(ctx.question.strip())
        return any(k in q for k in _CAPABILITY_KEYWORDS_NORM)

    async def handle(self, _ctx: QueryContext) -> str:
        return t("rag.capabilities")
