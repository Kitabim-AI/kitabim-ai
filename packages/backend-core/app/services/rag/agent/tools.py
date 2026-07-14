"""Agent tool schemas and dispatch for the agentic RAG loop.

Each tool wraps existing retrieval code — no new retrieval logic lives here.
"""

from __future__ import annotations

import logging
from typing import List, Optional
import socket
import asyncio
import httpx
from sqlalchemy.exc import DBAPIError, OperationalError
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from google.adk.tools import ToolContext

from app.services.rag.context import QueryContext
from app.services.rag.retrieval import (
    embed_query,
    find_books_by_title_in_question,
    vector_search,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.tools")


# ---------------------------------------------------------------------------
# ADK Tool implementations and observation logging helper
# ---------------------------------------------------------------------------


async def _execute_and_record_tool(
    tool_context: ToolContext | None,
    tool_name: str,
    tool_args: dict,
) -> dict:
    if tool_context is None:
        raise ValueError(
            f"ADK ToolContext is required but was None for tool '{tool_name}'"
        )

    ctx: QueryContext = tool_context.state["query_context"]
    try:
        res = await _dispatch_tool_with_retry(tool_name, tool_args, ctx)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Agent tool failed after retries",
            tool=tool_name,
            error=str(exc),
        )
        if "observations" in tool_context.state:
            tool_context.state["observations"] = list(
                tool_context.state["observations"]
            ) + [
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": {"ok": False, "error": str(exc)},
                }
            ]
        raise

    # Append to observations list in session state for context building and grading
    if "observations" in tool_context.state:
        tool_context.state["observations"] = list(
            tool_context.state["observations"]
        ) + [
            {
                "tool": tool_name,
                "args": tool_args,
                "result": res,
            }
        ]
    return res


async def search_chunks(
    query: str,
    book_ids: Optional[List[str]] = None,
    tool_context: ToolContext = None,
) -> dict:
    """Vector-search book chunks for passages relevant to a query.

    Args:
        query: The search query to embed and match against book passages.
        book_ids: Optional list of book IDs to restrict the search scope.
                  Always try to restrict scope first. Only omit (pass no book_ids) after a
                  scoped search returned fewer than 4 results, or after discovery tools found
                  no usable book IDs.
    """
    args = {"query": query, "book_ids": book_ids}
    return await _execute_and_record_tool(tool_context, "search_chunks", args)


async def search_books_by_summary(
    query: str,
    book_ids: Optional[List[str]] = None,
    tool_context: ToolContext = None,
) -> dict:
    """Find books whose summaries are most relevant to a query.

    Call this before search_chunks when you don't know which books to search.
    Returns a list of book IDs sorted by relevance.

    Args:
        query: The question or topic to match against book summaries.
        book_ids: Optional candidate set to restrict to (e.g. character-filtered books).
    """
    args = {"query": query, "book_ids": book_ids}
    return await _execute_and_record_tool(tool_context, "search_books_by_summary", args)


async def find_books_by_title(
    question: str,
    tool_context: ToolContext = None,
) -> dict:
    """Return book IDs and metadata (including title, author, and volume) for titles explicitly mentioned in the question.

    Handles both «quoted» exact match and fuzzy word-prefix match.
    Returns an empty list if no recognisable title is found.

    Args:
        question: The full user question (title extraction is done server-side).
    """
    args = {"question": question}
    return await _execute_and_record_tool(tool_context, "find_books_by_title", args)


async def rewrite_query(
    question: str,
    tool_context: ToolContext = None,
) -> dict:
    """Resolve pronouns and co-references in a follow-up question using chat history.

    Call ONLY when the pronoun cannot be resolved within the same question — i.e., when
    the question begins with a pronoun or uses pronouns referring to an entity named in a
    PREVIOUS conversation turn. Do NOT call if the pronoun's antecedent is already named
    within the same question (e.g. "يۇنۇسخان كىم؟ ئۇنىڭ قانچە پەرزەنتى بار؟" — ئۇنىڭ
    refers to يۇنۇسخان which is already stated in this question).
    Returns the rewritten standalone question.

    Args:
        question: The user's original question that contains unresolved references.
    """
    args = {"question": question}
    return await _execute_and_record_tool(tool_context, "rewrite_query", args)


async def get_book_author(
    question: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up the author of a specific book title mentioned in the question.

    Call when the user asks who wrote a book or wants the author of a title.
    Returns the book title and its author name.

    Args:
        question: The user's question or a phrase containing the book title to look up.
    """
    args = {"question": question}
    return await _execute_and_record_tool(tool_context, "get_book_author", args)


async def get_books_by_author(
    question: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up all books written by an author named in the question.

    Call when the user asks what books a specific author has written.
    Returns a list of books with volume and page counts.

    Args:
        question: The user's question or a phrase containing the author name to look up.
    """
    args = {"question": question}
    return await _execute_and_record_tool(tool_context, "get_books_by_author", args)


async def search_catalog(
    query: str,
    tool_context: ToolContext = None,
) -> dict:
    """Search the library catalog for books, authors, or general library listings.

    Call for general library browsing questions: what books exist, what an author has
    published, or catalog-level metadata. Do NOT call for content questions — use
    search_chunks for those.

    Args:
        query: The user's question about the library catalog.
    """
    args = {"query": query}
    return await _execute_and_record_tool(tool_context, "search_catalog", args)


async def get_book_summary(
    book_ids: List[str],
    tool_context: ToolContext = None,
) -> dict:
    """Get the full semantic summary of specific books.

    Call this when asked about the main characters, plot, themes, or identity of a person/character.
    Returns the text of the book's summary.

    Args:
        book_ids: List of book IDs to fetch summaries for. If an ID belongs to a
                  multi-volume book, ALL of that book's sister volumes are
                  included automatically (server-side) — you do not need to
                  enumerate every volume ID yourself, and none will be dropped
                  even if you only pass one. This cap only applies to distinct,
                  unrelated books: limit to at most 5 DIFFERENT books — each
                  summary is large, and passing many unrelated ones is wasteful
                  and dilutes the answer.
    """
    args = {"book_ids": book_ids}
    return await _execute_and_record_tool(tool_context, "get_book_summary", args)


async def get_sister_volumes(
    book_id: str,
    tool_context: ToolContext = None,
) -> dict:
    """Return all volumes of the same book series as the given book.

    Call when the user asks about a different volume of the current book — next volume,
    previous volume, or a specific volume number (e.g. '2-توم', 'كەيىنكى توم').
    Returns all volumes with their IDs so you can target the right one in search_chunks.

    Args:
        book_id: The ID of any volume in the series (use the current book_id from [Context]).
    """
    args = {"book_id": book_id}
    return await _execute_and_record_tool(tool_context, "get_sister_volumes", args)


async def get_current_page(
    tool_context: ToolContext = None,
) -> dict:
    """Retrieve the full text of the page the user is currently reading.

    Call this ONLY when the user explicitly asks about the current page they are on
    (e.g. "what is written on this page?", "read this page", "بۇ بەتتە نېمە دېيىلگەن؟").
    Only available in single-book (in-reader) mode — [Context] will include a current_page
    number when it applies.
    Do NOT call search_chunks after calling this.
    """
    return await _execute_and_record_tool(tool_context, "get_current_page", {})


async def query_knowledge_graph(
    query: str,
    book_ids: Optional[List[str]] = None,
    tool_context: ToolContext = None,
) -> dict:
    """Query the book knowledge graph to retrieve connections and relationships between entities.

    Call this tool when the query asks about historical figures, events, locations, concepts,
    or relations between multiple entities, to retrieve semantic network context.

    Args:
        query: The search query or question containing entities to query.
        book_ids: Optional list of book IDs to restrict the knowledge graph query scope.
    """
    args = {"query": query}
    if book_ids is not None:
        args["book_ids"] = book_ids
    return await _execute_and_record_tool(tool_context, "query_knowledge_graph", args)


async def lookup_uyghur_word(
    term: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up a Uyghur word's dictionary definition.

    Call this for lexical questions such as "what does X mean?", "X دېگەن نېمە؟",
    or when the user asks for a word explanation rather than book passages.

    Args:
        term: The Uyghur word or phrase to define.
    """
    args = {"term": term}
    return await _execute_and_record_tool(tool_context, "lookup_uyghur_word", args)


async def lookup_history_term(
    term: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up a historical term, person, event, location, or concept.

    Call this for history vocabulary and encyclopedia-style questions, especially
    "X كىم؟" or "X نېمە؟" when X looks like a historical name or term.

    Args:
        term: The historical term, person name, event, or concept to explain.
    """
    args = {"term": term}
    return await _execute_and_record_tool(tool_context, "lookup_history_term", args)


async def translate_english_to_uyghur(
    term: str,
    tool_context: ToolContext = None,
) -> dict:
    """Translate an English word or phrase into Uyghur.

    Call this when the user asks for the Uyghur equivalent of an English word.

    Args:
        term: The English word or phrase to translate.
    """
    args = {"term": term}
    return await _execute_and_record_tool(
        tool_context, "translate_english_to_uyghur", args
    )


async def check_word_spelling(
    word: str,
    tool_context: ToolContext = None,
) -> dict:
    """Check whether a Uyghur word exists in the spelling word list.

    Call this when the user asks if a Uyghur spelling is correct or valid.

    Args:
        word: The Uyghur word to validate.
    """
    args = {"word": word}
    return await _execute_and_record_tool(tool_context, "check_word_spelling", args)


async def lookup_uyghur_name(
    term: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up a Uyghur name or list names starting with a letter.

    Call this when the user asks about Uyghur names, is looking up a name,
    or wants a list of names starting with a specific letter.

    Args:
        term: The name or the target starting letter (e.g., "ب", "ئا").
    """
    args = {"term": term}
    return await _execute_and_record_tool(tool_context, "lookup_uyghur_name", args)


async def search_language_sources(
    query: str,
    tool_context: ToolContext = None,
) -> dict:
    """Search all dictionary/language sources with exact and fuzzy matching.

    Call this when the user asks a dictionary-style question but it is unclear
    whether the answer belongs in the Uyghur dictionary, history dictionary,
    names list, spelling word list, or English-Uyghur dictionary.

    Args:
        query: The word, term, name, or short phrase to search.
    """
    args = {"query": query}
    return await _execute_and_record_tool(tool_context, "search_language_sources", args)


async def lookup_proverbs(
    term: str,
    tool_context: ToolContext = None,
) -> dict:
    """Look up a Uyghur proverb or find proverbs matching a search term/keyword.

    Call this when the user asks about proverbs, wants to look up a proverb,
    or asks for proverbs matching a specific word or theme.

    Args:
        term: The search term or keyword to look up (e.g., "بىلىم", "knowledge").
    """
    args = {"term": term}
    return await _execute_and_record_tool(tool_context, "lookup_proverbs", args)


async def search_quran(
    surah: Optional[int] = None,
    ayah: Optional[int] = None,
    q: Optional[str] = None,
    tool_context: ToolContext = None,
) -> dict:
    """Retrieve or search Quran surahs and verses (ayahs) using surah number, ayah number, or text keywords.

    Args:
        surah: Optional Surah number (1-114).
        ayah: Optional Ayah/verse number in the specified Surah.
        q: Optional search query/text to search across Quranic verses.
    """
    args = {"surah": surah, "ayah": ayah, "q": q}
    return await _execute_and_record_tool(tool_context, "search_quran", args)


# ---------------------------------------------------------------------------
# Dispatch — routes tool call name+args to the real async implementation
# ---------------------------------------------------------------------------

TRANSIENT_EXCEPTIONS = (
    OperationalError,
    DBAPIError,
    ServiceUnavailable,
    SessionExpired,
    httpx.RequestError,
    asyncio.TimeoutError,
    socket.timeout,
    ConnectionError,
)


def _log_retry(retry_state):
    log_json(
        logger,
        logging.WARNING,
        "Retrying tool execution due to transient error",
        tool=retry_state.args[0] if retry_state.args else "unknown",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()),
    )


async def _dispatch_tool_with_retry(
    tool_name: str, tool_args: dict, ctx: QueryContext
) -> dict:
    if tool_name == "search_chunks":
        chunks = await _run_search_chunks(tool_args, ctx)
        return {"ok": True, "chunks": chunks, "found_count": len(chunks)}
    if tool_name == "search_books_by_summary":
        book_ids = await _run_search_books_by_summary(tool_args, ctx)
        return {"ok": True, "book_ids": book_ids, "found_count": len(book_ids)}
    if tool_name == "find_books_by_title":
        books = await _run_find_books_by_title(tool_args, ctx)
        book_ids = [b["id"] for b in books]
        return {
            "ok": True,
            "book_ids": book_ids,
            "books": books,
            "found_count": len(book_ids),
        }
    if tool_name == "rewrite_query":
        result = await _run_rewrite_query(tool_args, ctx)
        return {"ok": True, **result, "found_count": 0}
    if tool_name == "get_book_author":
        result = await _run_get_book_author(tool_args, ctx)
        return {
            "ok": True,
            **result,
            "found_count": 1 if result.get("author") is not None else 0,
        }
    if tool_name == "get_books_by_author":
        result = await _run_get_books_by_author(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("books", []))}
    if tool_name == "search_catalog":
        result = await _run_search_catalog(tool_args, ctx)
        return {"ok": True, **result, "found_count": result.get("book_count", 0)}
    if tool_name == "get_book_summary":
        result = await _run_get_book_summary(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("summaries", []))}
    if tool_name == "get_sister_volumes":
        result = await _run_get_sister_volumes(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("book_ids", []))}
    if tool_name == "get_current_page":
        result = await _run_get_current_page(ctx)
        return {"ok": True, **result, "found_count": 0}
    if tool_name == "query_knowledge_graph":
        result = await _run_query_knowledge_graph(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("relations", []))}
    if tool_name == "lookup_uyghur_word":
        result = await _run_lookup_uyghur_word(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    if tool_name == "lookup_history_term":
        result = await _run_lookup_history_term(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    if tool_name == "translate_english_to_uyghur":
        result = await _run_translate_english_to_uyghur(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    if tool_name == "check_word_spelling":
        result = await _run_check_word_spelling(tool_args, ctx)
        return {"ok": True, **result, "found_count": result.get("found_count", 0)}
    if tool_name == "lookup_uyghur_name":
        result = await _run_lookup_uyghur_name(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    if tool_name == "search_language_sources":
        result = await _run_search_language_sources(tool_args, ctx)
        return {"ok": True, **result, "found_count": result.get("found_count", 0)}
    if tool_name == "lookup_proverbs":
        result = await _run_lookup_proverbs(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    if tool_name == "search_quran":
        result = await _run_search_quran(tool_args, ctx)
        return {"ok": True, **result, "found_count": len(result.get("entries", []))}
    raise ValueError(f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


async def _run_search_chunks(args: dict, ctx: QueryContext) -> List[dict]:
    from app.services.rag.agent.config import CONTEXT_SWITCH_SCORE_THRESHOLD

    query = args.get("query", "")
    # Preserve None (agent omitted book_ids = global search) vs [] (agent passed empty = no books found).
    book_ids_arg = args.get("book_ids")
    book_ids: Optional[List[str]] = (
        [str(bid) for bid in book_ids_arg] if book_ids_arg is not None else None
    )

    query_vector = await embed_query(query, ctx)
    if not query_vector:
        return []

    results = await vector_search(ctx, book_ids, query_vector=query_vector)

    # Transparent context-switch fallback: if the LLM passed the previous
    # answer's book IDs verbatim and the similarity scores are weak (different
    # topic), rediscover relevant books via the summary index and re-search within them.
    if (
        book_ids
        and ctx.context_book_ids
        and set(book_ids) == {str(x) for x in ctx.context_book_ids}
    ):
        top_score = max((r.get("score", 0.0) for r in results), default=0.0)
        if top_score < CONTEXT_SWITCH_SCORE_THRESHOLD:
            log_json(
                logger,
                logging.INFO,
                "Context switch detected — rediscovering books via summaries",
                top_score=round(top_score, 3),
                threshold=CONTEXT_SWITCH_SCORE_THRESHOLD,
            )
            new_book_ids = await _run_search_books_by_summary({"query": query}, ctx)
            if new_book_ids:
                broader = await vector_search(
                    ctx, new_book_ids, query_vector=query_vector
                )
                if broader:
                    results = broader
                    book_ids = new_book_ids
                    log_json(
                        logger,
                        logging.INFO,
                        "Context-switch re-search succeeded",
                        new_books=len(new_book_ids),
                    )

    log_json(
        logger,
        logging.INFO,
        "Agent tool search_chunks",
        query=query[:60],
        book_count=len(book_ids) if book_ids is not None else 0,
        results=len(results),
    )
    return results


async def _run_search_books_by_summary(args: dict, ctx: QueryContext) -> List[str]:
    from app.db.repositories.book_summaries_repository import BookSummariesRepository
    from app.core.config import settings

    query = args.get("query", "")
    char_book_ids: Optional[List[str]] = args.get("book_ids")

    query_vector = await embed_query(query, ctx)
    if not query_vector:
        return []

    repo = BookSummariesRepository(ctx.session)
    book_ids = await repo.summary_search(
        query_embedding=query_vector,
        book_ids=char_book_ids,
        categories=ctx.character_categories or None,
        threshold=settings.summary_threshold,
        limit=20,
    )

    log_json(
        logger,
        logging.INFO,
        "Agent tool search_books_by_summary",
        query=query[:60],
        books=len(book_ids),
    )
    return book_ids


async def _run_get_book_summary(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.book_summaries_repository import BookSummariesRepository
    from app.db.repositories.books_repository import BooksRepository

    book_ids = args.get("book_ids") or []
    if not book_ids:
        return {"context": "No book IDs provided.", "summaries": []}

    # The LLM may under-comply with the "pass all sister volumes" guidance
    # (observed in production: a title resolving to 6 volumes, only 5 passed
    # here). Expand server-side rather than trusting the model's book_ids.
    books_repo = BooksRepository(ctx.session)
    expanded_ids = list(dict.fromkeys(str(bid) for bid in book_ids))
    for book_id in list(expanded_ids):
        sister_volumes = await books_repo.find_sister_volumes(book_id)
        for sister in sister_volumes:
            sister_id = str(sister.id)
            if sister_id not in expanded_ids:
                expanded_ids.append(sister_id)

    repo = BookSummariesRepository(ctx.session)
    summaries = await repo.get_summaries_for_books(expanded_ids)

    if not summaries:
        log_json(logger, logging.INFO, "Agent tool get_book_summary", count=0)
        return {
            "context": "No summaries found for the provided book IDs.",
            "summaries": [],
        }

    lines = []
    for s in summaries:
        header_parts = [f"BookID: {s['book_id']}", f"Book: {s['title']}"]
        if s.get("author"):
            header_parts.append(f"Author: {s['author']}")
        if s.get("volume") is not None:
            header_parts.append(f"Volume: {s['volume']}")
        header_parts.append("SUMMARY")
        lines.append(f"[{', '.join(header_parts)}]\n{s['summary']}")

    context_text = "\n\n".join(lines)
    log_json(logger, logging.INFO, "Agent tool get_book_summary", count=len(summaries))

    return {"context": context_text, "summaries": summaries}


async def _run_get_sister_volumes(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.books_repository import BooksRepository

    book_id = args.get("book_id", "")
    if not book_id:
        return {"context": "No book_id provided.", "book_ids": []}

    repo = BooksRepository(ctx.session)
    books = await repo.find_sister_volumes(book_id)
    if not books:
        log_json(
            logger,
            logging.INFO,
            "Agent tool get_sister_volumes — no results",
            book_id=book_id,
        )
        return {"context": "No volumes found for this book.", "book_ids": []}

    lines = ["Volumes in this series:"]
    book_ids = []
    for b in books:
        volume = f"Volume {b.volume}" if b.volume is not None else "No volume number"
        lines.append(f"- {b.title}, {volume} (ID: {b.id})")
        book_ids.append(str(b.id))

    log_json(
        logger,
        logging.INFO,
        "Agent tool get_sister_volumes",
        book_id=book_id,
        count=len(books),
    )
    return {"context": "\n".join(lines), "book_ids": book_ids}


async def _run_get_current_page(ctx: QueryContext) -> dict:
    from app.db.repositories.pages_repository import PagesRepository
    from app.utils.markdown import strip_markdown

    if ctx.is_global or ctx.current_page is None or not ctx.book:
        log_json(
            logger,
            logging.INFO,
            "Agent tool get_current_page — not available",
            is_global=ctx.is_global,
        )
        return {"context": "Current page is not available in this context."}

    pages_repo = PagesRepository(ctx.session)
    page_rec = await pages_repo.find_one(ctx.book_id, ctx.current_page)

    if not page_rec or not page_rec.text:
        log_json(
            logger,
            logging.INFO,
            "Agent tool get_current_page — no text",
            page=ctx.current_page,
        )
        return {"context": f"No text found for page {ctx.current_page}."}

    book = ctx.book
    author_info = f", Author: {book.author}" if book.author else ""
    volume_info = f", Volume {book.volume}" if book.volume is not None else ""
    page_text = strip_markdown(page_rec.text)

    context = (
        f"[BookID: {ctx.book_id}, Book: {book.title or 'Unknown'}"
        f"{author_info}{volume_info}, Page {ctx.current_page}]\n"
        f"{page_text}"
    )
    log_json(
        logger,
        logging.INFO,
        "Agent tool get_current_page",
        page=ctx.current_page,
        chars=len(page_text),
    )
    return {"context": context}


async def _run_find_books_by_title(args: dict, ctx: QueryContext) -> List[dict]:
    question = args.get("question", "")
    if not hasattr(ctx, "_title_cache"):
        ctx._title_cache = {}
    if question in ctx._title_cache:
        result = ctx._title_cache[question]
        log_json(
            logger,
            logging.INFO,
            "Agent tool find_books_by_title (cached)",
            question=question[:120],
            books=len(result),
        )
        return result

    books = await find_books_by_title_in_question(
        question, ctx.session, categories=ctx.character_categories or None
    )
    result = books or []
    ctx._title_cache[question] = result
    log_json(
        logger,
        logging.INFO,
        "Agent tool find_books_by_title",
        question=question[:120],
        books=len(result),
    )
    return result


async def _run_rewrite_query(args: dict, ctx: QueryContext) -> dict:
    from app.services.rag.query_rewriter import QueryRewriter

    # Always rewrite when the agent explicitly calls this tool — the agent has
    # deliberate intent to resolve co-references, so a stale upstream enriched
    # question must not override the fresh rewrite.
    rewritten = await QueryRewriter().rewrite(ctx)
    ctx.enriched_question = rewritten
    log_json(logger, logging.INFO, "Agent tool rewrite_query", rewritten=rewritten[:80])
    return {"rewritten_question": rewritten}


async def _run_get_book_author(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.books_repository import BooksRepository

    question = args.get("question", "")
    repo = BooksRepository(ctx.session)
    result = await repo.find_author_by_title_in_question(
        question, ctx.character_categories or None
    )
    if result:
        title, author = result
        log_json(
            logger,
            logging.INFO,
            "Agent tool get_book_author",
            title=title,
            author=author,
        )
        return {
            "context": f"The book '{title}' was written by {author}.",
            "title": title,
            "author": author,
        }
    log_json(logger, logging.INFO, "Agent tool get_book_author", found=False)
    return {"context": "", "title": None, "author": None}


async def _run_get_books_by_author(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.books_repository import BooksRepository

    question = args.get("question", "")
    repo = BooksRepository(ctx.session)
    books = await repo.find_books_by_author_in_question(
        question, ctx.character_categories or None
    )
    if not books:
        log_json(logger, logging.INFO, "Agent tool get_books_by_author", found=0)
        return {"context": "", "books": []}

    author = books[0].author or "Unknown"
    lines = [f"Books by {author} in the library:"]
    book_list = []
    for b in books:
        volume = f", Volume {b.volume}" if b.volume is not None else ""
        pages = f", {b.total_pages} pages" if b.total_pages else ""
        lines.append(f"- {b.title}{volume}{pages} (ID: {b.id})")
        book_list.append(
            {
                "id": str(b.id),
                "title": b.title,
                "author": b.author,
                "volume": b.volume,
                "total_pages": b.total_pages,
            }
        )

    log_json(
        logger,
        logging.INFO,
        "Agent tool get_books_by_author",
        author=author,
        count=len(books),
    )
    return {"context": "\n".join(lines), "books": book_list}


async def _run_search_catalog(args: dict, ctx: QueryContext) -> dict:
    from app.services.rag.handlers.catalog import CatalogHandler

    query = args.get("query", "")
    context_text, count = await CatalogHandler._build_catalog_context(
        query, ctx.session, ctx.character_categories or None
    )
    context_text = CatalogHandler._prepend_current_book(context_text, ctx)
    log_json(
        logger, logging.INFO, "Agent tool search_catalog", query=query[:60], books=count
    )
    return {"context": context_text, "book_count": count}


async def _run_query_knowledge_graph(args: dict, ctx: QueryContext) -> dict:
    from app.llm.models import build_text_llm
    from app.db.repositories.graph_repository import GraphRepository
    import re
    import unicodedata

    query = args.get("query", "")
    if not query:
        return {"context": "No query provided.", "relations": []}

    # Skip if in single-book mode and graph has not been built for this book
    if (
        not ctx.is_global
        and ctx.book
        and getattr(ctx.book, "graph_milestone", None) != "complete"
    ):
        log_json(
            logger,
            logging.INFO,
            "Agent tool query_knowledge_graph — skipped, graph not available",
            book_id=ctx.book_id,
        )
        return {
            "context": "Knowledge graph is not available for this book.",
            "relations": [],
        }

    # Extract entities from the query using the LLM
    prompt = (
        "Extract any names of key entities (persons, locations, events, organizations, historical eras, or concepts) "
        "mentioned in the following user query. "
        "CRITICAL: Keep the names in their original script and spelling (e.g., Uyghur Arabic script). Do NOT translate or transliterate names to English or Latin characters. "
        "Return them ONLY as a comma-separated list, with no other text, explanation, or formatting. "
        "If no specific entities are mentioned, return an empty string.\n\n"
        f"Query: {query}"
    )

    try:
        llm = build_text_llm(ctx.agent_model)
        llm_response = await llm.ainvoke(prompt)

        entities = [
            unicodedata.normalize("NFC", e.strip())
            for e in re.split(r"[,，\u060c\n]", llm_response)
            if e.strip()
        ]
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Failed to extract entities for knowledge graph query",
            error=str(exc),
        )
        entities = []

    if not entities:
        log_json(
            logger,
            logging.INFO,
            "Agent tool query_knowledge_graph — no entities extracted",
            query=query[:60],
        )
        return {
            "context": "No entities extracted from the query to match in the knowledge graph.",
            "relations": [],
        }

    book_ids = None
    book_ids_arg = args.get("book_ids")
    if book_ids_arg:
        book_ids = [str(bid) for bid in book_ids_arg]
    elif not ctx.is_global and ctx.book_id:
        from app.db.repositories.books_repository import BooksRepository

        books_repo = BooksRepository(ctx.session)
        sister_volumes = await books_repo.find_sister_volumes(ctx.book_id)
        if sister_volumes:
            book_ids = [str(b.id) for b in sister_volumes]
        else:
            book_ids = [str(ctx.book_id)]

    search_entities = list(entities)
    if book_ids:
        try:
            from sqlalchemy import select
            from app.db.models import Book
            from app.db.repositories.system_configs_repository import (
                SystemConfigsRepository,
            )

            config_repo = SystemConfigsRepository(ctx.session)

            fictional_categories_val = await config_repo.get_value(
                "fictional_categories",
                "رومان, تارىخىي رومان, بالىلار رومانى, ساتىرىك رومان, پەلسەپىۋىي رومان, پوۋېست, پوۋېستلار, تارىخىي پوۋېست, ھېكايىلەر, تارىخىي ھېكايىلەر, بالىلار ھېكايىلېرى, چۆچەكلەر, قىسسە, تارىخىي قىسسە, داستان, داستانلار, تارىخىي داستان, رىۋايەتلەر, مەسەللەر, لەتىپىلەر, يۇمۇرلار, شېئىرلار, سەھنە ئەسەرلېرى, كىنو سېنارىيىلىرى, fiction, novel, story, drama, poetry, fairytale, fable, play",
            )
            fictional_cats = [
                c.strip().lower()
                for c in fictional_categories_val.split(",")
                if c.strip()
            ]

            stmt = select(Book).where(Book.id.in_(book_ids))
            res = await ctx.session.execute(stmt)
            books = res.scalars().all()
            for book in books:
                book_cats = [
                    c.strip().lower() for c in (book.categories or []) if c.strip()
                ]
                is_fictional = any(c in fictional_cats for c in book_cats)
                if is_fictional:
                    base_title = re.sub(r"[\s-]+\d+\s*$", "", book.title or "").strip()
                    if base_title:
                        for ent in entities:
                            namespaced = f"{ent} ({base_title})"
                            if namespaced not in search_entities:
                                search_entities.append(namespaced)
        except Exception as ns_exc:
            log_json(
                logger,
                logging.WARNING,
                "Failed to namespace entities for query",
                error=str(ns_exc),
            )

    graph_repo = GraphRepository()
    try:
        records = await graph_repo.query_subgraph(search_entities, book_ids=book_ids)
    except Exception as kg_exc:
        log_json(
            logger,
            logging.WARNING,
            "Knowledge graph query failed — returning empty result",
            error=str(kg_exc),
        )
        return {
            "context": "Knowledge graph is temporarily unavailable.",
            "relations": [],
        }
    finally:
        await graph_repo.close()

    if not records:
        return {
            "context": f"No knowledge graph relationships found for entities: {', '.join(entities)}.",
            "relations": [],
        }

    lines = [f"Knowledge Graph Relationships for: {', '.join(entities)}"]
    for rec in records:
        source = rec.get("source")
        source_type = rec.get("source_type", "Entity")
        rel = rec.get("rel", "RELATED_TO")
        target = rec.get("target")
        target_type = rec.get("target_type", "Entity")
        lines.append(
            f"- ({source}: {source_type}) -[{rel}]-> ({target}: {target_type})"
        )

    context_text = "\n".join(lines)
    log_json(
        logger,
        logging.INFO,
        "Agent tool query_knowledge_graph",
        query=query[:60],
        entities=entities,
        relations=len(records),
    )
    return {"context": context_text, "relations": records}


def _format_dictionary_context(source_label: str, entries: list[dict]) -> str:
    if not entries:
        return ""

    blocks = []
    for entry in entries:
        if source_label == "dictionary":
            blocks.append(
                "[Dictionary Source: Uyghur Dictionary, "
                f"Term: {entry.get('word', '')}]\n"
                f"{entry.get('definition') or 'No definition text available.'}"
            )
        elif source_label == "history_dictionary":
            transliteration = entry.get("transliteration")
            trans_part = (
                f", Transliteration: {transliteration}" if transliteration else ""
            )
            blocks.append(
                "[Dictionary Source: History Dictionary, "
                f"Term: {entry.get('term', '')}{trans_part}]\n"
                f"{entry.get('definition') or 'No definition text available.'}"
            )
        elif source_label == "english_uyghur_dictionary":
            blocks.append(
                "[Dictionary Source: English-Uyghur Dictionary, "
                f"English: {entry.get('english', '')}]\n"
                f"{entry.get('uyghur') or 'No translation text available.'}"
            )
        elif source_label == "names_dictionary":
            blocks.append(
                "[Dictionary Source: Names Dictionary, "
                f"Name: {entry.get('name', '')}]\n"
                "This name exists in the names dictionary."
            )
        elif source_label == "proverbs":
            vol = entry.get("volume")
            page = entry.get("page_number")
            ref_info = ""
            if vol and page:
                ref_info = f" (Found in Volume: {vol}, Page: {page})"
            elif page:
                ref_info = f" (Found on Page: {page})"
            elif vol:
                ref_info = f" (Found in Volume: {vol})"
            blocks.append(
                "[Dictionary/Culture Source: Uyghur Proverbs, "
                f"Text: {entry.get('text', '')}]\n"
                f"This is a Uyghur proverb: \"{entry.get('text', '')}\"{ref_info}"
            )
    return "\n\n---\n\n".join(blocks)


async def _run_lookup_uyghur_word(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository

    term = args.get("term", "")
    repo = DictionaryRepository(ctx.session)
    entries = await repo.lookup_uyghur_definition(term)
    context = _format_dictionary_context("dictionary", entries)
    log_json(
        logger,
        logging.INFO,
        "Agent tool lookup_uyghur_word",
        term=term[:60],
        count=len(entries),
    )
    return {"context": context, "entries": entries}


async def _run_lookup_history_term(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository

    term = args.get("term", "")
    repo = DictionaryRepository(ctx.session)
    entries = await repo.lookup_history_term(term)
    context = _format_dictionary_context("history_dictionary", entries)
    log_json(
        logger,
        logging.INFO,
        "Agent tool lookup_history_term",
        term=term[:60],
        count=len(entries),
    )
    return {"context": context, "entries": entries}


async def _run_translate_english_to_uyghur(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository

    term = args.get("term", "")
    repo = DictionaryRepository(ctx.session)
    entries = await repo.translate_english_to_uyghur(term)
    context = _format_dictionary_context("english_uyghur_dictionary", entries)
    log_json(
        logger,
        logging.INFO,
        "Agent tool translate_english_to_uyghur",
        term=term[:60],
        count=len(entries),
    )
    return {"context": context, "entries": entries}


async def _run_check_word_spelling(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository

    word = args.get("word", "")
    repo = DictionaryRepository(ctx.session)
    result = await repo.check_word_spelling(word)
    suggestions = result.get("suggestions", [])
    if result.get("is_known"):
        context = (
            "[Dictionary Source: Spelling Word List, "
            f"Word: {result.get('word', word)}]\n"
            "The word exists in the spelling word list."
        )
        found_count = 1
    elif suggestions:
        suggestion_text = "\n".join(f"- {s.get('word')}" for s in suggestions)
        context = (
            "[Dictionary Source: Spelling Word List, "
            f"Word: {word}]\n"
            "The exact word was not found. Similar spellings:\n"
            f"{suggestion_text}"
        )
        found_count = len(suggestions)
    else:
        context = (
            "[Dictionary Source: Spelling Word List, "
            f"Word: {word}]\n"
            "The exact word was not found and no similar spellings were found."
        )
        found_count = 0

    log_json(
        logger,
        logging.INFO,
        "Agent tool check_word_spelling",
        word=word[:60],
        found=found_count,
    )
    return {
        "context": context,
        "is_known": result.get("is_known", False),
        "suggestions": suggestions,
        "found_count": found_count,
    }


async def _run_search_language_sources(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository

    query = args.get("query", "")
    repo = DictionaryRepository(ctx.session)
    results = await repo.search_language_sources(query)

    context_parts = []
    found_count = 0
    for source_label, entries in results.items():
        found_count += len(entries)
        formatted = _format_dictionary_context(source_label, entries)
        if formatted:
            context_parts.append(formatted)

    context = (
        "\n\n---\n\n".join(context_parts)
        if context_parts
        else "NO RELEVANT DICTIONARY ENTRIES FOUND."
    )
    log_json(
        logger,
        logging.INFO,
        "Agent tool search_language_sources",
        query=query[:60],
        found=found_count,
    )
    return {"context": context, "results": results, "found_count": found_count}


async def _run_lookup_uyghur_name(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.dictionary_repository import DictionaryRepository
    from app.db.models import NamesDictionary
    from sqlalchemy import select

    term = args.get("term", "").strip()
    repo = DictionaryRepository(ctx.session)

    valid_groups = {
        "ئا",
        "ئە",
        "ب",
        "پ",
        "ت",
        "ج",
        "چ",
        "خ",
        "د",
        "ر",
        "ز",
        "ژ",
        "س",
        "ش",
        "غ",
        "ف",
        "ق",
        "ك",
        "گ",
        "ڭ",
        "ل",
        "م",
        "ن",
        "ھ",
        "ئو",
        "ئۇ",
        "ئۆ",
        "ئۈ",
        "ۋ",
        "ئې",
        "ئى",
        "ي",
    }

    if term in valid_groups or len(term) <= 2:
        stmt = (
            select(NamesDictionary)
            .where(NamesDictionary.letter_group == term)
            .order_by(NamesDictionary.name)
            .limit(100)
        )
        res = await ctx.session.execute(stmt)
        entries = [
            dict(id=r.id, name=r.name, letter_group=r.letter_group)
            for r in res.scalars().all()
        ]

        if entries:
            names_list = ", ".join(entry["name"] for entry in entries)
            context = (
                f"[Dictionary Source: Names Dictionary, Letter Group: {term}]\n"
                f"Here are Uyghur person names starting with the letter '{term}':\n"
                f"{names_list}"
            )
        else:
            context = f"No names found starting with the letter '{term}' in the names dictionary."
    else:
        entries = await repo.lookup_name(term, limit=10)
        if entries:
            context_parts = []
            for entry in entries:
                context_parts.append(
                    f"[Dictionary Source: Names Dictionary, Name: {entry.get('name')}]\n"
                    f"This name exists in the names dictionary (Letter Group: {entry.get('letter_group')})."
                )
            context = "\n\n---\n\n".join(context_parts)
        else:
            context = f"The name '{term}' was not found in the names dictionary."

    log_json(
        logger,
        logging.INFO,
        "Agent tool lookup_uyghur_name",
        term=term[:60],
        count=len(entries),
    )
    return {"context": context, "entries": entries, "found_count": len(entries)}


async def _run_lookup_proverbs(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.proverbs_repository import ProverbsRepository
    from app.db.models import Proverb
    from sqlalchemy import select

    term = args.get("term", "").strip()
    repo = ProverbsRepository(ctx.session)

    if not term:
        proverb = await repo.get_random_proverb()
        entries = [proverb] if proverb else []
    else:
        stmt = select(Proverb).where(Proverb.text.op("~*")(term)).limit(10)
        res = await ctx.session.execute(stmt)
        entries = list(res.scalars().all())

    entries_dict = []
    for entry in entries:
        entries_dict.append(
            {
                "id": entry.id,
                "text": entry.text,
                "volume": entry.volume,
                "page_number": entry.page_number,
            }
        )

    if entries_dict:
        context_parts = []
        for entry in entries_dict:
            source_info = (
                f"[Dictionary/Culture Source: Uyghur Proverbs, Text: {entry['text']}]"
            )
            ref_info = ""
            if entry.get("volume") or entry.get("page_number"):
                vol = entry.get("volume")
                page = entry.get("page_number")
                ref_info = (
                    f" (Found in Volume: {vol}, Page: {page})"
                    if vol and page
                    else f" (Found on Page: {page})"
                    if page
                    else f" (Found in Volume: {vol})"
                )
            context_parts.append(
                f"{source_info}\nThis is a Uyghur proverb: \"{entry['text']}\"{ref_info}"
            )
        context = "\n\n---\n\n".join(context_parts)
    else:
        context = f"No proverbs found matching '{term}'."

    log_json(
        logger,
        logging.INFO,
        "Agent tool lookup_proverbs",
        term=term[:60],
        count=len(entries_dict),
    )
    return {"context": context, "entries": entries_dict}


async def _run_search_quran(args: dict, ctx: QueryContext) -> dict:
    from app.db import session as db_session
    from app.db.models import Quran
    from sqlalchemy import select, or_

    surah = args.get("surah")
    ayah = args.get("ayah")
    q = args.get("q")

    async with db_session.async_session_factory() as session:
        if surah is not None:
            stmt = select(Quran).where(Quran.surah == surah)
            if ayah is not None:
                stmt = stmt.where(Quran.ayah == ayah)
            stmt = stmt.order_by(Quran.ayah.asc()).limit(30)
            res = await session.execute(stmt)
            entries = list(res.scalars().all())
        elif q:
            # Try semantic vector search first
            query_vector = None
            try:
                from app.services.rag.retrieval import embed_query

                query_vector = await embed_query(q, ctx)
            except Exception as e:
                logger.warning(
                    f"Failed to embed query in search_quran, falling back to keyword search: {e}"
                )

            if query_vector:
                from sqlalchemy import text

                embedding_str = str(query_vector)
                stmt = text("""
                    SELECT 
                        id, surah, surah_name_en, surah_name_ar, surah_name_ug,
                        ayah, text_ar, text_en, text_ug, created_at
                    FROM quran
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))
                    LIMIT :limit
                """)
                res = await session.execute(
                    stmt, {"embedding": embedding_str, "limit": 15}
                )
                entries = res.fetchall()
            else:
                # Fallback to standard keyword search
                search_pattern = f"%{q}%"
                stmt = (
                    select(Quran)
                    .where(
                        or_(
                            Quran.text_ug.ilike(search_pattern),
                            Quran.text_ar.ilike(search_pattern),
                            Quran.text_en.ilike(search_pattern),
                            Quran.surah_name_ug.ilike(search_pattern),
                            Quran.surah_name_en.ilike(search_pattern),
                        )
                    )
                    .order_by(Quran.surah.asc(), Quran.ayah.asc())
                    .limit(10)
                )
                res = await session.execute(stmt)
                entries = list(res.scalars().all())
        else:
            entries = []

    formatted_entries = []
    context_parts = []
    for entry in entries:
        formatted = {
            "surah": entry.surah,
            "surah_name_ug": entry.surah_name_ug,
            "surah_name_en": entry.surah_name_en,
            "surah_name_ar": entry.surah_name_ar,
            "ayah": entry.ayah,
            "text_ar": entry.text_ar,
            "text_ug": entry.text_ug,
            "text_en": entry.text_en,
        }
        formatted_entries.append(formatted)

        # Build clean markup citation context for RAG
        context_parts.append(
            f"[Source: Holy Quran, Surah: {entry.surah_name_ug} ({entry.surah_name_en}), Ayah: {entry.ayah}]\n"
            f"Arabic: {entry.text_ar}\n"
            f"Uyghur Translation: {entry.text_ug}\n"
            f"English Translation: {entry.text_en}"
        )

    context = (
        "\n\n---\n\n".join(context_parts)
        if context_parts
        else "No Quranic verses found matching criteria."
    )

    log_json(
        logger,
        logging.INFO,
        "Agent tool search_quran",
        surah=surah,
        ayah=ayah,
        q=q[:60] if q else None,
        count=len(formatted_entries),
    )
    return {"context": context, "entries": formatted_entries}
