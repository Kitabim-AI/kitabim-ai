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
    "كەيىنكى قىسىم", "كېيىنكى قىسىم",      # following volumes
    "كەيىنكى توم", "كېيىنكى توم",
    "2-قىسىم", "3-قىسىم", "ئىككىنچى قىسىم", "ئۈچىنچى قىسىم",
    "بۇ شەخس", "بۇ پېرسوناژ", "بۇ قەھرىمان",  # this character (follow-up reference)
]
_FOLLOWUP_MARKERS_NORM = [normalize_uyghur(m) for m in _FOLLOWUP_MARKERS]

# Questions shorter than this threshold with prior history are likely follow-ups
_SHORT_QUESTION_THRESHOLD = 15

# Standalone referential pronouns that anchor a short question to a previous topic.
# We check word-level so "ئۇنىڭ" in "ئۇنىڭ ئاپتورى" matches, but a word that merely
# contains these characters as a substring does not.
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
    """Heuristic follow-up detection — no LLM overhead.

    When a follow-up is detected, the question is enriched by prepending the
    last user question as bracketed context (better embedding anchor than the
    AI answer), then the standard RAG pipeline runs.
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
        # Heuristic 2: very short question that contains a referential pronoun,
        # with at least 2 history turns. Bare standalone words like "ئۇنىڭ"
        # only make sense in reference to prior context; a short question without
        # any such pronoun is more likely a new, independent question.
        if len(q) < _SHORT_QUESTION_THRESHOLD and len(ctx.history) >= 2:
            words = set(q.split())
            if words & _REFERENTIAL_PRONOUNS:
                return True
        return False

    def _enrich(self, ctx: QueryContext) -> str:
        # Use the last user question (not the AI answer) as the resolution anchor.
        # The previous question is topic-focused and produces a better embedding
        # for pronoun resolution; the AI answer prose biases retrieval toward the
        # old topic rather than the referenced entity.
        last_user_q = next(
            (m.get("text", "") for m in reversed(ctx.history) if m.get("role") == "user"),
            "",
        )
        if last_user_q:
            return f"{t('rag.followup_context_prefix', context=last_user_q[:200])}\n{ctx.question}"
        return ctx.question

    async def _extract_history_book_ids(self, ctx: QueryContext) -> list:
        """Scan recent assistant messages for book titles and return their IDs.

        Tries messages from most-recent to oldest so the most recent book context wins.
        """
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        seen: set = set()
        for msg in reversed(ctx.history):
            if msg.get("role") != "assistant":
                continue
            text = msg.get("text", "").strip()
            if not text:
                continue
            found = await StandardRAGHandler._find_books_by_title_in_question(text, ctx.session)
            if found:
                for bid in found:
                    seen.add(bid)
                break  # stop at the most recent assistant turn that had a named book
        return list(seen)

    async def handle(self, ctx: QueryContext) -> str:
        ctx.enriched_question = self._enrich(ctx)
        if ctx.is_global:
            ctx.history_book_ids = await self._extract_history_book_ids(ctx)
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        return await StandardRAGHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        ctx.enriched_question = self._enrich(ctx)
        if ctx.is_global:
            ctx.history_book_ids = await self._extract_history_book_ids(ctx)
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        async for chunk in StandardRAGHandler().handle_stream(ctx):
            yield chunk
