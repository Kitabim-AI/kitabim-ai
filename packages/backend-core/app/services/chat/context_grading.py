"""Context grading and formatting helpers used by the chat orchestrator."""

from __future__ import annotations

import logging

from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.services.chat.context_grading")


async def _build_human_message(ctx: QueryContext, question: str) -> str:
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
            # Titles (not just opaque IDs) let the agent judge for itself whether a
            # topic-shifted follow-up plausibly still belongs to these books, instead
            # of blindly reusing them and relying solely on the reactive score-based
            # fallback in tools.py::_run_search_chunks to catch a mismatch.
            from app.db.repositories.books_repository import BooksRepository

            books_repo = BooksRepository(ctx.session)
            books = await books_repo.find_titles_by_ids(ctx.context_book_ids[:10])
            if books:
                book_descriptions = []
                for b in books:
                    desc = f'"{b["title"]}"'
                    if b.get("author"):
                        desc += f" by {b['author']}"
                    desc += f" (book_id: {b['id']})"
                    book_descriptions.append(desc)
                lines.append("Previous response books: " + "; ".join(book_descriptions))
            else:
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
