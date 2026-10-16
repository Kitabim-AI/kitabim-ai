"""
LLM Spell Check Job — live-path worker job for on-demand Gemini-based spell
correction. Runs the pages given in page_ids (already set to in_progress by
the triggering endpoint). Not a pipeline stage: no PipelineEvent rows, no
retry_count bookkeeping, no scanner-driven page claiming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from app.core.config import settings
from app.core.pipeline import PAGE_MILESTONE_FAILED, PAGE_MILESTONE_SUCCEEDED
from app.db import session as db_session
from app.db.models import Page
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.llm_spell_check_service import (
    apply_llm_page_correction,
    correct_page_text,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.llm_spell_check_job")


async def llm_spell_check_job(ctx, page_ids: List[int]) -> None:
    log_json(
        logger, logging.INFO, "llm spell check job started", page_count=len(page_ids)
    )
    if not page_ids:
        return

    # Fetch configuration once before parallel processing
    model_name = "gemini-3.1-flash-lite"
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            val = await config_repo.get_value(
                "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
            )
            if isinstance(val, str):
                model_name = val
    except Exception:
        pass

    semaphore = asyncio.Semaphore(settings.max_parallel_llm_spell_check)

    async def process_page(page_id: int) -> None:
        async with semaphore:
            # 1. Read page and context data in a short-lived DB session
            page_text = None
            book_id = None
            page_number = None
            prev_text = None
            next_text = None

            async with db_session.async_session_factory() as session:
                pages_repo = PagesRepository(session)
                page = await session.get(Page, page_id)
                if page is None:
                    log_json(
                        logger,
                        logging.WARNING,
                        "llm spell check page not found",
                        page_id=page_id,
                    )
                    return

                if not page.text or not page.text.strip():
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_SUCCEEDED
                    )
                    await session.commit()
                    return

                book_id = page.book_id
                page_number = page.page_number
                page_text = page.text

                prev_page = await pages_repo.find_one(
                    page.book_id, page.page_number - 1
                )
                next_page = await pages_repo.find_one(
                    page.book_id, page.page_number + 1
                )
                prev_text = prev_page.text if prev_page else None
                next_text = next_page.text if next_page else None

            # 2. Call LLM without holding the DB connection
            corrected = None
            try:
                corrected = await correct_page_text(
                    page_text,
                    prev_text,
                    next_text,
                    model_name=model_name,
                )
            except Exception as exc:
                log_json(
                    logger,
                    logging.WARNING,
                    "llm spell check page failed",
                    book_id=book_id,
                    page=page_number,
                    error=repr(exc),
                )

            # 3. Apply results or mark failed in another short-lived session
            async with db_session.async_session_factory() as session:
                pages_repo = PagesRepository(session)
                page = await session.get(Page, page_id)
                if page is None:
                    return

                try:
                    if corrected is not None:
                        await apply_llm_page_correction(session, page, corrected)
                    else:
                        await pages_repo.set_llm_spell_check_status(
                            book_id, page_number, PAGE_MILESTONE_FAILED
                        )
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    log_json(
                        logger,
                        logging.ERROR,
                        "failed to persist llm spell check result",
                        book_id=book_id,
                        page=page_number,
                        error=repr(exc),
                    )
                    # Attempt a minimal status update to failed
                    try:
                        await pages_repo.set_llm_spell_check_status(
                            book_id, page_number, PAGE_MILESTONE_FAILED
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()

    await asyncio.gather(
        *(process_page(pid) for pid in page_ids), return_exceptions=True
    )

    log_json(
        logger, logging.INFO, "llm spell check job completed", page_count=len(page_ids)
    )
