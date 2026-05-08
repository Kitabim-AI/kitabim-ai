"""FollowUpHandler — detects follow-up questions and rewrites them as standalone queries."""
from __future__ import annotations

from typing import AsyncIterator

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.query_rewriter import QueryRewriter
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
    "كەيىنكى قىسىم", "كېيىنكى قىسىم",      # following volumes
    "كەيىنكى توم", "كېيىنكى توم",
    "2-قىسىم", "3-قىسىم", "ئىككىنچى قىسىم", "ئۈچىنچى قىسىم",
    "بۇ شەخس", "بۇ پېرسوناژ", "بۇ قەھرىمان",  # this character (follow-up reference)
]
_FOLLOWUP_MARKERS_NORM = [normalize_uyghur(m) for m in _FOLLOWUP_MARKERS]

_REFERENTIAL_PRONOUNS = {normalize_uyghur(p) for p in [
    "ئۇ", "بۇ", "شۇ",
    "ئۇلار", "بۇلار", "شۇلار",
    "ئۇنىڭ", "بۇنىڭ", "شۇنىڭ",
    "ئۇنى", "بۇنى", "شۇنى",
    "ئۇنىڭدا", "شۇنىڭدا", "بۇنىڭدا",
    "ئۇنىڭدىن", "شۇنىڭدىن", "بۇنىڭدىن",
    "ئۇنىڭغا", "شۇنىڭغا", "بۇنىڭغا",
]}


class FollowUpHandler(QueryHandler):
    """Heuristic follow-up detection followed by LLM query rewriting.

    When a follow-up is detected, QueryRewriter rewrites the question into a
    self-contained standalone query (resolving pronouns and implicit references)
    before delegating to the standard RAG pipeline.  Falls back to the original
    question if the rewriter fails.
    """

    intent_name = "follow_up"
    priority = 30

    def can_handle(self, ctx: QueryContext) -> bool:
        if not ctx.history:
            return False
        q = normalize_uyghur(ctx.question.strip())
        # Heuristic 1: explicit follow-up phrase or marker
        if any(m in q for m in _FOLLOWUP_MARKERS_NORM):
            return True
        # Heuristic 2: referential pronoun as a standalone word with prior history.
        # No length gate — "ئۇ غۇلجىدا تۇغۇلۇپ چوڭ بولغانغۇ" is a follow-up
        # just as much as the short "ئۇ قەيەرلىك؟".
        if len(ctx.history) >= 1:
            words = set(q.split())
            if words & _REFERENTIAL_PRONOUNS:
                return True
        return False

    async def handle(self, ctx: QueryContext) -> str:
        ctx.enriched_question = await QueryRewriter().rewrite(ctx)
        from app.services.rag.agent.handler import AgentRAGHandler
        return await AgentRAGHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        ctx.enriched_question = await QueryRewriter().rewrite(ctx)
        from app.services.rag.agent.handler import AgentRAGHandler
        async for chunk in AgentRAGHandler().handle_stream(ctx):
            yield chunk
