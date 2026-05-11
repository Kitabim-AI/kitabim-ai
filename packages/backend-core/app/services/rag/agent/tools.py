"""Agent tool schemas and dispatch for the agentic RAG loop.

Each tool wraps existing retrieval code — no new retrieval logic lives here.
The @tool decorator provides the JSON schema that Gemini uses for function calling.
dispatch_tool() routes a tool call name+args to the real async implementation.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.tools import tool

from app.services.rag.context import QueryContext
from app.services.rag.retrieval import embed_query, find_books_by_title_in_question, vector_search
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.tools")


# ---------------------------------------------------------------------------
# Tool schemas (bodies are never executed — only the schema is used by bind_tools)
# ---------------------------------------------------------------------------

@tool
def search_chunks(query: str, book_ids: Optional[List[str]] = None) -> str:
    """Vector-search book chunks for passages relevant to a query.

    Args:
        query: The search query to embed and match against book passages.
        book_ids: Optional list of book IDs to restrict the search scope.
                  Omit to search across all books.
    """
    return ""


@tool
def search_books_by_summary(query: str, book_ids: Optional[List[str]] = None) -> str:
    """Find books whose summaries are most relevant to a query.

    Call this before search_chunks when you don't know which books to search.
    Returns a list of book IDs sorted by relevance.

    Args:
        query: The question or topic to match against book summaries.
        book_ids: Optional candidate set to restrict to (e.g. character-filtered books).
    """
    return ""


@tool
def find_books_by_title(question: str) -> str:
    """Return book IDs for a title explicitly mentioned in the question.

    Handles both «quoted» exact match and fuzzy word-prefix match.
    Returns an empty list if no recognisable title is found.

    Args:
        question: The full user question (title extraction is done server-side).
    """
    return ""


@tool
def rewrite_query(question: str) -> str:
    """Resolve pronouns and co-references in a follow-up question using chat history.

    Call when the question contains Uyghur pronouns such as ئۇ، بۇ، شۇ، ئۇنىڭ، بۇنىڭ.
    Returns the rewritten standalone question.

    Args:
        question: The user's original question that contains unresolved references.
    """
    return ""


@tool
def get_book_author(question: str) -> str:
    """Look up the author of a specific book title mentioned in the question.

    Call when the user asks who wrote a book or wants the author of a title.
    Returns the book title and its author name.

    Args:
        question: The user's question or a phrase containing the book title to look up.
    """
    return ""


@tool
def get_books_by_author(question: str) -> str:
    """Look up all books written by an author named in the question.

    Call when the user asks what books a specific author has written.
    Returns a list of books with volume and page counts.

    Args:
        question: The user's question or a phrase containing the author name to look up.
    """
    return ""


@tool
def search_catalog(query: str) -> str:
    """Search the library catalog for books, authors, or general library listings.

    Call for general library browsing questions: what books exist, what an author has
    published, or catalog-level metadata. Do NOT call for content questions — use
    search_chunks for those.

    Args:
        query: The user's question about the library catalog.
    """
    return ""


AGENT_TOOLS = [
    search_chunks,
    search_books_by_summary,
    find_books_by_title,
    rewrite_query,
    get_book_author,
    get_books_by_author,
    search_catalog,
]


# ---------------------------------------------------------------------------
# Dispatch — routes tool call name+args to the real async implementation
# ---------------------------------------------------------------------------

async def dispatch_tool(tool_name: str, tool_args: dict, ctx: QueryContext) -> dict:
    """Execute a named tool and return a serialisable result dict."""
    try:
        if tool_name == "search_chunks":
            return {"chunks": await _run_search_chunks(tool_args, ctx)}
        if tool_name == "search_books_by_summary":
            return {"book_ids": await _run_search_books_by_summary(tool_args, ctx)}
        if tool_name == "find_books_by_title":
            return {"book_ids": await _run_find_books_by_title(tool_args, ctx)}
        if tool_name == "rewrite_query":
            return await _run_rewrite_query(tool_args, ctx)
        if tool_name == "get_book_author":
            return await _run_get_book_author(tool_args, ctx)
        if tool_name == "get_books_by_author":
            return await _run_get_books_by_author(tool_args, ctx)
        if tool_name == "search_catalog":
            return await _run_search_catalog(tool_args, ctx)
        return {"error": f"Unknown tool: {tool_name}"}
    except Exception as exc:
        log_json(logger, logging.WARNING, "Agent tool failed", tool=tool_name, error=str(exc))
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

async def _run_search_chunks(args: dict, ctx: QueryContext) -> List[dict]:
    query = args.get("query", "")
    book_ids: List[str] = args.get("book_ids") or []

    query_vector = await embed_query(query, ctx)
    if not query_vector:
        return []

    results = await vector_search(ctx, book_ids, query_vector=query_vector)

    log_json(
        logger, logging.INFO, "Agent tool search_chunks",
        query=query[:60], book_count=len(book_ids), results=len(results),
    )
    return results


async def _run_search_books_by_summary(args: dict, ctx: QueryContext) -> List[str]:
    from app.db.repositories.book_summaries import BookSummariesRepository
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
        threshold=settings.summary_threshold,
        limit=20,
    )

    log_json(logger, logging.INFO, "Agent tool search_books_by_summary", query=query[:60], books=len(book_ids))
    return book_ids


async def _run_find_books_by_title(args: dict, ctx: QueryContext) -> List[str]:
    question = args.get("question", "")
    book_ids = await find_books_by_title_in_question(question, ctx.session)
    result = book_ids or []
    log_json(logger, logging.INFO, "Agent tool find_books_by_title", question=question[:120], books=len(result))
    return result


async def _run_rewrite_query(args: dict, ctx: QueryContext) -> dict:
    if ctx.enriched_question:
        log_json(logger, logging.INFO, "Agent tool rewrite_query — already rewritten, skipping")
        return {"rewritten_question": ctx.enriched_question}

    from app.services.rag.query_rewriter import QueryRewriter

    rewritten = await QueryRewriter().rewrite(ctx)
    ctx.enriched_question = rewritten
    log_json(logger, logging.INFO, "Agent tool rewrite_query", rewritten=rewritten[:80])
    return {"rewritten_question": rewritten}


async def _run_get_book_author(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.books import BooksRepository

    question = args.get("question", "")
    repo = BooksRepository(ctx.session)
    result = await repo.find_author_by_title_in_question(
        question, ctx.character_categories or None
    )
    if result:
        title, author = result
        log_json(logger, logging.INFO, "Agent tool get_book_author", title=title, author=author)
        return {"context": f"The book '{title}' was written by {author}.", "title": title, "author": author}
    log_json(logger, logging.INFO, "Agent tool get_book_author", found=False)
    return {"context": "", "title": None, "author": None}


async def _run_get_books_by_author(args: dict, ctx: QueryContext) -> dict:
    from app.db.repositories.books import BooksRepository

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
        lines.append(f"- {b.title}{volume}{pages}")
        book_list.append({"title": b.title, "author": b.author, "volume": b.volume, "total_pages": b.total_pages})

    log_json(logger, logging.INFO, "Agent tool get_books_by_author", author=author, count=len(books))
    return {"context": "\n".join(lines), "books": book_list}


async def _run_search_catalog(args: dict, ctx: QueryContext) -> dict:
    from app.services.rag.handlers.catalog import CatalogHandler

    query = args.get("query", "")
    context_text, count = await CatalogHandler._build_catalog_context(
        query, ctx.session, ctx.character_categories or None
    )
    context_text = CatalogHandler._prepend_current_book(context_text, ctx)
    log_json(logger, logging.INFO, "Agent tool search_catalog", query=query[:60], books=count)
    return {"context": context_text, "book_count": count}
