"""FollowUpHandler — detects follow-up questions and enriches them with prior context."""
from __future__ import annotations

from typing import AsyncIterator

from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur

# Uyghur pronouns/markers that signal a follow-up question
_FOLLOWUP_MARKERS = [
    "ئۇ كىتاب", "شۇ كىتاب", "بۇ كىتاب",
    "ئۇ كىتابنىڭ", "شۇ كىتابنىڭ", "بۇ كىتابنىڭ",
    "ئۇ كىتابتىكى", "شۇ كىتابتىكى", "بۇ كىتابتىكى",
    "ئۇ كىتابتا", "شۇ كىتابتا", "بۇ كىتابتا",      # that/this book
    "ئۇ ئەسەر", "شۇ ئەسەر", "بۇ ئەسەر",        # that work
    "ئۇ ئاپتور", "شۇ ئاپتور", "بۇ ئاپتور",              # that author
    "ئۇ تومدا", "شۇ تومدا", "ئۇ قىسىمىدا",
    "شۇ قىسىمىدا", "بۇ قىسىمىدا", "بۇ تومدا",
    "ئۇ تومىدا", "شۇ تومىدا","بۇ قىسىمدا", "ئۇ قىسىمدا", # in that volume
    "يەنە", "داۋاملاشتۇر", "داۋامى",            # continue / more
    "تېخىمۇ", "قوشۇمچە", "مىسال كەلتۈر",          # additionally / example
    "نىمىشقا", "نېمە ئۈچۈن",                    # why (common follow-up)
    "كىمنى دىمەكچى", "نىمە دىمەكچى",       # what do you mean by ...
]
_FOLLOWUP_MARKERS_NORM = [normalize_uyghur(m) for m in _FOLLOWUP_MARKERS]

# Questions shorter than this threshold with prior history are likely follow-ups
_SHORT_QUESTION_THRESHOLD = 15


class FollowUpHandler(QueryHandler):
    """Heuristic follow-up detection — no LLM overhead.

    When a follow-up is detected, the question is enriched by prepending the
    last AI turn as bracketed context, then the standard RAG pipeline runs.
    """

    intent_name = "follow_up"
    priority = 30

    def can_handle(self, ctx: QueryContext) -> bool:
        if not ctx.history:
            return False
        q = normalize_uyghur(ctx.question.strip())
        # Heuristic 1: explicit follow-up pronoun or marker
        if any(m in q for m in _FOLLOWUP_MARKERS_NORM):
            return True
        # Heuristic 2: very short question with at least 2 history turns
        if len(q) < _SHORT_QUESTION_THRESHOLD and len(ctx.history) >= 2:
            return True
        return False

    def _enrich(self, ctx: QueryContext) -> str:
        last_ai = next(
            (m.get("text", "") for m in reversed(ctx.history) if m.get("role") == "assistant"),
            "",
        )
        if last_ai:
            return f"{t('rag.followup_context_prefix', context=last_ai[:200])}\n{ctx.question}"
        return ctx.question

    async def handle(self, ctx: QueryContext) -> str:
        ctx.enriched_question = self._enrich(ctx)
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        return await StandardRAGHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        ctx.enriched_question = self._enrich(ctx)
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        async for chunk in StandardRAGHandler().handle_stream(ctx):
            yield chunk
