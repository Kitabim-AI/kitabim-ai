"""
Summary Job — generates and stores a semantic summary + embedding for one book.

Triggered by:
  - pipeline_driver when a book first reaches 'ready' status
  - summary_scanner for backfill / retry of failed books

Process:
  1. Load all page texts for the book (ordered by page_number)
  2. Pass full text to LLM (SUMMARY_MAX_CHARS=3M chars is a safety ceiling for outlier books)
  3. Call Gemini chat model to generate a structured Uyghur summary
  4. Embed the summary using GeminiEmbeddings
  5. Upsert into book_summaries table

Job failure does not affect book availability — books without summaries fall
back to the existing category-based search in rag_service.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.prompts import BOOK_SUMMARY_PROMPT
from app.db import session as db_session
from app.db.models import Book, Page
from app.db.repositories.book_summaries import BookSummariesRepository
from app.db.repositories.system_configs import SystemConfigsRepository
from app.langchain import build_text_chain
from app.langchain.models import GeminiEmbeddings
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.summary_job")


def _sample_text(pages_text: list[str], max_chars: int) -> str:
    """
    Concatenate page texts and sample if total exceeds max_chars.
    Strategy: take first 40%, middle 20%, last 40% to get broad coverage.
    """
    full_text = "\n\n".join(t for t in pages_text if t)
    if len(full_text) <= max_chars:
        return full_text

    first = full_text[: int(max_chars * 0.4)]
    mid_start = len(full_text) // 2 - int(max_chars * 0.1)
    mid_end = mid_start + int(max_chars * 0.2)
    middle = full_text[mid_start:mid_end]
    last = full_text[-int(max_chars * 0.4):]
    return first + "\n\n...\n\n" + middle + "\n\n...\n\n" + last


async def summary_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "summary job started", book_id=book_id)

    try:
        async with db_session.async_session_factory() as session:
            # Fetch models from system_configs (no fallback — must be configured in DB)
            config_repo = SystemConfigsRepository(session)
            gemini_chat_model = await config_repo.get_value("gemini_chat_model")
            if not gemini_chat_model:
                raise RuntimeError("system_config 'gemini_chat_model' is not set")
            gemini_embedding_model = await config_repo.get_value("gemini_embedding_model")
            if not gemini_embedding_model:
                raise RuntimeError("system_config 'gemini_embedding_model' is not set")

            # Load book metadata
            result = await session.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            if not book:
                log_json(logger, logging.WARNING, "summary job: book not found", book_id=book_id)
                return

            # Load all page texts ordered by page_number, excluding TOC
            result = await session.execute(
                select(Page.text)
                .where(Page.book_id == book_id, Page.text.isnot(None), Page.is_toc.is_(False))
                .order_by(Page.page_number)
            )
            pages_text = [row[0] for row in result.fetchall() if row[0]]

        if not pages_text:
            log_json(logger, logging.WARNING, "summary job: no page text found", book_id=book_id)
            return

        # Full text is passed directly; _sample_text only truncates the rare outlier book
        # that exceeds the model's context window (safety ceiling: SUMMARY_MAX_CHARS=3M chars)
        sampled_text = _sample_text(pages_text, settings.summary_max_chars)

        # Generate summary via Gemini chat model
        chain = build_text_chain(
            BOOK_SUMMARY_PROMPT,
            gemini_chat_model,
            run_name="summary_chain",
        )
        summary = await chain.ainvoke(
            {
                "title": book.title or "Unknown",
                "author": book.author or "Unknown",
                "text": sampled_text,
            }
        )
        summary = (summary or "").strip()
        if not summary:
            log_json(logger, logging.WARNING, "summary job: LLM returned empty summary", book_id=book_id)
            return

        # Embed the summary
        embeddings_model = GeminiEmbeddings(gemini_embedding_model)
        vectors = await embeddings_model.aembed_documents([summary])
        embedding = vectors[0]

        async with db_session.async_session_factory() as session:
            repo = BookSummariesRepository(session)
            await repo.upsert(book_id=book_id, summary=summary, embedding=embedding)
            await session.commit()

        log_json(
            logger, logging.INFO, "summary job completed",
            book_id=book_id,
            summary_chars=len(summary),
            text_chars=len(sampled_text),
        )

    except Exception as exc:
        log_json(logger, logging.ERROR, "summary job failed", book_id=book_id, error=str(exc))
        raise
