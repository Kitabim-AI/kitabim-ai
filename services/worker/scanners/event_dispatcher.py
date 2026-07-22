"""
Event Dispatcher — processes the pipeline_events outbox and triggers downstream jobs.

This allows the pipeline to be reactive and run faster than 1-minute crons.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Book, Page, PipelineEvent
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.event_dispatcher")


async def _claim_candidate_pages(
    session, ctx, candidate_page_ids, milestone_column, step: str
):
    """
    Atomically claims the subset of candidate pages still idle for `step`,
    mirroring the *_scanner claim pattern (SKIP LOCKED + milestone flip to
    in_progress). Without this claim, this reactive dispatch and the
    corresponding scanner's own poll cycle can both enqueue a job for the
    same page — the redis lock inside the job resolves the race safely, but
    every loser is a wasted job invocation.
    """
    if not candidate_page_ids:
        return []

    id_stmt = (
        select(Page.id, Page.book_id)
        .join(Book, Page.book_id == Book.id)
        .where(
            Page.id.in_(candidate_page_ids),
            milestone_column == "idle",
            ~Book.status.in_(["error"]),
        )
        .with_for_update(skip_locked=True)
    )
    rows = (await session.execute(id_stmt)).fetchall()
    page_ids = [row[0] for row in rows]
    if not page_ids:
        return []

    book_ids = list({row[1] for row in rows})

    await session.execute(
        update(Page)
        .where(Page.id.in_(page_ids))
        .values(
            **{milestone_column.key: "in_progress"},
            worker_id=ctx.get("worker_id", "unknown"),
            claimed_at=func.now(),
            last_updated=func.now(),
        )
    )
    for book_id in book_ids:
        await BookMilestoneService.update_book_milestone_for_step(
            session, book_id, step
        )

    return page_ids


async def run_event_dispatcher(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        # Fetch unprocessed events
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

        chunking_candidates = [
            e.page_id for e in events if e.event_type == "ocr_succeeded"
        ]
        embedding_candidates = [
            e.page_id for e in events if e.event_type == "chunking_succeeded"
        ]

        chunking_page_ids = await _claim_candidate_pages(
            session, ctx, chunking_candidates, Page.chunking_milestone, "chunking"
        )
        embedding_page_ids = await _claim_candidate_pages(
            session, ctx, embedding_candidates, Page.embedding_milestone, "embedding"
        )

        processed_ids = [event.id for event in events]
        await session.execute(
            update(PipelineEvent)
            .where(PipelineEvent.id.in_(processed_ids))
            .values(processed=True)
        )
        await session.commit()

    enqueued = 0
    if chunking_page_ids:
        await redis.enqueue_job("chunking_job", page_ids=chunking_page_ids)
        enqueued += 1
    if embedding_page_ids:
        await redis.enqueue_job("embedding_job", page_ids=embedding_page_ids)
        enqueued += 1

    log_json(
        logger,
        logging.INFO,
        "event dispatcher run complete",
        events_processed=len(processed_ids),
        chunking_pages_claimed=len(chunking_page_ids),
        embedding_pages_claimed=len(embedding_page_ids),
        jobs_enqueued=enqueued,
    )
