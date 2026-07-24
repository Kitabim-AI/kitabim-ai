"""DeterministicRAGHandler — deterministic, python-based RAG router.

Replaces LLM-driven ADK ReAct agent sequences with a deterministic decision tree
built on extracted signals and conditional intent classification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator, TYPE_CHECKING, Union
from google.genai import types

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json
from app.services.rag.agent.tools import _dispatch_tool_with_retry
from app.services.rag.utils import normalize_uyghur
from app.db.repositories.books_repository import BooksRepository
from app.llm.models import build_text_llm

from app.services.rag.agent.llm_routed_handler import (
    _grade_context,
    _extract_used_book_ids,
    _populate_ctx_from_observations,
)

from app.services.rag.keywords import (
    UYGHUR_PRONOUN_TOKENS,
    VOLUME_SHIFT_KEYWORDS,
    CATALOG_AUTHOR_QUERIES,
    CATALOG_BOOKS_QUERIES,
    PAGE_QUERY_PATTERNS,
)

if TYPE_CHECKING:
    from app.services.rag.agent.graph_router import RunnerServices

logger = logging.getLogger("app.rag.agent.deterministic_handler")

# Punctuation boundaries for pronouns
_PUNCT = "«»،؟!()[]{}\"''"


def _cap_summary_book_ids(book_ids: list, books: list, cap: int = 5) -> list[str]:
    """Cap book IDs passed to get_book_summary at *cap*, unless every book is a
    volume of the same title+author series — a named-title lookup can legitimately
    resolve to more than 5 sister volumes, and none should be silently dropped."""
    if not books:
        return [str(bid) for bid in book_ids][:cap]
    first_title, first_author = books[0].get("title"), books[0].get("author")
    is_single_series = all(
        b.get("title") == first_title and b.get("author") == first_author for b in books
    )
    ids = [str(b["id"]) for b in books]
    return ids if is_single_series else ids[:cap]


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


async def _merge_sub_question_streams(
    generators: list,
) -> AsyncIterator[tuple[int, object]]:
    """Runs multiple async generators concurrently, yielding (index, item)
    tuples as items arrive from any of them — arrival order, not generator
    order, so events from a fast sub-question can interleave with a slow
    one's rather than waiting for it.

    Re-raises the first exception encountered (after cancelling the rest)
    once that generator's stream ends — by then its own items are already
    yielded, matching "partial work already visible before the error" the
    same way the sequential loop always has.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()
    errors: dict[int, BaseException] = {}

    async def _drain(gen, idx: int) -> None:
        try:
            async for item in gen:
                await queue.put((idx, item))
        except BaseException as exc:  # noqa: BLE001 - re-raised by the caller below
            errors[idx] = exc
        finally:
            await queue.put((idx, _DONE))

    tasks = [asyncio.create_task(_drain(gen, i)) for i, gen in enumerate(generators)]
    remaining = len(tasks)
    try:
        while remaining > 0:
            idx, item = await queue.get()
            if item is _DONE:
                remaining -= 1
                if idx in errors:
                    raise errors[idx]
                continue
            yield idx, item
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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

        Uses a single structured JSON response to classify query properties,
        using tool calls to resolve book titles/authors dynamically.
        """
        in_reader = (ctx.current_page is not None) or (
            not ctx.is_global and bool(ctx.book_id)
        )
        current_page = ctx.current_page
        has_history = len(ctx.history) > 0
        history_str = ctx.chat_history_str if has_history else "None"

        async def find_books_by_title(question: str) -> dict:
            """Find books matching a title mentioned in the question.

            Args:
                question: The user's query containing the book title.
            """
            return await _dispatch_tool_with_retry(
                "find_books_by_title", {"question": question}, ctx
            )

        async def get_books_by_author(question: str) -> dict:
            """Find books written by an author mentioned in the question.

            Args:
                question: The user's query containing the author's name.
            """
            return await _dispatch_tool_with_retry(
                "get_books_by_author", {"question": question}, ctx
            )

        prompt = f"""Analyze this Uyghur/English query in the context of a RAG book reading assistant.

Context:
- In Reader (Active Book Context): {in_reader} (Page: {current_page})
- Has Chat History: {has_history}

Chat History:
{history_str}

Query: {question}

Database Tools:
You have access to tools to query the book database:
- `find_books_by_title(question)`: Call this if the query mentions a specific book title or title keyword to check if the book exists in the library.
- `get_books_by_author(question)`: Call this if the query mentions a specific author to check what books by this author exist in the library.

Before returning the final JSON, call these tools if the user is asking about specific books or authors, so you can determine the catalog signals accurately.

Important Guidelines for Tool Use:
- If a tool call (e.g., `find_books_by_title` or `get_books_by_author`) returns no books or empty results (e.g., `books: []` or `found_count: 0`), do NOT call the tools again with the same or similar arguments.
- Once you have called a tool and successfully found one or more matching books or authors (i.e., `books` is not empty, `found_count > 0`), do NOT keep calling tools to search for other variations of the same name or title. Stop calling tools immediately and output the final JSON response.
- If you cannot find any matching books/authors via tools, stop calling tools and immediately return the final JSON classification with the best available signals. Do not get stuck in an execution loop.

Return ONLY valid JSON matching this schema:
{{
  "is_current_page_query": boolean, // True if the user asks about the page/text they are currently looking at (e.g. "what is on this page", "read this page", "بۇ بەتتە نېمە بار")
  "is_volume_shift": boolean,       // True if the user wants to go to another volume (e.g. "next volume", "previous volume", "ئالدىنقى توم", "2-توم")
  "target_volume": integer | null,  // The volume number to shift to if specified (e.g. 2, 3), else null
  "needs_rewrite": boolean,         // True ONLY if the query has unresolved pronouns/coreferences or implicit references (ellipsis) referring to prior chat history. MUST be false if the query is fully self-contained, or if there is no chat history.
  "rewritten_question": string | null, // If needs_rewrite is true, rewrite the question to resolve all pronouns/references using chat history to make it self-contained in Uyghur/English. If needs_rewrite is false, return null.
  "catalog_subtype": "author_of" | "books_by" | "general" | null, // Use "author_of" if asking who wrote a book, "books_by" if asking what books an author wrote, "general" for other catalog/library-wide queries (like "what books do you have"), or null if this is NOT a catalog query.
  "dictionary_subtype": "uyghur_definition" | "history_term" | "english_uyghur" | "spelling" | "names" | "proverbs" | "synonyms" | "general" | null, // Use only when intent is "dictionary".
  "dictionary_term": string | null, // The exact word/term/name/English phrase to look up when intent is "dictionary".
  "quran_surah": integer | null,    // The surah number (1-114) if specified (e.g. 1 for Fatihah, 2 for Baqarah), or null.
  "quran_ayah": integer | null,     // The ayah/verse number if specified, or null.
  "quran_query": string | null,     // The text query or keyword to search inside Quranic verses, or null.
  "intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran",
  "is_composite": boolean,          // True if the query contains multiple distinct questions or requests that should be handled separately (e.g. "Who wrote X and what is it about?").
  "sub_questions": Array<{{         // If is_composite is true, return each sub-question with its own signals. If is_composite is false, return null.
    "question": string,             // Self-contained sub-question text (pronouns resolved using history)
    "intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran",
    "is_current_page_query": boolean,
    "is_volume_shift": boolean,
    "target_volume": integer | null,
    "catalog_subtype": "author_of" | "books_by" | "general" | null,
    "dictionary_subtype": "uyghur_definition" | "history_term" | "english_uyghur" | "spelling" | "names" | "proverbs" | "synonyms" | "general" | null,
    "dictionary_term": string | null,
    "quran_surah": integer | null,
    "quran_ayah": integer | null,
    "quran_query": string | null
  }}> | null
}}

Intents:
- catalog     : asking about book metadata, authors of books, book listings, or what books exist in the library
- dictionary  : asking for word meanings, dictionary definitions, spelling validity, names, synonyms, historical vocabulary headword explanations, or English-to-Uyghur translation
- identity    : asking who/what a person or character IS (biography, role, background)
- summary     : asking about the plot, themes, or main characters of a book
- relationship: asking about connections, lineages, family trees, or how X and Y relate
- passage     : asking for specific events, facts, quotes, details, timelines, dates, or historical events/origins (e.g., "when and how was X founded?", "why did X happen?", "tell me about X's history")
- quran       : asking about Quran surahs, verses (ayahs), translations, or searching for specific verses/phrases in the Quran (e.g., "what is surah 1?", "read ayah 1:2", "فاتىھە سۈرىسى", "ئاللاھنىڭ ئىسمى بىلەن باشلايمەن قايسى سۈرىدە بار؟")

Dictionary subtype rules:
- "uyghur_definition": Uyghur word meaning or definition ("X دېگەن نېمە؟", "X مەنىسى نېمە؟")
- "history_term": historical entity/person/place lookup for direct headword definition (e.g. "X كىم؟", "X نېمە؟"). Do NOT use "dictionary" for complex historical questions asking about events, origins, timelines, dates, or causes (e.g. "when/how was X founded?", "why did X happen?") — classify those as "passage".
- "english_uyghur": user asks for the Uyghur translation/equivalent of an English word or phrase
- "spelling": user asks whether a Uyghur spelling is correct or valid
- "names": Uyghur person name lookup, or listing/asking about names starting with a specific letter/alphabet (e.g. "ب ھەرىپىدىن باشلانغان كىشى ئىسىملىرى", "ئالىم دېگەن ئىسىم"). For requests listing names starting with a letter, extract the target letter (e.g., "ب") as the dictionary_term.
- "proverbs": user asks for proverbs, Uyghur proverbs/sayings, or searches for proverbs containing a word (e.g. "ماقال-تەمسىللەر", "بىلىم ھەققىدە ماقال-تەمسىل", "proverb about knowledge")
- "synonyms": user asks for synonyms of a Uyghur word, words with the same or similar meaning, or a list of synonym-dictionary headwords starting with a letter (e.g. "مەنىداش سۆز", "X نىڭ مەنىداش سۆزى نېمە؟", "ئوخشاش مەنىلىك سۆزلەر", "synonym for X")
- "general": dictionary-style query where the exact source is unclear
"""
        from app.llm.models import _get_text_client

        client = _get_text_client()
        model = (
            ctx.agent_model.replace("models/", "", 1)
            if ctx.agent_model.startswith("models/")
            else ctx.agent_model
        )

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        ]

        matched_books = []
        matched_author_books = []
        has_title = False
        has_author = False

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            tools=[find_books_by_title, get_books_by_author],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

        tools_invoked = False

        for _ in range(3):
            # One round of tool calls is all we allow: after the model has had a
            # chance to resolve titles/authors, force the final JSON on the next
            # turn instead of trusting prompt-level "stop calling tools" guidance.
            if tools_invoked and config.tools is not None:
                config.tools = None

            res_obj = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            # Add model response to history
            if res_obj.candidates and res_obj.candidates[0].content:
                contents.append(res_obj.candidates[0].content)

            # Check for function calls
            if res_obj.function_calls:
                tools_invoked = True
                parts = []
                for call in res_obj.function_calls:
                    name = call.name
                    args = call.args or {}
                    # Execute tool
                    if name == "find_books_by_title":
                        tool_res = await find_books_by_title(**args)
                        if tool_res.get("ok"):
                            books = tool_res.get("books", [])
                            matched_books.extend(books)
                            if books:
                                has_title = True
                    elif name == "get_books_by_author":
                        tool_res = await get_books_by_author(**args)
                        if tool_res.get("ok"):
                            books = tool_res.get("books", [])
                            matched_author_books.extend(books)
                            if books:
                                has_author = True
                    else:
                        tool_res = {"ok": False, "error": f"Unknown tool: {name}"}

                    parts.append(
                        types.Part.from_function_response(name=name, response=tool_res)
                    )
                contents.append(types.Content(role="user", parts=parts))
            else:
                # No more function calls, parse final text response
                res_text = res_obj.text or ""
                break
        else:
            raise ValueError("Too many tool call iterations in query analysis")

        m = re.search(r"\{.*\}", res_text, re.DOTALL)
        if m:
            repaired_json = repair_json_unescaped_quotes(m.group())
            result = json.loads(repaired_json)

            # Deduplicate books by ID
            seen_books = set()
            deduped_books = []
            for b in matched_books:
                bid = b.get("id")
                if bid not in seen_books:
                    seen_books.add(bid)
                    deduped_books.append(b)

            seen_author_books = set()
            deduped_author_books = []
            for b in matched_author_books:
                bid = b.get("id")
                if bid not in seen_author_books:
                    seen_author_books.add(bid)
                    deduped_author_books.append(b)

            result["has_title"] = has_title
            result["has_author"] = has_author
            result["matched_books"] = deduped_books
            result["matched_author_books"] = deduped_author_books

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
        in_reader = (ctx.current_page is not None) or (
            not ctx.is_global and bool(ctx.book_id)
        )
        has_current_book = ctx.book_id is not None and not ctx.is_global
        has_context_books = len(ctx.context_book_ids) > 0
        is_global = ctx.is_global

        # 1. LLM query analysis (intent & signals) with keyword fallback fallback
        try:
            llm_res = await self._llm_analyze_query(question, ctx)
            is_current_page_query = llm_res.get("is_current_page_query", False)
            is_volume_shift = llm_res.get("is_volume_shift", False)
            target_volume = llm_res.get("target_volume")
            needs_rewrite = llm_res.get("needs_rewrite", False)
            rewritten_question = llm_res.get("rewritten_question")
            catalog_subtype = llm_res.get("catalog_subtype") or "general"
            dictionary_subtype = llm_res.get("dictionary_subtype") or "general"
            dictionary_term = llm_res.get("dictionary_term")
            quran_surah = llm_res.get("quran_surah")
            quran_ayah = llm_res.get("quran_ayah")
            quran_query = llm_res.get("quran_query")
            intent = llm_res.get("intent", "passage")
            is_composite = llm_res.get("is_composite", False)
            sub_questions = llm_res.get("sub_questions")

            # Extract the database query results captured during tool calling!
            has_title = llm_res.get("has_title", False)
            has_author = llm_res.get("has_author", False)
            matched_books = llm_res.get("matched_books", [])
            matched_author_books = llm_res.get("matched_author_books", [])
        except Exception as exc:
            # Run DB queries as a fallback when LLM fails
            matched_books = await find_books_by_title_in_db(question, ctx)
            has_title = bool(matched_books)
            books_repo = BooksRepository(ctx.session)
            matched_author_books = await books_repo.find_books_by_author_in_question(
                question, categories=ctx.character_categories or None
            )
            has_author = bool(matched_author_books)

            rewritten_question = None
            is_composite = False
            sub_questions = None
            dictionary_subtype = "general"
            dictionary_term = None
            quran_surah = None
            quran_ayah = None
            quran_query = None
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
            quran_surah = None
            quran_ayah = None
            quran_query = None
            quran_keywords = [
                "قۇرئان",
                "سۈرە",
                "ئايەت",
                "سۈرىسى",
                "quran",
                "surah",
                "ayah",
                "verse",
            ]
            is_quran_query = any(
                normalize_uyghur(k.lower()) in q_norm for k in quran_keywords
            )
            if is_quran_query:
                intent = "quran"

                p_surah = normalize_uyghur("(?:سۈرە|surah|سۈرىسى)")
                p_ayah = normalize_uyghur(
                    "(?:ئايەت|ئايىتى|ئايەتنىڭ|ئايەتتە|ئايەتتىن|ئايىت|ayah|verse)"
                )
                surah_match = re.search(rf"{p_surah}\s*(\d+)|(\d+)-{p_surah}", q_norm)
                ayah_match = re.search(rf"{p_ayah}\s*(\d+)|(\d+)-{p_ayah}", q_norm)
                surah_val = (
                    next((g for g in surah_match.groups() if g is not None), None)
                    if surah_match
                    else None
                )
                ayah_val = (
                    next((g for g in ayah_match.groups() if g is not None), None)
                    if ayah_match
                    else None
                )
                quran_surah = int(surah_val) if surah_val else None
                quran_ayah = int(ayah_val) if ayah_val else None
                quran_query = None
                if not quran_surah:
                    quran_query = question
            elif _looks_like_dictionary_question(q_norm):
                intent = "dictionary"
                dictionary_subtype = _guess_dictionary_subtype(q_norm)
                dictionary_term = _extract_dictionary_term(question)

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
            "intent": intent,
            "dictionary_subtype": dictionary_subtype,
            "dictionary_term": dictionary_term,
            "quran_surah": quran_surah,
            "quran_ayah": quran_ayah,
            "quran_query": quran_query,
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
- dictionary  : asking for word meanings, definitions, spelling validity, historical vocabulary lookup, names dictionary lookup, or English-to-Uyghur translation
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
- "democracy نىڭ ئۇيغۇرچىسى نېمە؟" -> {{"intent": "dictionary"}}
- "ئىنقىلاب دېگەن نېمە؟" -> {{"intent": "dictionary"}}

Question: {question}
Context signals: {signals_summary}

Return ONLY valid JSON matching this schema:
{{"intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran"}}
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
                    "dictionary",
                    "identity",
                    "summary",
                    "relationship",
                    "passage",
                    "quran",
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

        in_reader = (ctx.current_page is not None) or (
            not ctx.is_global and bool(ctx.book_id)
        )
        has_current_book = ctx.book_id is not None and not ctx.is_global
        has_context_books = len(ctx.context_book_ids) > 0
        is_global = ctx.is_global

        is_current_page_query = sub_q_data.get("is_current_page_query", False)
        is_volume_shift = sub_q_data.get("is_volume_shift", False)
        target_volume = sub_q_data.get("target_volume")
        catalog_subtype = sub_q_data.get("catalog_subtype") or "general"
        dictionary_subtype = sub_q_data.get("dictionary_subtype") or "general"
        dictionary_term = sub_q_data.get("dictionary_term")
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
            "intent": intent,
            "dictionary_subtype": dictionary_subtype,
            "dictionary_term": dictionary_term,
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
        runner_services: "RunnerServices | None" = None,
    ) -> AsyncIterator[dict]:
        """Stage 4: Execution Router — builds and runs the ADK graph that
        picks and executes a fixed path.

        Routing itself lives in graph_router.py as a declarative
        google.adk.workflow.Workflow (select_path -> one of the 9 ``_path_*``
        branch methods below via RoutingMap/DEFAULT_ROUTE). Tool-call events
        are bridged through google.genai.types.Content so they never trip
        ADK's one-output-per-node limit, then decoded back into the plain
        dicts this method has always yielded — see graph_router.py's module
        docstring for why.

        Six of the nine branches (named_title, named_author, volume_shift,
        in_reader_only, context_books, open) always run `_run_universal_
        fallback` after their own retrieval — that call is a graph edge
        (see graph_router.py), not inline Python, so it appears in
        `observations` exactly once regardless of which branch ran.
        `_path_catalog` is the one exception: it calls `_run_universal_
        fallback` inline, conditionally, only when the strict title/author
        match found nothing — genuine branch-local business logic, not
        routing structure, so it stays inside the method rather than
        becoming an unconditional edge.

        `runner_services`: pass the same `RunnerServices` instance across
        every sub-question of one chat turn to reuse its session/artifact/
        memory backends instead of building fresh ones per call (see
        graph_router.py). Omit it for a self-contained run — every
        existing caller (including all direct unit tests) does this today.
        """
        from app.services.rag.agent.graph_router import run_path_selection_workflow

        async for ev in run_path_selection_workflow(
            intent, signals, question, ctx, observations, self, runner_services
        ):
            yield ev

    # --- Path A: Current Page ---
    async def _path_current_page(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        async for ev in self._run_tool_and_yield(
            "get_current_page", {}, ctx, observations, result_holder
        ):
            yield ev

    # --- Path: Quran ---
    async def _path_quran(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        surah = signals.get("quran_surah")
        ayah = signals.get("quran_ayah")
        q = signals.get("quran_query") or question
        async for ev in self._run_tool_and_yield(
            "search_quran",
            {"surah": surah, "ayah": ayah, "q": q},
            ctx,
            observations,
            result_holder,
        ):
            yield ev

    # --- Path B: Dictionary / Language Sources ---
    async def _path_dictionary(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        subtype = signals.get("dictionary_subtype") or "general"
        term = (
            signals.get("dictionary_term") or _extract_dictionary_term(question)
        ).strip()
        if not term:
            term = question.strip()

        if subtype == "uyghur_definition":
            async for ev in self._run_tool_and_yield(
                "lookup_uyghur_word",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif subtype == "history_term":
            async for ev in self._run_tool_and_yield(
                "lookup_history_term",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            if result_holder.get("result", {}).get("found_count", 0) == 0:
                async for ev in self._run_tool_and_yield(
                    "search_language_sources",
                    {"query": term},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
        elif subtype == "english_uyghur":
            async for ev in self._run_tool_and_yield(
                "translate_english_to_uyghur",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif subtype == "spelling":
            async for ev in self._run_tool_and_yield(
                "check_word_spelling",
                {"word": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif subtype == "names":
            async for ev in self._run_tool_and_yield(
                "lookup_uyghur_name",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif subtype == "proverbs":
            async for ev in self._run_tool_and_yield(
                "lookup_proverbs",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        elif subtype == "synonyms":
            async for ev in self._run_tool_and_yield(
                "lookup_synonyms",
                {"term": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        else:
            async for ev in self._run_tool_and_yield(
                "search_language_sources",
                {"query": term},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

        # Fallback to book chunk search if no dictionary results were found
        total_found = 0
        for obs in observations:
            if obs.get("tool") in {
                "lookup_uyghur_word",
                "lookup_history_term",
                "translate_english_to_uyghur",
                "check_word_spelling",
                "lookup_uyghur_name",
                "lookup_proverbs",
                "lookup_synonyms",
                "search_language_sources",
            }:
                total_found += obs.get("result", {}).get("found_count", 0)

        if total_found == 0:
            search_query = ctx.enriched_question or question
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": search_query, "book_ids": None},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

    # --- Path B: Catalog ---
    async def _path_catalog(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        subtype = signals.get("catalog_subtype", "general")
        catalog_found = True
        if subtype == "author_of":
            async for ev in self._run_tool_and_yield(
                "get_book_author",
                {"question": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            catalog_found = bool(result_holder.get("result", {}).get("title"))
        elif subtype == "books_by":
            async for ev in self._run_tool_and_yield(
                "get_books_by_author",
                {"question": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            catalog_found = bool(result_holder.get("result", {}).get("books"))
        else:
            async for ev in self._run_tool_and_yield(
                "search_catalog",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            catalog_found = result_holder.get("result", {}).get("book_count", 0) > 0

        # The strict title/author string match found nothing (e.g. the book or
        # author was described rather than named exactly) — fall back to
        # semantic book discovery + chunk search instead of returning empty.
        if not catalog_found:
            async for ev in self._run_tool_and_yield(
                "search_books_by_summary",
                {"query": question},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summary_res = result_holder["result"]
            book_ids = summary_res.get("book_ids", [])
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

    # --- Path C: Named Title ---
    async def _path_named_title(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        matched_books = signals.get("matched_books", [])
        matched_book_ids = (
            [str(b["id"]) for b in matched_books]
            if isinstance(matched_books, list)
            else []
        )

        if matched_book_ids:
            book_ids = matched_book_ids
            title_res = {"ok": True, "book_ids": book_ids, "books": matched_books}
        else:
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

        summary_book_ids = _cap_summary_book_ids(book_ids, title_res.get("books", []))

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
            summary_book_ids = book_ids[:5]

        if intent == "summary":
            async for ev in self._run_tool_and_yield(
                "get_book_summary",
                {"book_ids": summary_book_ids},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
            summaries = result_holder.get("result", {}).get("summaries", [])
            if not summaries:
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
                {"book_ids": summary_book_ids},
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

    # --- Path D: Named Author (no title) ---
    async def _path_named_author(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        matched_author_books = signals.get("matched_author_books", [])
        matched_author_book_ids = (
            [
                str(b.id) if hasattr(b, "id") else str(b["id"])
                for b in matched_author_books
            ]
            if isinstance(matched_author_books, list)
            else []
        )

        if matched_author_book_ids:
            author_book_ids = matched_author_book_ids
            # Convert DB models to standard dict structure if needed
            books_list = []
            for b in matched_author_books:
                if hasattr(b, "id"):
                    books_list.append(
                        {
                            "id": str(b.id),
                            "title": getattr(b, "title", ""),
                            "author": getattr(b, "author", ""),
                        }
                    )
                else:
                    books_list.append(b)
            author_res = {"ok": True, "books": books_list}
            result_holder["result"] = author_res
        else:
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

    # --- Path E: Volume Shift ---
    async def _path_volume_shift(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
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
                [target_volume_id] if target_volume_id else [str(b.id) for b in books]
            )
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": search_book_ids},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

    # --- Path F: In-Reader, No Title/Author ---
    async def _path_in_reader_only(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
        current_book_id = ctx.book_id
        if current_book_id and (intent == "summary" or intent == "identity"):
            async for ev in self._run_tool_and_yield(
                "get_book_summary",
                {"book_ids": [current_book_id]},
                ctx,
                observations,
                result_holder,
            ):
                yield ev
        async for ev in self._run_tool_and_yield(
            "search_chunks",
            {
                "query": question,
                "book_ids": [current_book_id] if current_book_id else None,
            },
            ctx,
            observations,
            result_holder,
        ):
            yield ev

    # --- Path G: Prior Context, No Title/Author ---
    async def _path_context_books(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        result_holder = {}
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
            summaries = result_holder.get("result", {}).get("summaries", [])
            if not summaries:
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {"query": question, "book_ids": context_book_ids},
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
        elif intent == "relationship":
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

    # --- Path H: Open / No Context ---
    async def _path_open(
        self,
        intent: str,
        signals: dict,
        question: str,
        ctx: QueryContext,
        observations: list,
    ) -> AsyncIterator[dict]:
        # intent routing for global searches
        # search_books_by_summary returns up to 20 books; passing all 20 to search_chunks
        # spreads RAG_TOP_K=25 slots across too many books (~1-2 per book), diluting the
        # specific passage that may only appear in 1 book. Focus on top 5 to concentrate
        # chunk slots. The universal fallback widens to global scope if results are thin.
        result_holder = {}
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
            summaries = result_holder.get("result", {}).get("summaries", [])
            if not summaries:
                async for ev in self._run_tool_and_yield(
                    "search_chunks",
                    {
                        "query": question,
                        "book_ids": top_ids[:_TOP_BOOKS_FOR_CHUNK_SEARCH],
                    },
                    ctx,
                    observations,
                    result_holder,
                ):
                    yield ev
        elif intent == "relationship":
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
                "search_chunks",
                {"query": question, "book_ids": None},
                ctx,
                observations,
                result_holder,
            ):
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

        # 2. Still < 4 results or weak match: widen to global scope
        top_score = max((c.get("score", 0.0) for c in chunks), default=0.0)
        if len(chunks) < 4 or top_score < CONTEXT_SWITCH_SCORE_THRESHOLD:
            async for ev in self._run_tool_and_yield(
                "search_chunks",
                {"query": question, "book_ids": None},
                ctx,
                observations,
                result_holder,
            ):
                yield ev

    async def _run_sub_question(
        self,
        sub_q_item,
        question: str,
        sub_questions: list,
        signals_orig: dict,
        ctx: QueryContext,
        runner_services: "RunnerServices",
    ) -> AsyncIterator[tuple]:
        """Runs Stage 3 (intent classification) + Stage 4 (execute_path) for
        one sub-question against its own, isolated observations list.

        Isolation matters once sub-questions run concurrently (see
        _execute_workflow_stream): sharing one observations list across
        concurrent runs would let their duplicate-tool-call dedup checks
        (e.g. "did we already run find_books_by_title for these book ids")
        race on interleaving timing, making the deterministic router
        non-deterministic. The cost is that cross-sub-question dedup this
        currently enables is lost for composite questions specifically —
        an efficiency tradeoff (possible redundant tool calls), not a
        correctness one.

        Yields ("event", dict) tuples to stream, and exactly one final
        ("done", (sub_q_text, sub_observations, llm_calls_delta)).
        """
        sub_observations: list = []
        llm_calls_delta = 0

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
                if (
                    len(sub_questions) == 1
                    and signals_orig.get("top_intent") == "current_page"
                ):
                    sub_signals["top_intent"] = "current_page"
                if "intent" in sub_signals:
                    llm_calls_delta += 1

        sub_intent = await self.classify_intent(sub_signals, sub_q, ctx)
        if "intent" not in sub_signals:
            if (
                sub_intent != "passage"
                or sub_signals.get("has_title")
                or sub_signals.get("has_context_books")
                or sub_signals.get("is_global")
            ):
                # Intent classification LLM was run for non-skipped flows
                llm_calls_delta += 1

        async for ev in self.execute_path(
            sub_intent, sub_signals, sub_q, ctx, sub_observations, runner_services
        ):
            yield ("event", ev)

        yield ("done", (sub_q, sub_observations, llm_calls_delta))

    async def _execute_workflow_stream(
        self, ctx: QueryContext, question: str, observations: list
    ) -> AsyncIterator[dict]:
        # 1. Stage 1: Detect top intent
        signals_orig = await self.extract_signals(question, ctx)
        top_intent = signals_orig.get("top_intent")
        yield {"type": "planning", "intent": top_intent}

        # 2. Stage 2: Coreference Resolution
        needs_rewrite = signals_orig.get("needs_rewrite", False)
        if not ctx.history:
            needs_rewrite = False

        is_composite = signals_orig.get("is_composite", False)
        sub_questions = signals_orig.get("sub_questions")

        llm_calls = 0
        if "intent" in signals_orig:
            llm_calls += 1

        if needs_rewrite:
            rewritten_question = signals_orig.get("rewritten_question")
            if (
                rewritten_question
                and rewritten_question.strip().lower() != question.strip().lower()
            ):
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
            elif not rewritten_question:
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
                # Double-check if the fallback rewrite is actually different
                final_rewritten = result_holder.get("result", {}).get(
                    "rewritten_question"
                )
                if (
                    final_rewritten
                    and final_rewritten.strip().lower() == question.strip().lower()
                ):
                    # If it ended up the same, clear enriched_question to avoid downstream confusion
                    ctx.enriched_question = None
                llm_calls += 1

        # 3. Query Decomposition (splitting multi-questions)
        if is_composite and isinstance(sub_questions, list) and len(sub_questions) > 1:
            yield {"type": "decompose", "count": len(sub_questions)}
        else:
            # Not composite or no sub_questions returned, use single question path
            question_to_process = ctx.enriched_question or ctx.question
            sub_questions = [question_to_process]

        # 4. Stage 3 & 4: Intent Classifier and Execution Router per sub-question
        #
        # runner_services is shared across every sub-question in this turn so
        # each execute_path() call reuses the same in-memory session/artifact/
        # memory backends instead of constructing fresh ones — see
        # graph_router.py's RunnerServices docstring for why this is safe
        # even when sub-questions below run concurrently.
        from app.services.rag.agent.graph_router import RunnerServices

        runner_services = RunnerServices()
        sub_question_texts: list[str] = []

        if len(sub_questions) == 1:
            # Common case — nothing to parallelize, run directly with no
            # generator-merging overhead.
            async for kind, payload in self._run_sub_question(
                sub_questions[0],
                question,
                sub_questions,
                signals_orig,
                ctx,
                runner_services,
            ):
                if kind == "event":
                    yield payload
                else:
                    sub_q, sub_observations, llm_calls_delta = payload
                    sub_question_texts.append(sub_q)
                    observations.extend(sub_observations)
                    llm_calls += llm_calls_delta
        else:
            # Composite: sub-questions are independent of each other, so run
            # them concurrently. Each gets its own observations list (see
            # _run_sub_question's docstring for why they can't share one),
            # merged back into `observations` in original sub-question order
            # — not completion order — once every sub-question is done, so
            # the final result is identical regardless of which one finishes
            # first.
            generators = [
                self._run_sub_question(
                    sub_q_item,
                    question,
                    sub_questions,
                    signals_orig,
                    ctx,
                    runner_services,
                )
                for sub_q_item in sub_questions
            ]
            done_by_index: dict = {}
            async for idx, (kind, payload) in _merge_sub_question_streams(generators):
                if kind == "event":
                    yield payload
                else:
                    done_by_index[idx] = payload

            for idx in range(len(sub_questions)):
                sub_q, sub_observations, llm_calls_delta = done_by_index[idx]
                sub_question_texts.append(sub_q)
                observations.extend(sub_observations)
                llm_calls += llm_calls_delta

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


def _looks_like_dictionary_question(q_norm: str) -> bool:
    dictionary_markers = [
        "دېگەن نېمە",
        "دېگەن نىمە",
        "مەنىسى",
        "ما معنى",
        "definition",
        "meaning",
        "translate",
        "translation",
        "ئۇيغۇرچىسى",
        "ئۇيغۇرچە",
        "قانداق يېزىلىدۇ",
        "توغرا يېزىلىشى",
        "ئىملا",
        "spelling",
        "spell",
        "كىشى ئىسىملىرى",
        "ئىسىملىرى",
        "ئىسىملەر",
        "ئىسىم",
        "ماقال",
        "تەمسىل",
        "proverb",
        "saying",
        "مەنىداش",
        "ئوخشاش مەنىلىك",
        "يېقىن مەنىلىك",
        "synonym",
    ]
    return any(normalize_uyghur(marker) in q_norm for marker in dictionary_markers)


def _guess_dictionary_subtype(q_norm: str) -> str:
    if any(
        normalize_uyghur(marker) in q_norm
        for marker in ["translate", "translation", "ئۇيغۇرچىسى"]
    ):
        return "english_uyghur"
    if any(
        normalize_uyghur(marker) in q_norm
        for marker in [
            "قانداق يېزىلىدۇ",
            "توغرا يېزىلىشى",
            "ئىملا",
            "spelling",
            "spell",
        ]
    ):
        return "spelling"
    if any(
        normalize_uyghur(marker) in q_norm
        for marker in ["كىشى ئىسىملىرى", "ئىسىملىرى", "ئىسىملەر", "ئىسىم"]
    ):
        return "names"
    if any(
        normalize_uyghur(marker) in q_norm
        for marker in ["مەنىداش", "ئوخشاش مەنىلىك", "يېقىن مەنىلىك", "synonym"]
    ):
        return "synonyms"
    if any(
        normalize_uyghur(marker) in q_norm
        for marker in ["ماقال", "تەمسىل", "proverb", "saying"]
    ):
        return "proverbs"
    if re.search(r"[A-Za-z]", q_norm):
        return "english_uyghur"
    return "general"


def _extract_dictionary_term(question: str) -> str:
    """Best-effort term extraction for deterministic dictionary fallback."""
    text = question.strip()
    quoted = re.search(r"[\"'«‹](.+?)[\"'»›]", text)
    if quoted:
        return quoted.group(1).strip()

    # Check for name starting letter group (e.g. "ب ھەرىپىدىن باشلانغان")
    letter_match = re.search(r"([\u0621-\u06ff]{1,2})\s+ھەر[پى]", text)
    if letter_match and any(
        normalize_uyghur(m) in normalize_uyghur(text)
        for m in ["كىشى ئىسىملىرى", "ئىسىملىرى", "ئىسىملەر", "ئىسىم", "مەنىداش"]
    ):
        return letter_match.group(1).strip()

    cleanup_patterns = [
        r"دېگەن\s+نېمە.*$",
        r"دېگەن\s+نىمە.*$",
        r"مەنىسى\s+نېمە.*$",
        r"مەنىسى\s+نىمە.*$",
        r"نىڭ\s+ئۇيغۇرچىسى\s+نېمە.*$",
        r"نىڭ\s+ئۇيغۇرچە\s+مەنىسى\s+نېمە.*$",
        r"ئۇيغۇرچىسى\s+نېمە.*$",
        r"توغرىمۇ.*$",
        r"قانداق\s+يېزىلىدۇ.*$",
        r"\bmeaning\b.*$",
        r"\bdefinition\b.*$",
        r"\btranslate\b",
        r"\btranslation\b",
        r"\bspell(?:ing)?\b.*$",
        r"ماقال\s*-?\s*تەمسىل(?:لەر)?",
        r"ماقاللار",
        r"تەمسىللەر",
        r"\bproverbs?\b",
        r"\bsayings?\b",
        r"نىڭ\s+مەنىداش\s+سۆزى\s+نېمە.*$",
        r"مەنىداش\s+سۆز(?:لىرى|لەر|ى)?",
        r"ئوخشاش\s+مەنىلىك\s+سۆز(?:لەر)?",
        r"يېقىن\s+مەنىلىك\s+سۆز(?:لەر)?",
        r"\bsynonyms?\b",
        r"\bfor\b",
        r"\bof\b",
        r"بارمۇ.*$",
        r"[؟?!.]+$",
    ]
    term = text
    for pattern in cleanup_patterns:
        term = re.sub(pattern, "", term, flags=re.IGNORECASE).strip()

    # For English prompts like "what is the Uyghur for democracy", keep the final
    # Latin phrase instead of the whole question.
    latin_words = re.findall(r"[A-Za-z][A-Za-z -]*[A-Za-z]", term)
    if latin_words:
        return latin_words[-1].strip()

    return term.strip(" :：،,؛;")


async def find_books_by_title_in_db(question: str, ctx: QueryContext) -> list[dict]:
    """Helper to synchronously trigger title checks by invoking _run_find_books_by_title."""
    from app.services.rag.agent.tools import _run_find_books_by_title

    try:
        return await _run_find_books_by_title({"question": question}, ctx)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Failed to find books by title in database",
            error=str(exc),
        )
    return []
