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
        book_ids: List of book IDs to fetch summaries for. Limit to at most 5 IDs —
                  each summary is large; passing more is wasteful and dilutes the answer.
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


AGENT_TOOLS = [
    search_chunks,
    search_books_by_summary,
    find_books_by_title,
    rewrite_query,
    get_book_author,
    get_books_by_author,
    search_catalog,
    get_book_summary,
    get_sister_volumes,
    get_current_page,
    query_knowledge_graph,
]


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

    book_ids = args.get("book_ids") or []
    if not book_ids:
        return {"context": "No book IDs provided.", "summaries": []}

    repo = BookSummariesRepository(ctx.session)
    summaries = await repo.get_summaries_for_books(book_ids)

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
    books = await find_books_by_title_in_question(
        question, ctx.session, categories=ctx.character_categories or None
    )
    result = books or []
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
        "mentioned in the following user query. Return them ONLY as a comma-separated list, with no other text, explanation, or formatting. "
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

    graph_repo = GraphRepository()
    try:
        records = await graph_repo.query_subgraph(entities, book_ids=book_ids)
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
