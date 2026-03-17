"""
Event Dispatcher — processes the pipeline_events outbox and triggers downstream jobs.

This allows the pipeline to be reactive and run faster than 1-minute crons.
"""
from __future__ import annotations

import logging
import json

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import PipelineEvent, Page
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.event_dispatcher")

async def run_event_dispatcher(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        # Fetch unprocessed events
        stmt = (
            select(PipelineEvent)
            .where(PipelineEvent.processed == False)
            .order_by(PipelineEvent.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            return

        processed_ids = []
        enqueued = 0

        for event in events:
            try:
                # Logic to determine next job
                if event.event_type == "ocr_succeeded":
                    # OCR success -> Trigger Chunking
                    # Note: We group pages by book to reduce jobs if needed,
                    # but for immediate dispatch, single page jobs are fine.
                    await redis.enqueue_job("chunking_job", page_ids=[event.page_id])
                    enqueued += 1
                
                elif event.event_type == "chunking_succeeded":
                    # Chunking success -> Trigger Embedding
                    await redis.enqueue_job("embedding_job", page_ids=[event.page_id])
                    enqueued += 1

                elif event.event_type == "embedding_succeeded":
                    # Embedding success -> Nothing to trigger (Driver handles book ready)
                    pass
                

                processed_ids.append(event.id)

            except Exception as exc:
                log_json(logger, logging.ERROR, "event dispatcher: failed to handle event",
                         event_id=event.id, error=str(exc))

        if processed_ids:
            await session.execute(
                update(PipelineEvent)
                .where(PipelineEvent.id.in_(processed_ids))
                .values(processed=True)
            )
            await session.commit()

        if enqueued:
            log_json(logger, logging.INFO, "event dispatcher run complete",
                     events_processed=len(processed_ids), jobs_enqueued=enqueued)
