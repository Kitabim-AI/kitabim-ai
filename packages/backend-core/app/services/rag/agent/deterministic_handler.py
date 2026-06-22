"""DeterministicRAGHandler — deterministic, python-based RAG router.

Replaces LLM-driven ADK ReAct agent sequences with a deterministic decision tree
built on extracted signals and conditional intent classification.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Union
from google.genai import types

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json
from app.services.rag.agent.tools import _dispatch_tool_with_retry
from app.services.rag.utils import normalize_uyghur
from app.db.repositories.books_repository import BooksRepository
from app.llm.models import build_text_llm

from app.services.rag.agent.handler import (
    _grade_context,
    _extract_used_book_ids,
    _populate_ctx_from_observations,
)

logger = logging.getLogger("app.rag.agent.deterministic_handler")

# Punctuation boundaries for pronouns
_PUNCT = "«»،؟!()[]{}\"''"

from app.services.rag.keywords import (
    UYGHUR_PRONOUN_TOKENS,
    VOLUME_SHIFT_KEYWORDS,
    CATALOG_AUTHOR_QUERIES,
    CATALOG_BOOKS_QUERIES,
    PAGE_QUERY_PATTERNS,
)


def repair_json_unescaped_quotes(json_str: str) -> str:
    """Repair JSON string values with unescaped internal double quotes."""
    pattern = (
        r'"(rewritten_question|question|intent|catalog_subtype)":\s*"(.*)"\s*(,?)\s*$'
    )

    def escape_internal_quotes(match):
        key = match.group(1)
        val = match.group(2)
        suffix = match.group(3)
        normalized = val.replace('\\"', '"')
        escaped = normalized.replace('"', '\\"')
        return f'"{key}": "{escaped}"{suffix}'

    return re.sub(pattern, escape_internal_quotes, json_str, flags=re.MULTILINE)


class DeterministicRAGHandler(QueryHandler):
    """Deterministic Python RAG Handler.

    Uses a rule-based signal extractor and a conditional LLM intent classifier
    to choose and execute specific, optimized retrieval paths.
    """

    intent_name = "deterministic_rag"

    def can_handle(self, ctx: QueryContext) -> bool:
        return ctx.use_deterministic_router

    async def _llm_analyze_query(self, question: str, ctx: QueryContext) -> dict:
        """Stage 1.5: Query Signal & Intent Extractor LLM Call.

        Uses a single structured JSON response to classify query properties.
        """
        in_reader = ctx.current_page is not None
        current_page = ctx.current_page
        has_history = len(ctx.history) > 0
        history_str = ctx.chat_history_str if has_history else "None"

        prompt = f"""Analyze this Uyghur/English query in the context of a RAG book reading assistant.

Context:
- In Reader (Active Book Context): {in_reader} (Page: {current_page})
- Has Chat History: {has_history}

Chat History:
{history_str}

Query: {question}

Return ONLY valid JSON matching this schema:
{{
  "is_current_page_query": boolean, // True if the user asks about the page/text they are currently looking at (e.g. "what is on this page", "read this page", "بۇ بەتتە نېمە بار")
  "is_volume_shift": boolean,       // True if the user wants to go to another volume (e.g. "next volume", "previous volume", "ئالدىنقى توم", "2-توم")
  "target_volume": integer | null,  // The volume number to shift to if specified (e.g. 2, 3), else null
  "needs_rewrite": boolean,         // True if the query has unresolved pronouns/coreferences referring to history (e.g. "who wrote it?", "what is his age?", "ئۇ كىم؟")
  "rewritten_question": string | null, // If needs_rewrite is true, rewrite the question to resolve all pronouns/references using chat history to make it self-contained in Uyghur/English. If needs_rewrite is false, return null.
  "catalog_subtype": "author_of" | "books_by" | "general" | null, // Use "author_of" if asking who wrote a book, "books_by" if asking what books an author wrote, "general" for other catalog/library-wide queries (like "what books do you have"), or null if this is NOT a catalog query.
  "intent": "catalog" | "identity" | "summary" | "relationship" | "passage",
  "is_composite": boolean,          // True if the query contains multiple distinct questions or requests that should be handled separately (e.g. "Who wrote X and what is it about?").
  "sub_questions": Array<{{         // If is_composite is true, return each sub-question with its own signals. If is_composite is false, return null.
    "question": string,             // Self-contained sub-question text (pronouns resolved using history)
    "intent": "catalog" | "identity" | "summary" | "relationship" | "passage",
    "is_current_page_query": boolean,
    "is_volume_shift": boolean,
    "target_volume": integer | null,
    "catalog_subtype": "author_of" | "books_by" | "general" | null
  }}> | null
}}

Intents:
- catalog     : asking about book metadata, authors of books, book listings, or what books exist in the library
- identity    : asking who/what a person or character IS (biography, role, background)
- summary     : asking about the plot, themes, or main characters of a book
- relationship: asking about connections, lineages, family trees, or how X and Y relate
- passage     : asking for specific events, facts, quotes, or details — including "tell me about X's actions"
"""
        llm = build_text_llm(ctx.agent_model)
        res_text = await llm.ainvoke(
            prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        m = re.search(r"\{.*\}", res_text, re.DOTALL)
        if m:
            repaired_json = repair_json_unescaped_quotes(m.group())
            result = json.loads(repaired_json)
            log_json(
                logger,
                logging.INFO,
                "Query analyzer result received",
                result=result,
            )
            return result
        raise ValueError("LLM response did not contain a JSON block")

    async def extract_signals(self, question: str, ctx: QueryContext) -> dict:
        """Stage 1: Signal Extractor — database metadata lookups combined with structured LLM query analysis."""
        # 1. DB-based metadata checks (fast & deterministic)
        has_title = False
        matched_books = await find_books_by_title_in_db(question, ctx)
        if matched_books:
            has_title = True

        has_author = False
        books_repo = BooksRepository(ctx.session)
        matched_author_books = await books_repo.find_books_by_author_in_question(
            question, categories=ctx.character_categories or None
        )
        if matched_author_books:
            has_author = True

        in_reader = ctx.current_page is not None
        has_current_book = ctx.book_id is not None and not ctx.is_global
        has_context_books = len(ctx.context_book_ids) > 0
        is_global = ctx.is_global
        graph_available = (
            getattr(ctx.book, "graph_milestone", None) == "complete"
            if ctx.book
            else False
        )

        # 2. LLM query analysis (intent & signals) with keyword fallback fallback
        try:
            llm_res = await self._llm_analyze_query(question, ctx)
            is_current_page_query = llm_res.get("is_current_page_query", False)
            is_volume_shift = llm_res.get("is_volume_shift", False)
            target_volume = llm_res.get("target_volume")
            needs_rewrite = llm_res.get("needs_rewrite", False)
            rewritten_question = llm_res.get("rewritten_question")
            catalog_subtype = llm_res.get("catalog_subtype") or "general"
            intent = llm_res.get("intent", "passage")
            is_composite = llm_res.get("is_composite", False)
            sub_questions = llm_res.get("sub_questions")
        except Exception as exc:
            rewritten_question = None
            is_composite = False
            sub_questions = None
            log_json(
                logger,
                logging.WARNING,
                "Unified LLM signal extraction failed, falling back to keywords",
                error=str(exc),
            )
            # FALLBACK to original local python/keyword heuristics
            q_norm = normalize_uyghur(question.lower())

            # top intent
            is_current_page_query = ctx.current_page is not None and any(
                p in q_norm for p in PAGE_QUERY_PATTERNS
            )

            # catalog subtype
            catalog_subtype = "general"
            author_queries = [normalize_uyghur(x) for x in CATALOG_AUTHOR_QUERIES]
            books_queries = [normalize_uyghur(x) for x in CATALOG_BOOKS_QUERIES]
            if any(x in q_norm for x in author_queries):
                catalog_subtype = "author_of"
            elif any(x in q_norm for x in books_queries):
                catalog_subtype = "books_by"

            # volume shift
            volume_keywords = [normalize_uyghur(k) for k in VOLUME_SHIFT_KEYWORDS]
            is_volume_shift = any(k in q_norm for k in volume_keywords)
            target_volume = None
            if is_volume_shift:
                m = re.search(r"(\d+)\s*-?\s*توم|volume\s*(\d+)", q_norm)
                if m:
                    target_volume = int(m.group(1) or m.group(2))
                else:
                    current_volume = (
                        ctx.book.volume
                        if (ctx.book and ctx.book.volume is not None)
                        else None
                    )
                    next_keywords = [
                        normalize_uyghur(x) for x in ["كەيىنكى", "كېيىنكى", "next"]
                    ]
                    prev_keywords = [
                        normalize_uyghur(x) for x in ["ئالدىنقى", "prev", "previous"]
                    ]
                    if any(x in q_norm for x in next_keywords):
                        target_volume = (
                            (current_volume + 1) if current_volume is not None else 1
                        )
                    elif any(x in q_norm for x in prev_keywords):
                        target_volume = (
                            (current_volume - 1) if current_volume is not None else 1
                        )
                if target_volume is not None:
                    target_volume = max(1, target_volume)

            # needs rewrite
            needs_rewrite = False
            if ctx.history:
                words = [w.strip(_PUNCT) for w in q_norm.split()]
                if any(w in UYGHUR_PRONOUN_TOKENS for w in words):
                    if not (has_title or has_author) or len(words) < 8:
                        needs_rewrite = True

            intent = "passage"

        return {
            "top_intent": "current_page" if is_current_page_query else "content_search",
            "catalog_subtype": catalog_subtype,
            "has_title": has_title,
            "has_author": has_author,
            "is_volume_shift": is_volume_shift,
            "target_volume": target_volume,
            "needs_rewrite": needs_rewrite,
            "in_reader": in_reader,
            "has_current_book": has_current_book,
            "has_context_books": has_context_books,
            "is_global": is_global,
            "graph_available": graph_available,
            "intent": intent,
            "rewritten_question": rewritten_question if needs_rewrite else None,
            "is_composite": is_composite,
            "sub_questions": sub_questions,
            "matched_books": matched_books,
            "matched_author_books": matched_author_books,
        }

    async def classify_intent(
        self, signals: dict, question: str, ctx: QueryContext
    ) -> str:
        """Stage 3: Intent Classifier — returns pre-extracted intent, or falls back to classification LLM."""
        if "intent" in signals:
            return signals["intent"]

        top_intent = signals.get("top_intent")
        if top_intent == "current_page":
            return "passage"

        has_title = signals.get("has_title", False)
        has_author = signals.get("has_author", False)
        is_volume_shift = signals.get("is_volume_shift", False)
        in_reader = signals.get("in_reader", False)
        has_context_books = signals.get("has_context_books", False)
        is_global = signals.get("is_global", False)

        # Skip classification if signals are sufficient
        if has_author and not has_title:
            return "passage"
        if is_volume_shift:
            return "passage"
        if in_reader and not has_title and not has_author:
            return "passage"

        signals_summary = f"has_title={has_title}, has_context_books={has_context_books}, is_global={is_global}"

        prompt = f"""Classify this Uyghur/English question into ONE intent.

Intents:
- catalog     : asking about book metadata, authors of books, book listings, or what books exist in the library (e.g., who wrote X, list X's books, do you have book Y)
- identity    : asking who/what a person or character IS (biography, role, background)
- summary     : asking about the plot, themes, or main characters of a book
- relationship: asking about connections, lineages, family trees, or how X and Y relate
- passage     : asking for specific events, facts, quotes, or details — including "tell me about X's actions"

Examples:
- "زوردۇن سابىر كىم؟" -> {{"intent": "identity"}}
- "سادات بوۋاي كىمنىڭ ئوغلى؟" -> {{"intent": "relationship"}}
- "ئانا يۇرت رومانىنىڭ باش تېمىسى نېمە؟" -> {{"intent": "summary"}}
- "ئانا يۇرت رومانى قاچان يېزىلغان؟" -> {{"intent": "passage"}}
- "يۇلتۇزلۇق تۈنلەر رومانى كىمنىڭ؟" -> {{"intent": "catalog"}}
- "سەندە قانداق كىتابلار بار؟" -> {{"intent": "catalog"}}

Question: {question}
Context signals: {signals_summary}

Return ONLY valid JSON matching this schema:
{{"intent": "catalog" | "identity" | "summary" | "relationship" | "passage"}}
"""
        try:
            llm = build_text_llm(ctx.agent_model)
            res_text = await llm.ainvoke(
                prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            m = re.search(r"\{.*\}", res_text, re.DOTALL)
            if m:
                repaired_json = repair_json_unescaped_quotes(m.group())
                data = json.loads(repaired_json)
                intent = data.get("intent", "passage").strip().lower()
                if intent in {
                    "catalog",
                    "identity",
                    "summary",
                    "relationship",
                    "passage",
                }:
                    log_json(logger, logging.INFO, "Intent classified", intent=intent)
                    return intent
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "Intent classification LLM call failed, defaulting to passage",
                error=str(exc),
            )
        return "passage"

    async def _build_sub_signals_from_llm(
        self, sub_q_data: dict, ctx: QueryContext
    ) -> dict:
        """Build signals for a sub-question from LLM-extracted fields + DB lookups.

        Avoids a redundant _llm_analyze_query call per sub-question by reusing the
        per-item signals already returned by the composite question's first LLM call.
        DB lookups (title/author) are still run per sub-question since they can't
        be resolved inside the LLM.
        """
        sub_q = sub_q_data["question"]

        matched_books = await find_books_by_title_in_db(sub_q, ctx)
        has_title = bool(matched_books)

        books_repo = BooksRepository(ctx.session)
        matched_author_books = await books_repo.find_books_by_author_in_question(
            sub_q, categories=ctx.character_categories or None
        )
        has_author = bool(matched_author_books)

        in_reader = ctx.current_page is not None
        has_current_book = ctx.book_id is not None and not ctx.is_global
        has_context_books = len(ctx.context_book_ids) > 0
        is_global = ctx.is_global
        graph_available = (
            getattr(ctx.book, "graph_milestone", None) == "complete"
            if ctx.book
            else False
        )

        is_current_page_query = sub_q_data.get("is_current_page_query", False)
        is_volume_shift = sub_q_data.get("is_volume_shift", False)
        target_volume = sub_q_data.get("target_volume")
        catalog_subtype = sub_q_data.get("catalog_subtype") or "general"
        intent = sub_q_data.get("intent", "passage")

        return {
            "top_intent": "current_page" if is_current_page_query else "content_search",
            "catalog_subtype": catalog_subtype,
            "has_title": has_title,
            "has_author": has_author,
            "is_volume_shift": is_volume_shift,
            "target_volume": target_volume,
            "needs_rewrite": False,
            "in_reader": in_reader,
            "has_current_book": has_current_book,
            "has_context_books": has_context_books,
            "is_global": is_global,
            "graph_available": graph_available,
            "intent": intent,
            "rewritten_question": None,
            "is_composite": False,
            "sub_questions": None,
            "matched_books": matched_books,
            "matched_author_books": matched_author_books,
        }

    async def execute_path(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        """Stage 4: Execution Router — picks and runs a fixed path."""
        top_intent = signals.get("top_intent")
        result_holder = {}

        # --- Path A: Current Page ---
        if top_intent == "current_page" and signals.get("in_reader"):
            async for ev in self._run_tool_and_yield(
                "get_current_page", {}, ctx, observations, result_holder
            ):
                yield ev
            return

        # --- Path B: Catalog ---
        if intent == "catalog":
            subtype = signals.get("catalog_subtype", "general")
            if subtype == "author_of":
                async for ev in self._run_tool_and_yield(
                    "get_book_author",
                    {"question": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            elif subtype == "books_by":
                async for ev in self._run_tool_and_yield(
                    "get_books_by_author",
                    {"question": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            else:
                async for ev in self._run_tool_and_yield(
                    "search_catalog",
                    {"query": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            return

        # --- Path C: Named Title ---
        if signals.get("has_title"):
            matched_books = signals.get("matched_books", [])
            matched_book_ids = (
                [str(b["id"]) for b in matched_books]
                if isinstance(matched_books, list)
                else []
            )

            # Check if we already ran find_books_by_title and got the same book IDs in this request
            prev_title_call = next(
                (
                    obs
                    for obs in observations
                    if obs.get("tool") == "find_books_by_title"
                    and set(
                        str(bid) for bid in obs.get("result", {}).get("book_ids", [])
                    )
                    == set(matched_book_ids)
                ),
                None,
            )

            if prev_title_call:
                title_res = prev_title_call["result"]
                result_holder["result"] = title_res
                book_ids = title_res.get("book_ids", [])
            else:
                async for ev in self._run_tool_and_yield(
                    "find_books_by_title",
                    {"question": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                title_res = result_holder["result"]
                book_ids = title_res.get("book_ids", [])

            # Fallback for summary lookups
            if (intent == "summary" or intent == "identity") and not book_ids:
                async for ev in self._run_tool_and_yield(
                    "search_books_by_summary",
                    {"query": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                summary_search_res = result_holder["result"]
                book_ids = summary_search_res.get("book_ids", [])

            if intent == "summary":
                async for ev in self._run_tool_and_yield(
                    "get_book_summary",
                    {"book_ids": book_ids[:5]},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            elif intent == "identity":
                async for ev in self._run_tool_and_yield(
                    "get_book_summary",
                    {"book_ids": book_ids[:5]},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            elif intent == "relationship":
                if signals.get("graph_available"):
                    async for ev in self._run_tool_and_yield(
                        "query_knowledge_graph",
                        {"query": question, "book_ids": book_ids},
                        ctx,
                        observations,
                        result_holder,
                    ):
                        yield ev
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            else:  # intent == passage
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev

            async for ev in self._run_universal_fallback(question, ctx, observations):
                yield ev
            return

        # --- Path D: Named Author (no title) ---
        if signals.get("has_author") and not signals.get("has_title"):
            matched_author_books = signals.get("matched_author_books", [])
            matched_author_book_ids = (
                [str(b.id) for b in matched_author_books]
                if isinstance(matched_author_books, list)
                else []
            )

            # Check if we already ran get_books_by_author and got the same book IDs in this request
            prev_author_call = next(
                (
                    obs
                    for obs in observations
                    if obs.get("tool") == "get_books_by_author"
                    and set(
                        str(b["id"]) for b in obs.get("result", {}).get("books", [])
                    )
                    == set(matched_author_book_ids)
                ),
                None,
            )

            if prev_author_call:
                author_res = prev_author_call["result"]
                result_holder["result"] = author_res
                books_list = author_res.get("books", [])
                author_book_ids = [b["id"] for b in books_list]
            else:
                async for ev in self._run_tool_and_yield(
                    "get_books_by_author",
                    {"question": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                author_res = result_holder["result"]
                books_list = author_res.get("books", [])
                author_book_ids = [b["id"] for b in books_list]
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": author_book_ids},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            async for ev in self._run_universal_fallback(question, ctx, observations):
                yield ev
            return

        # --- Path E: Volume Shift ---
        if signals.get("is_volume_shift") and (
            signals.get("in_reader") or signals.get("has_context_books")
        ):
            current_book_id = ctx.book_id if (ctx.book and not ctx.is_global) else None
            source_book_id = current_book_id or (
                ctx.context_book_ids[0] if ctx.context_book_ids else None
            )
            if source_book_id:
                repo = BooksRepository(ctx.session)
                books = await repo.find_sister_volumes(source_book_id)

                # Register the get_sister_volumes call in observations for tracing
                async for ev in self._run_tool_and_yield(
                    "get_sister_volumes",
                    {"book_id": source_book_id},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev

                target_volume = signals.get("target_volume")
                target_volume_id = None
                if books and target_volume is not None:
                    for b in books:
                        if b.volume == target_volume:
                            target_volume_id = str(b.id)
                            break

                search_book_ids = (
                    [target_volume_id]
                    if target_volume_id
                    else [str(b.id) for b in books]
                )
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": search_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                async for ev in self._run_universal_fallback(
                    question, ctx, observations
                ):
                    yield ev
            return

        # --- Path F: In-Reader, No Title/Author ---
        if (
            signals.get("in_reader")
            and not signals.get("has_title")
            and not signals.get("has_author")
        ):
            current_book_id = ctx.book_id
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": [current_book_id]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            async for ev in self._run_universal_fallback(question, ctx, observations):
                yield ev
            return

        # --- Path G: Prior Context, No Title/Author ---
        if signals.get("has_context_books"):
            context_book_ids = ctx.context_book_ids
            if intent == "identity":
                async for ev in self._run_tool_and_yield(
                    "search_books_by_summary",
                    {"query": question, "book_ids": context_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                summary_res = result_holder["result"]
                verified_ids = summary_res.get("book_ids", [])
                if verified_ids:
                    async for ev in self._run_tool_and_yield(
                        "get_book_summary",
                        {"book_ids": verified_ids[:5]},
                        ctx,
                        observations,
                        result_holder,
                    ):
                        yield ev
                    async for ev in self._run_tool_and_yield(
                        "search_chunks",
                        {"query": question, "book_ids": verified_ids},
                        ctx,
                        observations,
                        result_holder,
                    ):
                        yield ev
                else:
                    async for ev in self._run_tool_and_yield(
                        "search_chunks",
                        {"query": question, "book_ids": context_book_ids},
                        ctx,
                        observations,
                        result_holder,
                    ):
                        yield ev
            elif intent == "summary":
                async for ev in self._run_tool_and_yield(
                    "get_book_summary",
                    {"book_ids": context_book_ids[:5]},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": context_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            elif intent == "relationship":
                if signals.get("graph_available"):
                    async for ev in self._run_tool_and_yield(
                        "query_knowledge_graph",
                        {"query": question, "book_ids": context_book_ids},
                        ctx,
                        observations,
                        result_holder,
                    ):
                        yield ev
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": context_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
            else:  # intent == passage
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": context_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev

            async for ev in self._run_universal_fallback(question, ctx, observations):
                yield ev
            return

        # --- Path H: Open / No Context ---
        # intent routing for global searches
        # search_books_by_summary returns up to 20 books; passing all 20 to search_chunks
        # spreads RAG_TOP_K=25 slots across too many books (~1-2 per book), diluting the
        # specific passage that may only appear in 1 book. Focus on top 5 to concentrate
        # chunk slots. The universal fallback widens to global scope if results are thin.
        _TOP_BOOKS_FOR_CHUNK_SEARCH = 5
        if intent == "identity":
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            top_ids = summary_res.get("book_ids", [])
            async for ev in self._run_tool_and_yield(
                "get_book_summary",
                {"book_ids": top_ids[:5]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": top_ids[:_TOP_BOOKS_FOR_CHUNK_SEARCH]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif intent == "summary":
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            top_ids = summary_res.get("book_ids", [])
            async for ev in self._run_tool_and_yield(
                "get_book_summary",
                {"book_ids": top_ids[:5]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": top_ids[:_TOP_BOOKS_FOR_CHUNK_SEARCH]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif intent == "relationship":
            async for ev in self._run_tool_and_yield(
                "query_knowledge_graph",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            top_ids = summary_res.get("book_ids", [])
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": top_ids[:_TOP_BOOKS_FOR_CHUNK_SEARCH]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        else:  # intent == passage
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            top_ids = summary_res.get("book_ids", [])
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": top_ids[:_TOP_BOOKS_FOR_CHUNK_SEARCH]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

        async for ev in self._run_universal_fallback(question, ctx, observations):
            yield ev

    async def _execute_tool(
        self, tool_name: str, tool_args: dict, ctx: QueryContext, observations: list
    ) -> AsyncIterator[dict]:
        yield {"type": "tool_call", "tool": tool_name, "name": tool_name}
        try:
            res = await _dispatch_tool_with_retry(tool_name, tool_args, ctx)
        except Exception as exc:
            observations.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": {"ok": False, "error": str(exc)},
                }
            )
            yield {"type": "tool_result", "tool": tool_name, "found": 0}
            raise

        observations.append(
            {
                "tool": tool_name,
                "args": tool_args,
                "result": res,
            }
        )

        found = res.get("found_count", 0)
        yield {"type": "tool_result", "tool": tool_name, "found": found}
        yield {"type": "tool_done_result", "result": res}

    async def _run_tool_and_yield(
        self,
        tool_name: str,
        tool_args: dict,
        ctx: QueryContext,
        observations: list,
        result_holder: dict,
    ) -> AsyncIterator[dict]:
        async for event in self._execute_tool(tool_name, tool_args, ctx, observations):
            if event.get("type") == "tool_done_result":
                result_holder["result"] = event["result"]
            else:
                yield event

    async def _run_universal_fallback(
        self, question: str, ctx: QueryContext, observations: list
    ) -> AsyncIterator[dict]:
        """Universal Fallback — checks last chunk search results and expands scope if needed."""
        from app.services.rag.agent.config import CONTEXT_SWITCH_SCORE_THRESHOLD

        if not observations:
            return
        last_obs = observations[-1]
        if last_obs.get("tool") != "search_chunks":
            return
        res = last_obs.get("result", {})
        if not res.get("ok", False):
            return

        chunks = res.get("chunks", [])
        top_score = max((c.get("score", 0.0) for c in chunks), default=0.0)
        if len(chunks) >= 4 and top_score >= CONTEXT_SWITCH_SCORE_THRESHOLD:
            return

        # 1. Check if search_books_by_summary was already run
        already_searched_summaries = any(
            obs.get("tool") == "search_books_by_summary" for obs in observations
        )

        new_book_ids = []
        result_holder = {}
        if not already_searched_summaries:
            # Re-run search_books_by_summary(question)
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            new_book_ids = summary_res.get("book_ids", [])
            # Re-run search_chunks(new_book_ids)
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": new_book_ids},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            chunks_res = result_holder["result"]
            chunks = chunks_res.get("chunks", [])

        # 2. Still < 4 results: widen to global scope
        if len(chunks) < 4:
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": None},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

    async def _execute_workflow_stream(
        self, ctx: QueryContext, question: str, observations: list
    ) -> AsyncIterator[dict]:
        # 1. Stage 1: Detect top intent
        signals_orig = await self.extract_signals(question, ctx)
        top_intent = signals_orig.get("top_intent")
        yield {"type": "planning", "intent": top_intent}

        # 2. Stage 2: Coreference Resolution
        needs_rewrite = signals_orig.get("needs_rewrite", False)
        is_composite = signals_orig.get("is_composite", False)
        sub_questions = signals_orig.get("sub_questions")

        llm_calls = 0
        if "intent" in signals_orig:
            llm_calls += 1

        if needs_rewrite:
            rewritten_question = signals_orig.get("rewritten_question")
            if rewritten_question:
                ctx.enriched_question = rewritten_question
                # Record to observations for tracing
                res = {
                    "ok": True,
                    "rewritten_question": rewritten_question,
                    "found_count": 0,
                }
                observations.append(
                    {
                        "tool": "rewrite_query",
                        "args": {"question": question},
                        "result": res,
                    }
                )
                # Yield frontend events to preserve UI rewrite animations
                yield {
                    "type": "tool_call",
                    "tool": "rewrite_query",
                    "name": "rewrite_query",
                }
                yield {"type": "tool_result", "tool": "rewrite_query", "found": 0}
            else:
                # Fallback to separate LLM tool execution on fallback path
                result_holder = {}
                async for ev in self._run_tool_and_yield(
                    "rewrite_query",
                    {"question": question},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
                llm_calls += 1

        # 3. Query Decomposition (splitting multi-questions)
        if is_composite and isinstance(sub_questions, list) and len(sub_questions) > 1:
            yield {"type": "decompose", "count": len(sub_questions)}
        else:
            # Not composite or no sub_questions returned, use single question path
            question_to_process = ctx.enriched_question or ctx.question
            sub_questions = [question_to_process]

        # 4. Stage 3 & 4: Intent Classifier and Execution Router per sub-question
        sub_question_texts: list[str] = []
        for sub_q_item in sub_questions:
            if isinstance(sub_q_item, dict):
                # Optimized path: signals already extracted by the first LLM call.
                # Only DB lookups (title/author) are re-run per sub-question.
                sub_q = sub_q_item["question"]
                sub_signals = await self._build_sub_signals_from_llm(sub_q_item, ctx)
            else:
                sub_q = sub_q_item
                if len(sub_questions) == 1 and sub_q == question:
                    sub_signals = signals_orig.copy()
                else:
                    sub_signals = await self.extract_signals(sub_q, ctx)
                    sub_signals["needs_rewrite"] = False
                    if "intent" in sub_signals:
                        llm_calls += 1

            sub_question_texts.append(sub_q)

            # Classify sub-question intent
            sub_intent = await self.classify_intent(sub_signals, sub_q, ctx)
            if "intent" not in sub_signals:
                if (
                    sub_intent != "passage"
                    or sub_signals.get("has_title")
                    or sub_signals.get("has_context_books")
                    or sub_signals.get("is_global")
                ):
                    # Intent classification LLM was run for non-skipped flows
                    llm_calls += 1

            # Run execution path
            async for ev in self.execute_path(
                sub_intent, sub_signals, sub_q, ctx, observations
            ):
                yield ev

        # 5. Grading and Post-processing
        graded_context, before_count, after_count = _grade_context(observations)

        # Update QueryContext metrics
        used_book_ids = _extract_used_book_ids(observations)
        ctx.used_book_ids = used_book_ids
        _populate_ctx_from_observations(ctx, observations, graded_context, llm_calls)

        yield {
            "type": "result",
            "sub_questions": sub_question_texts,
            "observations": observations,
            "llm_calls": llm_calls,
            "graded_context": graded_context,
            "before_count": before_count,
            "after_count": after_count,
        }

    async def handle(self, ctx: QueryContext) -> str:
        from app.utils.citation_fixer import fix_malformed_citations
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(
            logger,
            logging.INFO,
            "Deterministic RAG handler invoked (non-stream)",
            model=ctx.agent_model,
        )

        question = ctx.question
        observations = []
        sub_questions = None
        graded_context = None

        async for event in self._execute_workflow_stream(ctx, question, observations):
            if event.get("type") == "result":
                sub_questions = event["sub_questions"]
                graded_context = event["graded_context"]

        if graded_context is None or sub_questions is None:
            log_json(
                logger,
                logging.WARNING,
                "Deterministic RAG workflow yielded no result event — fallback to empty context",
            )
            graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            sub_questions = [question]

        final_question = (
            "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            if len(sub_questions) > 1
            else (ctx.enriched_question or ctx.question)
        )

        answer_chunks = []
        async for token in generate_answer_stream(
            graded_context,
            final_question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            answer_chunks.append(token)

        answer = "".join(answer_chunks)
        return fix_malformed_citations(answer)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[Union[str, dict]]:
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(
            logger,
            logging.INFO,
            "Deterministic RAG handler invoked (stream)",
            model=ctx.agent_model,
        )

        question = ctx.question
        observations = []
        sub_questions = None
        graded_context = None
        before_count = 0
        after_count = 0

        async for event in self._execute_workflow_stream(ctx, question, observations):
            if event.get("type") == "result":
                sub_questions = event["sub_questions"]
                graded_context = event["graded_context"]
                before_count = event.get("before_count", 0)
                after_count = event.get("after_count", 0)
            else:
                yield event

        if graded_context is None or sub_questions is None:
            log_json(
                logger,
                logging.WARNING,
                "Deterministic RAG workflow yielded no result event — fallback to empty context",
            )
            graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            sub_questions = [question]

        if before_count > 0:
            yield {"type": "grading", "before": before_count, "after": after_count}

        final_question = (
            "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            if len(sub_questions) > 1
            else (ctx.enriched_question or ctx.question)
        )

        yield {"type": "answer_start"}
        async for token in generate_answer_stream(
            graded_context,
            final_question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield {"type": "chunk", "text": token}
        yield {"type": "answer_end"}


async def find_books_by_title_in_db(question: str, ctx: QueryContext) -> list[dict]:
    """Helper to synchronously trigger title checks by invoking find_books_by_title_in_question."""
    from app.services.rag.retrieval import find_books_by_title_in_question

    if not hasattr(ctx, "_title_cache"):
        ctx._title_cache = {}
    if question in ctx._title_cache:
        return ctx._title_cache[question]

    try:
        books = await find_books_by_title_in_question(
            question, ctx.session, categories=ctx.character_categories or None
        )
        result = books or []
        ctx._title_cache[question] = result
        return result
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Failed to find books by title in database",
            error=str(exc),
        )
    return []
