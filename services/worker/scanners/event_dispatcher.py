"""
Event Dispatcher — processes the pipeline_events outbox and triggers downstream jobs.

When a book's OCR (and spell-check, if enabled) milestones become terminal and
`Book.structure_milestone == 'idle'`, claims `Book.structure_milestone = 'in_progress'`
and enqueues `structure_job(book_id=...)`.
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy import select, update

from app.db import session as db_session
from app.db.models import Page, PipelineEvent
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_structure_service import (
    claim_books_for_structure,
    enqueue_claimed_structure_jobs,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.event_dispatcher")


async def _claim_candidate_books_for_structure(
    session,
    candidate_page_ids: List[int],
    spell_check_enabled: bool,
) -> List[str]:
    if not candidate_page_ids:
        return []

    page_res = await session.execute(
        select(Page.book_id).where(Page.id.in_(candidate_page_ids)).distinct()
    )
    candidate_book_ids = [r[0] for r in page_res.fetchall() if r[0]]
    if not candidate_book_ids:
        return []

    return await claim_books_for_structure(
        session,
        book_ids=candidate_book_ids,
        require_spell_check_terminal=spell_check_enabled,
    )


async def run_event_dispatcher(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        stmt = (
            select(PipelineEvent)
            .where(PipelineEvent.processed.is_(False))
            .order_by(PipelineEvent.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            return

        config_repo = SystemConfigsRepository(session)
        spell_check_enabled = (
            await config_repo.get_value("spell_check_enabled", "false")
        ).lower() == "true"

        structure_trigger_types = (
            ("ocr_succeeded", "spell_check_succeeded", "spell_check_failed")
            if spell_check_enabled
            else ("ocr_succeeded",)
        )
        structure_candidate_page_ids = [
            e.page_id
            for e in events
            if e.page_id is not None and e.event_type in structure_trigger_types
        ]

        structure_book_ids = await _claim_candidate_books_for_structure(
            session, structure_candidate_page_ids, spell_check_enabled
        )

        processed_ids = [event.id for event in events]
        await session.execute(
            update(PipelineEvent)
            .where(PipelineEvent.id.in_(processed_ids))
            .values(processed=True)
        )
        await session.commit()

    enqueued = await enqueue_claimed_structure_jobs(
        redis,
        structure_book_ids,
        session_factory=db_session.async_session_factory,
    )

    log_json(
        logger,
        logging.INFO,
        "event dispatcher run complete",
        events_processed=len(processed_ids),
        structure_books_claimed=len(structure_book_ids),
        jobs_enqueued=enqueued,
    )
