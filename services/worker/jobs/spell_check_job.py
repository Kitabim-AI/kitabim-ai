"""
Spell Check Job — batch spell check runner for the background worker.

Receives a list of page_ids (already set to in_progress by the scanner)
and runs spell check on each via the shared spell_check_service.
"""
from __future__ import annotations

import logging
import traceback
from typing import List

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, PipelineEvent
from app.services.spell_check_service import run_spell_check_for_page
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.spell_check_job")


async def spell_check_job(ctx, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "spell check job started", page_count=len(page_ids))

    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    succeeded = 0
    failed = 0

    for page in pages:
        try:
            async with db_session.async_session_factory() as session:
                issue_count = await run_spell_check_for_page(session, page)
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="spell_check_succeeded",
                    payload=f'{{"issues": {issue_count}}}'
                ))
                await session.commit()

            succeeded += 1
            log_json(logger, logging.DEBUG, "spell check page succeeded",
                     book_id=page.book_id, page=page.page_number, ocr_issues=issue_count)

        except Exception as exc:
            async with db_session.async_session_factory() as session:
                error_msg = repr(exc)[:500]
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(spell_check_milestone="error", last_updated=func.now())
                )
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="spell_check_failed",
                    payload=f'{{"error": "{error_msg}"}}'
                ))
                await session.commit()
            failed += 1
            log_json(logger, logging.WARNING, "spell check page failed",
                     book_id=page.book_id, page=page.page_number,
                     error=repr(exc), traceback=traceback.format_exc())

    log_json(logger, logging.INFO, "spell check job completed",
             succeeded=succeeded, failed=failed)
