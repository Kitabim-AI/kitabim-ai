# ADK Chat Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ChatOrchestrator` (the ADK-native two-agent pipeline in `packages/backend-core/app/services/chat/`) the only chat/RAG implementation in the codebase, and delete the legacy `RAGService` → `HandlerRegistry` → `DeterministicRAGHandler`/`LLMRoutedRAGHandler` pipeline and its duplicate ADK agent builder.

**Architecture:** Today `POST /chat/` always uses legacy `RAGService`, and `POST /chat/stream` splits on a `use_adk_chat_v2` system_config flag OR the presence of `conversation_id` — first-turn stream requests hit legacy, follow-up turns hit `ChatOrchestrator`. This plan (1) extracts the handful of functions `ChatOrchestrator` currently borrows from the legacy files into new shared modules under `app/services/chat/`, (2) adds a non-streaming `ChatOrchestrator.answer()` method, (3) rewires both endpoints to use `ChatOrchestrator` unconditionally, (4) deletes the legacy files and their flag, and (5) removes/updates the tests that exercised only the legacy path.

**Tech Stack:** FastAPI, SQLAlchemy async, Google ADK (`google.adk.agents`, `google.adk.runners`), pytest + pytest-asyncio.

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)`.
- No hardcoded user-visible strings — use `t("errors.key")`.
- No raw SQL with user input.
- All new/changed API endpoints keep their existing auth dependency (`require_reader`) — never remove it.
- Every deleted file's remaining callers must be repointed in the same task that deletes it — no task may leave a dangling import behind for a later task to discover via a broken test run.
- `CatalogHandler` (`packages/backend-core/app/services/rag/handlers/catalog.py`) is **not** legacy — it's a plain helper class (not a `QueryHandler`) consumed by `app/services/rag/agent/tools.py`, which both the old and new pipelines share. It stays untouched.

---

## Task 1: Extract shared context-grading helpers out of `llm_routed_handler.py`

`ChatOrchestrator` currently imports `_build_human_message`, `_grade_context`, `_extract_used_book_ids` from `app/services/rag/agent/llm_routed_handler.py` (line 33-37 of `orchestrator.py`), a file this plan deletes in Task 7. Move the three functions verbatim into a new module before anything else changes, so orchestrator.py never has a broken import.

**Files:**
- Create: `packages/backend-core/app/services/chat/context_grading.py`
- Modify: `packages/backend-core/app/services/rag/agent/llm_routed_handler.py:94-284` (delete the three moved functions; the class below them, `LLMRoutedRAGHandler`, still uses them — it must import from the new module instead)

**Interfaces:**
- Produces: `_build_human_message(ctx: QueryContext, question: str) -> str`, `_grade_context(observations: list[dict], max_chunks: int | None = None) -> tuple[str, int, int]`, `_extract_used_book_ids(observations: list[dict]) -> list[str]` — all importable from `app.services.chat.context_grading`.

- [ ] **Step 1: Create the new module with the three functions moved verbatim**

Copy lines 94-284 of `packages/backend-core/app/services/rag/agent/llm_routed_handler.py` exactly as they are today (do not alter behavior) into a new file:

```python
"""Context grading and formatting helpers shared by the chat orchestrator
and (until it's deleted) the legacy LLM-routed handler."""

from __future__ import annotations

import logging

from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.services.chat.context_grading")


def _build_human_message(ctx: QueryContext, question: str) -> str:
    lines = []
    if not ctx.is_global and ctx.book:
        book = ctx.book
        book_info = f'"{book.title}"' if book.title else "unknown title"
        if book.author:
            book_info += f" by {book.author}"
        if book.volume is not None:
            book_info += f", volume {book.volume}"
        lines.append(f"Current book: {book_info} (book_id: {ctx.book_id})")
        if ctx.current_page is not None:
            lines.append(f"Current page: {ctx.current_page}")
    elif ctx.is_global:
        if ctx.context_book_ids:
            lines.append(
                f"Previous response book IDs: {', '.join(ctx.context_book_ids[:10])}"
            )
        if ctx.character_categories:
            lines.append(f"Category filter: {', '.join(ctx.character_categories)}")
    if ctx.history:
        lines.append("Chat history: Available (contains prior conversation context)")
    if not lines:
        return question
    return "[Context]\n" + "\n".join(lines) + "\n\n[Question]\n" + question


def _grade_context(
    observations: list[dict], max_chunks: int | None = None
) -> tuple[str, int, int]:
    from app.services.rag.agent.config import (
        AGENT_MAX_CONTEXT_CHUNKS,
        GRADE_RELATIVE_THRESHOLD,
        MIN_CHUNKS_AFTER_GRADING,
    )

    limit = max_chunks if max_chunks is not None else AGENT_MAX_CONTEXT_CHUNKS
    from app.services.rag.answer_builder import format_document, Document

    # Build metadata context from any tool returning a "context" key
    metadata_parts = []
    for obs in observations:
        res = obs.get("result", {})
        if not res.get("ok", False):
            continue
        data = res.get("data") or res
        if isinstance(data, dict) and data.get("context"):
            metadata_parts.append(data["context"])

    all_graded_documents: list[Document] = []
    total_raw_chunks = 0
    seen: set[tuple] = set()

    for obs in observations:
        if obs.get("tool") != "search_chunks":
            continue
        res = obs.get("result", {})
        if not res.get("ok", False):
            continue
        data = res.get("data") or res
        if not isinstance(data, dict):
            continue

        chunks = data.get("chunks", [])
        if not chunks:
            continue

        total_raw_chunks += len(chunks)

        # Convert to Document list for this search tool call
        search_docs = [
            Document(
                page_content=c.get("text", ""),
                metadata={
                    "title": c.get("title") or "Unknown",
                    "author": c.get("author") or None,
                    "volume": c.get("volume"),
                    "page": c.get("page")
                    if c.get("page") is not None
                    else c.get("page_number"),
                    "page_number": c.get("page_number")
                    if c.get("page_number") is not None
                    else c.get("page"),
                    "book_id": c.get("book_id"),
                    "score": c.get("score", 0.0),
                    "rrf_score": c.get("rrf_score", 0.0),
                    "rank": c.get("rank"),
                    "surah_name_en": c.get("surah_name_en"),
                    "surah": c.get("surah"),
                    "ayah": c.get("ayah"),
                },
            )
            for c in chunks
        ]

        # Grade this specific search call's results
        search_docs.sort(
            key=lambda d: (
                d.metadata.get("rrf_score", 0.0),
                d.metadata.get("score", 0.0),
            ),
            reverse=True,
        )
        top_score = max((d.metadata["score"] for d in search_docs), default=0.0)
        score_floor = top_score * GRADE_RELATIVE_THRESHOLD

        # Keep docs meeting relative score floor, OR keyword-only hits with positive rrf_score / keyword rank
        graded_search_docs = [
            d
            for d in search_docs
            if d.metadata["score"] >= score_floor
            or d.metadata.get("rrf_score", 0.0) > 0.0
            or d.metadata.get("rank") is not None
        ]

        # Fallback to keep minimum chunks for this specific search if drop is steep
        if len(graded_search_docs) < MIN_CHUNKS_AFTER_GRADING:
            graded_search_docs = search_docs[:MIN_CHUNKS_AFTER_GRADING]

        # Append to our global pool, deduplicating along the way
        for doc in graded_search_docs:
            page_val = (
                doc.metadata.get("page")
                if doc.metadata.get("page") is not None
                else doc.metadata.get("page_number")
            )
            key = (doc.metadata["book_id"], page_val)
            if key in seen:
                continue
            seen.add(key)
            all_graded_documents.append(doc)

    # Final global sort and limit cap
    if all_graded_documents:
        # Sort the globally aggregated list so highest overall scoring context comes first
        all_graded_documents.sort(
            key=lambda d: (
                d.metadata.get("rrf_score", 0.0),
                d.metadata.get("score", 0.0),
            ),
            reverse=True,
        )
        graded = all_graded_documents[:limit]

        log_json(
            logger,
            logging.INFO,
            "Context graded (per-search)",
            before=total_raw_chunks,
            after=len(graded),
        )
        chunk_parts = [format_document(d) for d in graded]
        after_count = len(graded)
    else:
        chunk_parts = []
        after_count = 0

    all_parts = metadata_parts + chunk_parts
    graded_context = (
        "\n\n---\n\n".join(all_parts)
        if all_parts
        else "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
    )
    return graded_context, total_raw_chunks, after_count


def _extract_used_book_ids(observations: list[dict]) -> list[str]:
    # Collect book IDs from search_chunks results
    chunk_book_ids = set()
    for obs in observations:
        if obs.get("tool") == "search_chunks":
            res = obs.get("result", {})
            if res.get("ok", False):
                data = res.get("data") or res
                if isinstance(data, dict):
                    for chunk in data.get("chunks", []):
                        if chunk.get("book_id"):
                            chunk_book_ids.add(str(chunk["book_id"]))

    # Collect book IDs from get_book_summary results
    summary_book_ids = set()
    for obs in observations:
        if obs.get("tool") == "get_book_summary":
            res = obs.get("result", {})
            if res.get("ok", False):
                data = res.get("data") or res
                if isinstance(data, dict):
                    for summary in data.get("summaries", []):
                        if summary.get("book_id"):
                            summary_book_ids.add(str(summary["book_id"]))

    return list(chunk_book_ids | summary_book_ids)
```

- [ ] **Step 2: Delete the moved functions from `llm_routed_handler.py` and import them from the new module instead**

In `packages/backend-core/app/services/rag/agent/llm_routed_handler.py`, delete lines 94-284 (the three function bodies you just copied), then add an import so the rest of the file (which still calls `_build_human_message`, `_grade_context`, `_extract_used_book_ids` internally) keeps working. Right after the existing `from app.services.rag.context import QueryContext` import near the top of the file, add:

```python
from app.services.chat.context_grading import (
    _build_human_message,
    _grade_context,
    _extract_used_book_ids,
)
```

- [ ] **Step 3: Verify nothing broke**

Run: `cd packages/backend-core && python -c "import app.services.rag.agent.llm_routed_handler"`
Expected: no `ImportError`/`SyntaxError`.

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_reranker_test.py tests/app/services/rag_system_config_top_k_test.py -q`
Expected: these currently pass and should still pass (they exercise `_grade_context` indirectly/directly and don't yet know about the new module — Task 8 repoints the direct importer).

- [ ] **Step 4: Commit**

```bash
git add packages/backend-core/app/services/chat/context_grading.py packages/backend-core/app/services/rag/agent/llm_routed_handler.py
git commit -m "refactor: extract context-grading helpers into chat/context_grading.py"
```

---

## Task 2: Extract query-signal analysis out of `deterministic_handler.py`

`ChatOrchestrator` instantiates `DeterministicRAGHandler()` purely to call its `_llm_analyze_query` method (`orchestrator.py:229-232`) for pre-processing signal extraction — the method never touches `self`. Move it to a standalone function so it survives Task 7's deletion of `deterministic_handler.py`. It internally calls `repair_json_unescaped_quotes` (same file, lines 61-75), which must move with it.

**Files:**
- Create: `packages/backend-core/app/services/chat/query_signals.py`
- Modify: none in this task (the source file is deleted wholesale in Task 7; leaving the old copies in place until then is fine since nothing calls them except the class itself, which still exists until Task 7)

**Interfaces:**
- Produces: `analyze_query_signals(question: str, ctx: QueryContext) -> dict` and `repair_json_unescaped_quotes(json_str: str) -> str`, both importable from `app.services.chat.query_signals`.

- [ ] **Step 1: Create the new module**

`packages/backend-core/app/services/rag/agent/deterministic_handler.py:134-356` is the `_llm_analyze_query` method body (it never references `self`), and lines 61-75 are `repair_json_unescaped_quotes`, which it calls. Both need `_dispatch_tool_with_retry` from `app.services.rag.agent.tools`. Write:

```python
"""Query signal & intent extraction — single-shot structured LLM call used
by the chat orchestrator's pre-processing stage."""

from __future__ import annotations

import json
import logging
import re

from google.genai import types

from app.services.rag.agent.tools import _dispatch_tool_with_retry
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.services.chat.query_signals")


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


async def analyze_query_signals(question: str, ctx: QueryContext) -> dict:
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

    prompt = f"""Analyze this query in the context of an Uyghur book reading assistant.

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
  "is_current_page_query": boolean, // True ONLY if the user explicitly asks about the current page/text they are looking at (e.g. "what is on this page", "read this page", "بۇ بەتتە نېمە بار"). MUST be false if asking about the book as a whole (e.g. "مەن ھازىر ئوقۇۋاتقان كىتابنىڭ ئاساسىي مەزمۇنى نېمە؟", "this book", "currently reading book").
  "is_volume_shift": boolean,       // True if the user wants to go to another volume (e.g. "next volume", "previous volume", "ئالدىنقى توم", "2-توم")
  "target_volume": integer | null,  // The volume number to shift to if specified (e.g. 2, 3), else null
  "needs_rewrite": boolean,         // True ONLY if the query has unresolved pronouns/coreferences or implicit references (ellipsis) referring to prior chat history. MUST be false if the query is fully self-contained, or if there is no chat history.
  "rewritten_question": string | null, // If needs_rewrite is true, rewrite the question to resolve all pronouns/references using chat history to make it self-contained in standard Uyghur (strictly maintaining Uyghur SOV word order and suffix grammar). If needs_rewrite is false, return null.
  "catalog_subtype": "author_of" | "books_by" | "general" | null, // Use "author_of" if asking who wrote a book, "books_by" if asking what books an author wrote, "general" for other catalog/library-wide queries (like "what books do you have"), or null if this is NOT a catalog query.
  "dictionary_subtype": "uyghur_definition" | "history_term" | "english_uyghur" | "spelling" | "names" | "proverbs" | "synonyms" | "general" | null, // Use only when intent is "dictionary".
  "dictionary_term": string | null, // The exact word/term/name/English phrase to look up when intent is "dictionary".
  "quran_surah": integer | null,    // The surah number (1-114) if specified (e.g. 1 for Fatihah, 2 for Baqarah), or null.
  "quran_ayah": integer | null,     // The ayah/verse number if specified, or null.
  "quran_query": string | null,     // The text query or keyword to search inside Quranic verses, or null.
  "intent": "catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran",
  "is_composite": boolean,          // True if the query contains multiple distinct questions or requests that should be handled separately (e.g. "Who wrote X and what is it about?").
  "sub_questions": Array<{{         // If is_composite is true, return each sub-question with its own signals. If is_composite is false, return null.
    "question": string,             // Self-contained sub-question text (pronouns resolved using history, in standard Uyghur SOV grammar)
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
            config.response_mime_type = "application/json"

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
```

- [ ] **Step 2: Verify the new module imports cleanly**

Run: `cd packages/backend-core && python -c "import app.services.chat.query_signals"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add packages/backend-core/app/services/chat/query_signals.py
git commit -m "refactor: extract analyze_query_signals into chat/query_signals.py"
```

---

## Task 3: Repoint `ChatOrchestrator` to the new modules and add a non-streaming `answer()` method

**Files:**
- Modify: `packages/backend-core/app/services/chat/orchestrator.py:32-38` (imports)
- Modify: `packages/backend-core/app/services/chat/orchestrator.py:228-232` (call site)
- Modify: `packages/backend-core/app/services/chat/orchestrator.py` (add `answer()` method after `stream_response`)
- Test: `packages/backend-core/tests/app/services/test_adk_orchestrator.py`

**Interfaces:**
- Consumes: `_build_human_message`, `_grade_context`, `_extract_used_book_ids` from `app.services.chat.context_grading` (Task 1); `analyze_query_signals` from `app.services.chat.query_signals` (Task 2).
- Produces: `ChatOrchestrator.answer(request_dto: ChatRequestDTO, db_session: AsyncSession, model_name: str = "gemini-2.5-flash") -> dict` returning `{"answer": str, "conversation_id": str | None, "used_book_ids": list[str], "eval_id": int | None}`.

- [ ] **Step 1: Swap the imports**

In `packages/backend-core/app/services/chat/orchestrator.py`, replace:

```python
from app.services.rag.agent.deterministic_handler import DeterministicRAGHandler
from app.services.rag.agent.llm_routed_handler import (
    _build_human_message,
    _extract_used_book_ids,
    _grade_context,
)
```

with:

```python
from app.services.chat.context_grading import (
    _build_human_message,
    _extract_used_book_ids,
    _grade_context,
)
from app.services.chat.query_signals import analyze_query_signals
```

- [ ] **Step 2: Update the call site**

Around line 228-232, replace:

```python
            # 2b. Fast signal pre-processing via DeterministicRAGHandler
            deterministic_handler = DeterministicRAGHandler()
            signals = await deterministic_handler._llm_analyze_query(
```

with:

```python
            # 2b. Fast signal pre-processing
            signals = await analyze_query_signals(
```

(Keep whatever argument list already followed `_llm_analyze_query(` on the next line(s) — only the callable name and the now-removed `deterministic_handler` instantiation change.)

- [ ] **Step 3: Add the non-streaming `answer()` method**

Add this method to the `ChatOrchestrator` class, directly after `stream_response` ends (after its final `yield` block, matching the same indentation as `stream_response`):

```python
    async def answer(
        self,
        request_dto: ChatRequestDTO,
        db_session: AsyncSession,
        model_name: str = "gemini-2.5-flash",
    ) -> dict:
        """Non-streaming convenience wrapper: drains stream_response and
        returns the concatenated answer text plus the done-event metadata."""
        answer_text = ""
        done_meta: dict = {}
        async for event in self.stream_response(request_dto, db_session, model_name):
            if isinstance(event, dict):
                if event.get("type") == "chunk":
                    answer_text += event.get("text", "")
                elif event.get("type") == "done":
                    done_meta = event
        return {
            "answer": answer_text,
            "conversation_id": done_meta.get("conversation_id"),
            "used_book_ids": done_meta.get("used_book_ids", []),
            "eval_id": done_meta.get("eval_id"),
        }
```

- [ ] **Step 4: Run the orchestrator test suite**

Run: `cd packages/backend-core && python -m pytest tests/app/services/test_adk_orchestrator.py -q`
Expected: PASS (existing tests must still pass — they exercise `stream_response`, which is otherwise unchanged).

- [ ] **Step 5: Write a failing test for `answer()`**

Read `packages/backend-core/tests/app/services/test_adk_orchestrator.py` first to match its existing fixture/mocking style for `ChatOrchestrator.stream_response` (it already mocks the ADK `Runner`/session plumbing), then add:

```python
@pytest.mark.asyncio
async def test_answer_concatenates_chunks_and_returns_done_metadata(monkeypatch):
    orchestrator = ChatOrchestrator()

    async def fake_stream_response(self, request_dto, db_session, model_name="gemini-2.5-flash"):
        yield {"type": "answer_start"}
        yield {"type": "chunk", "text": "سالام"}
        yield {"type": "chunk", "text": "، دۇنيا"}
        yield {
            "type": "done",
            "eval_id": 7,
            "conversation_id": "conv-xyz",
            "used_book_ids": ["book-1"],
        }

    monkeypatch.setattr(ChatOrchestrator, "stream_response", fake_stream_response)

    result = await orchestrator.answer(
        ChatRequestDTO(question="q", user_id="u1", book_id="book-1"),
        db_session=AsyncMock(),
    )

    assert result == {
        "answer": "سالام، دۇنيا",
        "conversation_id": "conv-xyz",
        "used_book_ids": ["book-1"],
        "eval_id": 7,
    }
```

Add `from unittest.mock import AsyncMock` to the test file's imports if not already present.

- [ ] **Step 6: Run it to verify it fails, then passes**

Run: `cd packages/backend-core && python -m pytest tests/app/services/test_adk_orchestrator.py -q`
Expected before Step 3's code exists: FAIL with `AttributeError: 'ChatOrchestrator' object has no attribute 'answer'`. Since Step 3 already added the method, this should PASS now — if it doesn't, fix `answer()` until it does.

- [ ] **Step 7: Commit**

```bash
git add packages/backend-core/app/services/chat/orchestrator.py packages/backend-core/tests/app/services/test_adk_orchestrator.py
git commit -m "feat: repoint orchestrator to extracted helpers, add non-streaming answer()"
```

---

## Task 4: Rewire `/chat/` and `/chat/stream` to always use `ChatOrchestrator`

Removes the `use_adk_chat_v2` flag branch and the `RAGService` fallback entirely. `POST /chat/stream` keeps its current `use_v2` code path (now unconditional); `POST /chat/` switches from `rag_service.answer_question` to `ChatOrchestrator.answer()`.

**Files:**
- Modify: `services/backend/api/endpoints/chat_router.py`
- Test: `services/backend/tests/api/endpoints/chat_router_test.py`

**Interfaces:**
- Consumes: `ChatOrchestrator.answer()` (Task 3), `ChatOrchestrator.stream_response()` (unchanged), `ChatRequestDTO` (unchanged).

- [ ] **Step 1: Update imports**

In `services/backend/api/endpoints/chat_router.py`, delete these two now-unused imports:

```python
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.rag_service import get_rag_service, RAGService
```

- [ ] **Step 2: Rewrite `chat_with_book_api` (`POST /chat/`)**

Replace the whole function (lines 38-101) with:

```python
@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(
    req: ChatRequest,
    request: Request,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Chat with book using the ADK chat orchestrator with role-based daily limits"""
    log_json(
        logger,
        logging.INFO,
        "Chat endpoint entered",
        user_id=current_user.id,
        book_id=req.book_id,
    )
    # 1. Check if user is within their daily limit
    usage_status = await chat_limit_service.get_user_usage_status(current_user, session)
    if usage_status["has_reached_limit"]:
        log_json(
            logger,
            logging.WARNING,
            "Chat limit reached for user",
            user_id=current_user.id,
            role=current_user.role,
            usage=usage_status["usage"],
            limit=usage_status["limit"],
        )
        raise HTTPException(status_code=429, detail=t("errors.daily_limit_reached"))

    try:
        # 2. Process chat request via the ADK orchestrator
        is_global = req.is_global or req.book_id == "global"
        dto = ChatRequestDTO(
            question=req.question,
            user_id=current_user.id,
            book_id=req.book_id,
            is_global=is_global,
            current_page=req.current_page,
            character_id=req.character_id,
            conversation_id=req.conversation_id,
            context_book_ids=req.context_book_ids,
            exact_phrase=req.exact_phrase,
        )
        adk_session_service = getattr(request.app.state, "adk_session_service", None)
        orchestrator = ChatOrchestrator(session_service=adk_session_service)
        result = await orchestrator.answer(dto, session)

        # 2.5. Fix malformed citation references
        answer = fix_malformed_citations(result["answer"])

        # 3. Increment usage on successful answer
        await chat_limit_service.increment_usage(current_user, session)
        usage_status = await chat_limit_service.get_user_usage_status(
            current_user, session
        )

        return {"answer": answer, "usage": usage_status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        error_str = str(exc)
        log_json(
            logger,
            logging.ERROR,
            "Chat request failed",
            book_id=req.book_id,
            error=error_str,
        )

        # Check for 429 RESOURCE_EXHAUSTED from Google/Gemini
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise HTTPException(status_code=429, detail=t("errors.system_busy"))

        # Record error using SQLAlchemy
        await record_book_error(session, req.book_id, "chat", error_str)
        raise HTTPException(status_code=500, detail=t("errors.system_busy_generic"))
```

- [ ] **Step 3: Simplify `chat_with_book_stream` (`POST /chat/stream`) to drop the legacy branch**

Replace the function signature (delete the `rag_service` parameter) — change:

```python
@router.post("/stream")
async def chat_with_book_stream(
    req: ChatRequest,
    request: Request,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
    rag_service: RAGService = Depends(get_rag_service),
):
```

to:

```python
@router.post("/stream")
async def chat_with_book_stream(
    req: ChatRequest,
    request: Request,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
```

Then, inside `event_generator()`, replace the whole `try:` body — from `config_repo = SystemConfigsRepository(session)` (currently line 141) down through the legacy `async for event in rag_service.answer_question_stream(...)` block and its trailing citation-fix/usage-increment/`done` yield (through line 225) — with the v2 body only, unconditional and un-indented one level (no more `if use_v2:` guard, no `return` needed since it's now the only path):

```python
        try:
            adk_session_service = getattr(
                request.app.state, "adk_session_service", None
            )
            orchestrator = ChatOrchestrator(session_service=adk_session_service)

            is_global = req.is_global or req.book_id == "global"
            dto = ChatRequestDTO(
                question=req.question,
                user_id=current_user.id,
                book_id=req.book_id,
                is_global=is_global,
                current_page=req.current_page,
                character_id=req.character_id,
                conversation_id=req.conversation_id,
                context_book_ids=req.context_book_ids,
                exact_phrase=req.exact_phrase,
            )

            async for event in orchestrator.stream_response(dto, session):
                if isinstance(event, dict):
                    if event.get("type") == "chunk":
                        yield f"data: {json.dumps({'chunk': event['text']})}\n\n"
                    elif event.get("type") == "done":
                        await chat_limit_service.increment_usage(
                            current_user, session
                        )
                        updated_usage = (
                            await chat_limit_service.get_user_usage_status(
                                current_user, session
                            )
                        )
                        done_payload = {
                            "done": True,
                            "usage": updated_usage,
                            "conversationId": event.get("conversation_id"),
                            "contextBookIds": event.get("used_book_ids", []),
                            "evalId": event.get("eval_id"),
                        }
                        yield f"data: {json.dumps(done_payload)}\n\n"
                    else:
                        yield f"data: {json.dumps(event)}\n\n"

        except ValueError as exc:
```

(The `except ValueError` / `except Exception` blocks below stay exactly as they are today — only the `try:` body above them changes. Note the removed legacy body also removed the citation-fixer pass over streamed text — that's fine, `ChatOrchestrator.stream_response` doesn't stream raw unfixed text the way the legacy path did; no equivalent correction event is needed here since Task 4 doesn't change orchestrator streaming behavior.)

- [ ] **Step 4: Confirm no leftover references to the removed names**

Run: `grep -n "rag_service\|RAGService\|SystemConfigsRepository\|use_adk_chat_v2\|use_v2" services/backend/api/endpoints/chat_router.py`
Expected: no output.

- [ ] **Step 5: Update `chat_router_test.py`'s two RAGService-mock tests**

Read `services/backend/tests/api/endpoints/chat_router_test.py` first (you'll need its exact `setup_paths()` helper and existing third test, `test_delete_conversation_endpoint_calls_repository_soft_delete`, which stays untouched). Replace the first two test functions (`test_chat_endpoint_uses_injected_rag_service` and `test_chat_stream_endpoint_uses_injected_rag_service`) with:

```python
@pytest.mark.asyncio
async def test_chat_endpoint_uses_chat_orchestrator():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_api
    from app.models.schemas import ChatRequest
    from app.models.user import User

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سوئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    mock_orchestrator = AsyncMock()
    mock_orchestrator.answer.return_value = {
        "answer": "جاۋاب",
        "conversation_id": "conv-1",
        "used_book_ids": ["book-abc"],
        "eval_id": 1,
    }

    with (
        patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service),
        patch(
            "api.endpoints.chat_router.ChatOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        response = await chat_with_book_api(
            req=req,
            request=MagicMock(),
            current_user=mock_user,
            session=mock_session,
        )

    assert response["answer"] == "جاۋاب"
    assert response["usage"] == mock_usage
    mock_orchestrator.answer.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream_endpoint_uses_chat_orchestrator():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_stream
    from app.models.schemas import ChatRequest
    from app.models.user import User
    import json

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سوئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    async def mock_stream_response(*args, **kwargs):
        yield {"type": "chunk", "text": "بىرىنچى"}
        yield {"type": "chunk", "text": "ئىككىنچى"}
        yield {
            "type": "done",
            "eval_id": 42,
            "conversation_id": "conv-1",
            "used_book_ids": ["book-abc"],
        }

    mock_orchestrator = MagicMock()
    mock_orchestrator.stream_response = mock_stream_response

    chunks = []
    with (
        patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service),
        patch(
            "api.endpoints.chat_router.ChatOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        response = await chat_with_book_stream(
            req=req,
            request=MagicMock(),
            current_user=mock_user,
            session=mock_session,
        )

        async for item in response.body_iterator:
            chunks.append(item)

    assert len(chunks) > 0
    assert f"data: {json.dumps({'chunk': 'بىرىنچى'})}\n\n" in chunks
    assert f"data: {json.dumps({'chunk': 'ئىككىنچى'})}\n\n" in chunks
```

- [ ] **Step 6: Run the test file**

Run: `cd services/backend && python -m pytest tests/api/endpoints/chat_router_test.py -q`
Expected: 3 passed (the two rewritten tests plus the untouched `test_delete_conversation_endpoint_calls_repository_soft_delete`).

- [ ] **Step 7: Commit**

```bash
git add services/backend/api/endpoints/chat_router.py services/backend/tests/api/endpoints/chat_router_test.py
git commit -m "feat: route /chat/ and /chat/stream exclusively through ChatOrchestrator"
```

---

## Task 5: Delete the legacy pipeline files and fix their dependents

At this point nothing production-facing imports `rag_service.py`, `rag/registry.py`, `rag/base_handler.py`, `rag/agent/deterministic_handler.py`, `rag/agent/graph_router.py`, `rag/agent/llm_routed_handler.py`, or `rag/agent/adk_agent.py` — but `rag/__init__.py`, the `adk web` dev entrypoint, and a diagnostic script still do. Fix those first, then delete.

**Files:**
- Modify: `packages/backend-core/app/services/rag/__init__.py`
- Modify: `packages/backend-core/agent.py`
- Modify: `scripts/test_graph_rag.py`
- Delete: `packages/backend-core/app/services/rag_service.py`, `packages/backend-core/app/services/rag/registry.py`, `packages/backend-core/app/services/rag/base_handler.py`, `packages/backend-core/app/services/rag/agent/deterministic_handler.py`, `packages/backend-core/app/services/rag/agent/graph_router.py`, `packages/backend-core/app/services/rag/agent/llm_routed_handler.py`, `packages/backend-core/app/services/rag/agent/adk_agent.py`

- [ ] **Step 1: Fix `rag/__init__.py`**

`packages/backend-core/app/services/rag/__init__.py` currently re-exports `QueryHandler` (from `base_handler.py`, being deleted) and `HandlerRegistry`/`get_registry` (from `registry.py`, being deleted). Every other module in the `rag` package runs this file on import, so it must be fixed in the same commit as the deletions. Replace its entire contents with:

```python
"""RAG package — public exports."""

from app.services.rag.context import QueryContext

__all__ = [
    "QueryContext",
]
```

- [ ] **Step 2: Repoint the `adk web` dev entrypoint**

`packages/backend-core/agent.py` builds its `root_agent` from `build_rag_agent()` in `adk_agent.py` (being deleted), which is functionally superseded by `build_retrieval_agent()` in the kept `chat/retrieval_agent.py` (same tools, same system prompt, plus optional intent-signal hints this entrypoint doesn't need). Replace the whole file with:

```python
"""ADK web entry point — exposes `root_agent` for `adk web` discovery.

Run from the packages/backend-core directory:
    adk web

Or from the repo root:
    adk web packages/backend-core
"""

from app.services.chat.retrieval_agent import build_retrieval_agent

# Default model for local ADK web dev session.
# Override by setting AGENT_MODEL env var before running `adk web`.
import os

_model = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

root_agent = build_retrieval_agent(_model)
```

- [ ] **Step 3: Repoint the diagnostic script**

`scripts/test_graph_rag.py` instantiates `RAGService` directly (being deleted). Replace its `main()` body to use `ChatOrchestrator.answer()` instead. Replace the full file contents with:

```python
#!/usr/bin/env python
"""Diagnostic script to test the Agentic GraphRAG query flow.

Run inside the backend container to verify the RAG system correctly routes
relational queries to the query_knowledge_graph tool and generates an answer.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add backend core path to python path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/backend-core"))

import logging
from app.utils.observability import configure_logging
configure_logging(logging.INFO)

from app.db import session as db_session
from app.services.chat.context import ChatRequestDTO
from app.services.chat.orchestrator import ChatOrchestrator
from app.db.models import User
from sqlalchemy import select

async def main():
    print("Initializing Database...")
    await db_session.init_db("worker")

    async with db_session.async_session_factory() as session:
        # Get a reader/admin user to bypass permission/usage checks
        user_res = await session.execute(select(User).limit(1))
        user = user_res.scalar()
        if not user:
            print("Error: No users found in database. Seed the database first.")
            await db_session.close_db()
            return

        print(f"Running test GraphRAG query as User: {user.email}")

        # This question directly targets the relationship: Sultan Said Khan -[SON_OF]-> Yunus Khan
        # which we verified exists in Neo4j!
        dto = ChatRequestDTO(
            question="سۇلتان سەئىدخام بىلەن يۇنۇسخاننىڭ قانداق مۇناسىۋىتى بار؟",
            user_id=user.id,
            book_id="dbd310c05e85",  # Book: لېيىغان بۇلاق-1
        )

        print("\n=== Sending Query to Agent ===")
        print(f"Query: {dto.question}\n")

        try:
            orchestrator = ChatOrchestrator()
            result = await orchestrator.answer(dto, session)
            print("\n=== Agent Response ===")
            print(result["answer"])
            print("======================\n")
        except Exception as exc:
            print(f"Error during RAG execution: {exc}")
            import traceback
            traceback.print_exc()

    await db_session.close_db()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Delete the seven legacy files**

```bash
git rm packages/backend-core/app/services/rag_service.py
git rm packages/backend-core/app/services/rag/registry.py
git rm packages/backend-core/app/services/rag/base_handler.py
git rm packages/backend-core/app/services/rag/agent/deterministic_handler.py
git rm packages/backend-core/app/services/rag/agent/graph_router.py
git rm packages/backend-core/app/services/rag/agent/llm_routed_handler.py
git rm packages/backend-core/app/services/rag/agent/adk_agent.py
```

- [ ] **Step 5: Confirm nothing outside tests still imports the deleted modules**

Run:
```bash
grep -rln "rag_service\|rag\.registry\|rag\.base_handler\|deterministic_handler\|llm_routed_handler\|rag\.agent\.adk_agent\|rag\.agent\.graph_router\|RAGService\|HandlerRegistry\|DeterministicRAGHandler\|LLMRoutedRAGHandler\|get_registry\b" \
  --include="*.py" packages/backend-core services/backend services/worker scripts \
  | grep -v "/tests/\|_test\.py"
```
Expected: no output. (Task 6 handles the test-directory hits.)

- [ ] **Step 6: Sanity-import the app**

Run: `cd packages/backend-core && python -c "import app.services.chat.orchestrator; import app.services.rag"`
Expected: no `ImportError`.

- [ ] **Step 7: Commit**

```bash
git add packages/backend-core/app/services/rag/__init__.py packages/backend-core/agent.py scripts/test_graph_rag.py
git commit -m "refactor: delete legacy RAGService/HandlerRegistry chat pipeline"
```

---

## Task 6: Delete or repoint the tests that only covered the legacy pipeline

**Files:**
- Delete: `packages/backend-core/tests/app/services/deterministic_router_test.py`
- Delete: `packages/backend-core/tests/app/services/graph_router_test.py`
- Delete: `packages/backend-core/tests/app/services/composite_sub_question_test.py`
- Delete: `packages/backend-core/tests/app/services/rag_adk_agent_test.py`
- Delete: `packages/backend-core/tests/app/services/rag_service_main_test.py`
- Delete: `packages/backend-core/tests/deterministic_eval/` (whole directory: `test_deterministic_router.py` + `cases/*.json`)
- Delete: `services/backend/tests/api/endpoints/chat_router_deterministic_graph_test.py`
- Modify: `packages/backend-core/tests/app/services/rag_system_config_top_k_test.py:6`

- [ ] **Step 1: Confirm each candidate really only imports doomed modules (safety check before deleting)**

```bash
for f in packages/backend-core/tests/app/services/deterministic_router_test.py \
         packages/backend-core/tests/app/services/graph_router_test.py \
         packages/backend-core/tests/app/services/composite_sub_question_test.py \
         packages/backend-core/tests/app/services/rag_adk_agent_test.py \
         packages/backend-core/tests/app/services/rag_service_main_test.py \
         packages/backend-core/tests/deterministic_eval/test_deterministic_router.py \
         services/backend/tests/api/endpoints/chat_router_deterministic_graph_test.py; do
  echo "=== $f ==="
  grep -n "^from\|^import\|from app.services.rag_service\|DeterministicRAGHandler\|HandlerRegistry\|build_rag_agent\|graph_router" "$f"
done
```
Expected: every file shows at least one import from a module deleted in Task 5. If any file imports something else too (shared/kept code), stop and re-scope that file instead of deleting it wholesale.

- [ ] **Step 2: Delete the confirmed dead test files**

```bash
git rm packages/backend-core/tests/app/services/deterministic_router_test.py
git rm packages/backend-core/tests/app/services/graph_router_test.py
git rm packages/backend-core/tests/app/services/composite_sub_question_test.py
git rm packages/backend-core/tests/app/services/rag_adk_agent_test.py
git rm packages/backend-core/tests/app/services/rag_service_main_test.py
git rm -r packages/backend-core/tests/deterministic_eval/
git rm services/backend/tests/api/endpoints/chat_router_deterministic_graph_test.py
```

- [ ] **Step 3: Repoint `rag_system_config_top_k_test.py`'s import**

In `packages/backend-core/tests/app/services/rag_system_config_top_k_test.py`, change line 6 from:

```python
from app.services.rag.agent.llm_routed_handler import _grade_context
```

to:

```python
from app.services.chat.context_grading import _grade_context
```

- [ ] **Step 4: Run the full backend-core and backend test suites**

Run: `cd packages/backend-core && python -m pytest -q`
Expected: all tests pass, zero collection errors (a collection error here means some other test file still imports a deleted module — grep for it and fix before proceeding).

Run: `cd services/backend && python -m pytest -q`
Expected: all tests pass, zero collection errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: remove tests for deleted legacy chat pipeline, repoint shared import"
```

---

## Task 7: Remove the dead `system_configs` seed rows and flag prod rows for manual deletion

Audited every `config_repo.get_value(...)` call site in the repo (`packages/backend-core`, `services/backend`, `services/worker`) against the files Task 5 deletes. Three keys become fully dead (seeded, and their only reader is deleted code):

| Key | Only reader (deleted in Task 5) | Seeded? |
|---|---|---|
| `use_deterministic_router` | `rag_service.py:132` (`_build_context`, picks `DeterministicRAGHandler` vs `LLMRoutedRAGHandler`) | Yes — `seeds.py:111-115` |
| `agent_max_steps` | `rag_service.py:118-122` → sets `QueryContext.agent_max_steps`, which **nothing ever reads** (`grep -rn "\.agent_max_steps" packages/backend-core services/backend services/worker` — no hits outside `rag_service.py`/`context.py` itself, not even inside the legacy ReAct loop) | Yes — `seeds.py:91-95` |
| `agent_enough_chunks` | `rag_service.py:124-130` → sets `QueryContext.agent_enough_chunks`, same story — never read anywhere (`grep -rn "\.agent_enough_chunks"` — no hits) | Yes — `seeds.py:96-100` |

Two more keys are read only by deleted code but were **never in `seeds.py`** (confirmed via `grep -n '"key":' packages/backend-core/app/db/seeds.py` — neither appears) — meaning any row for them in prod was added ad hoc through the generic system-configs admin CRUD, not by a fresh-env seed. The flowchart you're checking this plan against explicitly shows both being read in prod, so check the live table for these two and delete the rows if present:

| Key | Only reader (deleted in Task 5/4) | Seeded? |
|---|---|---|
| `use_adk_chat_v2` | `chat_router.py:142` (the `use_v2` branch condition, removed in Task 4) | No |
| `rag_eval_enabled` | `rag_service.py:186` (gates whether `answer_question_stream` writes a `rag_evaluations` row) | No |

Everything else the flowchart shows being read from `system_configs` (`gemini_chat_model`, `gemini_embedding_model`, `gemini_agent_loop_model`, `rag_reranker_enabled`, `gemini_reranker_model`, `rag_vector_top_k`, `rag_keyword_top_k`, `rag_graph_top_k`, `rag_judge_scoring_enabled`) is also read by `orchestrator.py` and/or the shared `rag/agent/tools.py` / `rag/retrieval.py` modules that survive this plan — keep all of those. `gemini_judge_model` is read only by `services/worker/jobs/rag_eval_job.py`, which both the old and new pipelines enqueue the same way — keep it too, out of scope here.

**Files:**
- Modify: `packages/backend-core/app/db/seeds.py:91-100` (`agent_max_steps`, `agent_enough_chunks`)
- Modify: `packages/backend-core/app/db/seeds.py:111-115` (`use_deterministic_router`) — exact line numbers shift after the first removal; re-locate by key name, not line number, when editing.

- [ ] **Step 1: Remove the three dead seed entries**

In `packages/backend-core/app/db/seeds.py`, delete these three dicts from the seed list:

```python
        {
            "key": "agent_max_steps",
            "value": "6",
            "description": "Maximum ReAct iterations/steps per round in the agent loop.",
        },
        {
            "key": "agent_enough_chunks",
            "value": "8",
            "description": "Early-exit threshold: stop agent loop once this many chunks are collected.",
        },
```

and

```python
        {
            "key": "use_deterministic_router",
            "value": "false",
            "description": "Globally enable/disable the deterministic Python RAG router instead of the LLM-driven ADK ReAct agent. Set to 'true' to activate.",
        },
```

- [ ] **Step 2: Verify no code still reads these keys**

Run: `grep -rn "use_deterministic_router\|agent_max_steps\|agent_enough_chunks" --include="*.py" packages/backend-core services/backend services/worker`
Expected: no output (the `QueryContext.agent_max_steps: int = 6` / `agent_enough_chunks: int = 8` dataclass field declarations in `rag/context.py` are harmless dead fields at this point — deleting them is optional cleanup outside this plan's scope, since nothing constructs `QueryContext` with those kwargs after Task 5 and unused dataclass fields with defaults don't error).

- [ ] **Step 3: Commit**

```bash
git add packages/backend-core/app/db/seeds.py
git commit -m "chore: remove dead system_configs seeds (use_deterministic_router, agent_max_steps, agent_enough_chunks)"
```

- [ ] **Step 4: Check and clean up the live prod table**

This step is manual, against production data — confirm with whoever owns the prod DB before running any `DELETE`. Query the current values first:

```sql
SELECT key, value, description FROM system_configs
WHERE key IN (
  'use_deterministic_router', 'agent_max_steps', 'agent_enough_chunks',
  'use_adk_chat_v2', 'rag_eval_enabled'
);
```

For every row returned, delete it (either via the admin system-configs UI, or `DELETE FROM system_configs WHERE key = '<key>';` per key) once Tasks 1-6 are deployed and confirmed working — deleting the row before the deploy would just make the code fall back to each `get_value(..., default)` call's hardcoded default (harmless), but deleting it only after deploy avoids any window where a rollback would need the row back. `use_deterministic_router`/`agent_max_steps`/`agent_enough_chunks` stop being seeded going forward per Steps 1-3; `use_adk_chat_v2`/`rag_eval_enabled` were never seeded, so nothing re-creates them once removed.

Note: none of this needs a schema migration — `system_configs` is a data table, not a schema Task 5/6 changes.

---

## Task 8: Full-repo verification pass

**Files:** none (verification only)

- [ ] **Step 1: Repo-wide grep for any remaining reference to deleted names**

```bash
grep -rn "RAGService\|HandlerRegistry\|DeterministicRAGHandler\|LLMRoutedRAGHandler\|build_rag_agent\|get_registry\b\|use_adk_chat_v2" \
  --include="*.py" packages/backend-core services/backend services/worker scripts
```
Expected: no output. If anything remains (e.g. a doc comment referencing old behavior in `packages/backend-core/app/services/rag/agent/reranker.py:170` mentioning `llm_routed_handler.py` by name), it's a comment — fine to leave or, if touching that file anyway, update the comment to say `context_grading.py`.

- [ ] **Step 2: Run both full backend test suites one more time**

Run: `cd packages/backend-core && python -m pytest -q`
Run: `cd services/backend && python -m pytest -q`
Expected: all green.

- [ ] **Step 3: Manually exercise both endpoints against the local dev stack**

```bash
./deploy/local/rebuild-and-restart.sh backend
```

Then send a first-turn (no `conversationId`) request to `POST http://localhost:30800/chat/` and a `POST http://localhost:30800/chat/stream` request (with and without an existing `conversationId`), confirming both return real answers and that `/chat/stream` events include `conversationId`/`contextBookIds`/`evalId` on the `done` event exactly as before. This closes the "split-brain" gap where first-turn stream requests used to silently hit the legacy path.

- [ ] **Step 4: No commit needed** — this task is verification-only. If Step 1 or Step 2 turns up anything, fix it and fold the fix into the most relevant earlier task's commit history via a new small commit, not an amend.

---

## Self-Review Notes

- **Spec coverage:** "keep ADK-based chat" → Tasks 1-4 (ChatOrchestrator becomes the sole runtime path for both endpoints). "remove other alternate implementations" → Tasks 5-7 (delete `RAGService`/`HandlerRegistry`/`DeterministicRAGHandler`/`LLMRoutedRAGHandler`/`adk_agent.py`, their dev/diagnostic entrypoints, their tests, and their dead config flag). Task 8 closes the loop with a repo-wide check.
- **Not touched, intentionally:** `CatalogHandler`, `rag/agent/tools.py`, `rag/context.py`, `rag/retrieval.py`, `rag/answer_builder.py`, `rag/keywords.py`, `rag/utils.py`, `rag/agent/reranker.py`, `rag/agent/prompts.py`, `rag/agent/config.py`, `rag/llm_resources.py`, `rag/judge.py`, `rag/phrase_intent.py` — all shared infrastructure consumed by `ChatOrchestrator` (directly or via its kept `chat/*` modules) or by the unrelated worker `rag_eval_job.py`.
- **Type/signature consistency check:** `ChatOrchestrator.answer()` return shape (`answer`, `conversation_id`, `used_book_ids`, `eval_id`) is used identically in Task 3's test, Task 4's `chat_with_book_api`, and Task 5's diagnostic script — verified all three read the same keys.
