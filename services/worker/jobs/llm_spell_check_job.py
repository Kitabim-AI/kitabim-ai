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
from app.services.llm_spell_check_service import correct_page_text
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.llm_spell_check_job")


async def llm_spell_check_job(ctx, page_ids: List[int]) -> None:
    log_json(
        logger, logging.INFO, "llm spell check job started", page_count=len(page_ids)
    )
    semaphore = asyncio.Semaphore(settings.max_parallel_llm_spell_check)

    async def process_page(page_id: int) -> None:
        async with semaphore:
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
                prev_page = await pages_repo.find_one(
                    page.book_id, page.page_number - 1
                )
                next_page = await pages_repo.find_one(
                    page.book_id, page.page_number + 1
                )
                try:
                    corrected = await correct_page_text(
                        page.text or "",
                        prev_page.text if prev_page else None,
                        next_page.text if next_page else None,
                        SystemConfigsRepository(session),
                    )
                    page.text = corrected
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_SUCCEEDED
                    )
                    await session.commit()
                except Exception as exc:
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_FAILED
                    )
                    await session.commit()
                    log_json(
                        logger,
                        logging.WARNING,
                        "llm spell check page failed",
                        book_id=page.book_id,
                        page=page.page_number,
                        error=repr(exc),
                    )

    await asyncio.gather(*(process_page(pid) for pid in page_ids))

    log_json(
        logger, logging.INFO, "llm spell check job completed", page_count=len(page_ids)
    )
