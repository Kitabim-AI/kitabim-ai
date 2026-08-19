"""
Batch History Extraction Service — Handles Gemini Batch API request formatting, GCS staging,
batch submission, and status polling/result ingestion for history dictionary extraction.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import BatchHistoryExtractionJob, Book, Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.core.prompts import EXTRACTION_PROMPT_TEMPLATE
from app.services.history_extraction_service import (
    HistoryExtractionService,
    parse_extraction_entities,
)
from app.services.storage_service import storage
from app.utils.observability import log_json

logger = logging.getLogger("app.services.batch_history_extraction_service")


def _get_genai_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


async def _get_extraction_model(session: AsyncSession) -> str:
    config_repo = SystemConfigsRepository(session)
    val = await config_repo.get_value("history_gemini_model", "gemini-2.5-flash")
    model = val.strip() if val else "gemini-2.5-flash"
    return model.replace("models/", "", 1) if model.startswith("models/") else model


async def _get_extraction_batch_size(session: AsyncSession) -> int:
    config_repo = SystemConfigsRepository(session)
    val = await config_repo.get_value("history_batch_size", "15")
    if val and val.strip().isdigit():
        return int(val.strip())
    return 15


async def submit_batch_history_extraction_job(
    session: AsyncSession,
    book_id: str,
    min_significance: int = 5,
    batch_size: int | None = None,
    overlap: int = 2,
) -> BatchHistoryExtractionJob:
    """
    Builds sliding window prompt requests, creates Gemini Batch API JSONL dataset,
    uploads dataset to GCS audit copy & Gemini Files API, submits batch job, and saves tracking record.
    """
    if batch_size is None:
        batch_size = await _get_extraction_batch_size(session)
    job_id = str(uuid.uuid4())
    model_name = await _get_extraction_model(session)

    # Load book & pages
    book = await session.scalar(select(Book).where(Book.id == book_id))
    if not book:
        raise ValueError(f"Book not found: {book_id}")

    pages_res = await session.execute(
        select(Page).where(Page.book_id == book_id).order_by(Page.page_number.asc())
    )
    pages = list(pages_res.scalars().all())

    if not pages:
        raise ValueError(f"No pages found for book {book_id}")

    # Build sliding-window batch requests
    requests_jsonl = []
    i = 0
    batch_idx = 0
    while i < len(pages):
        batch = pages[i : i + batch_size]
        if not batch:
            break

        text_blocks = []
        for p in batch:
            p_num = p.page_number
            content = (
                getattr(p, "cleaned_text", None) or getattr(p, "text", "") or ""
            ).strip()
            if content:
                text_blocks.append(f"--- PAGE {p_num} ---\n{content}")

        pages_text = "\n\n".join(text_blocks)
        if pages_text.strip():
            page_numbers = [p.page_number for p in batch]
            log_json(
                logger,
                logging.INFO,
                "Preparing history extraction batch",
                book_id=book_id,
                book_title=book.title,
                page_start=page_numbers[0],
                page_end=page_numbers[-1],
                pages_in_batch=len(batch),
                total_pages=len(pages),
                batch_idx=batch_idx,
            )
            prompt = EXTRACTION_PROMPT_TEMPLATE.format(pages_text=pages_text)
            req_item = {
                "custom_id": f"history-batch-{batch_idx}",
                "request": {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            }
            requests_jsonl.append(json.dumps(req_item, ensure_ascii=False))
            batch_idx += 1

        step = max(1, batch_size - overlap)
        i += step

    if not requests_jsonl:
        raise ValueError(f"No non-empty text content found in book {book_id}")

    # Upload JSONL dataset file to GCS audit copy
    jsonl_bytes = "\n".join(requests_jsonl).encode("utf-8")
    remote_input_path = f"batch_history/inputs/{job_id}.jsonl"
    await storage.upload_bytes(jsonl_bytes, remote_input_path)
    gcs_input_uri = storage.get_gs_uri(remote_input_path)

    # Submit batch job via Gemini GenAI Client
    client = _get_genai_client()
    uploaded_file = client.files.upload(
        file=io.BytesIO(jsonl_bytes),
        config=types.UploadFileConfig(
            display_name=f"batch_history_{job_id}", mime_type="jsonl"
        ),
    )

    batch_job = client.batches.create(
        model=model_name,
        src=uploaded_file.name,
    )

    now = datetime.now(timezone.utc)
    job_record = BatchHistoryExtractionJob(
        id=job_id,
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        status="submitted",
        gcs_input_uri=gcs_input_uri,
        total_batches=len(requests_jsonl),
        min_significance=min_significance,
        model_name=model_name,
        submitted_at=now,
    )

    session.add(job_record)
    await session.commit()
    await session.refresh(job_record)

    log_json(
        logger,
        logging.INFO,
        "Submitted Gemini Batch History Extraction job",
        job_id=job_id,
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        batch_count=len(requests_jsonl),
    )
    return job_record


async def poll_and_process_batch_history_jobs(session: AsyncSession) -> int:
    """
    Polls active BatchHistoryExtractionJob records, ingests completed batch results,
    stages entities into history_dictionary_staging, and updates job statuses.
    """
    active_jobs_res = await session.execute(
        select(BatchHistoryExtractionJob).where(
            BatchHistoryExtractionJob.status.in_(["submitting", "submitted", "running"])
        )
    )
    active_jobs = list(active_jobs_res.scalars().all())
    if not active_jobs:
        return 0

    client = _get_genai_client()
    processed_count = 0
    extraction_service = HistoryExtractionService(session)

    for job in active_jobs:
        if not job.gemini_batch_id:
            continue

        try:
            batch_info = client.batches.get(name=job.gemini_batch_id)
            state_str = str(batch_info.state).upper()

            if "SUCCEEDED" in state_str:
                log_json(
                    logger,
                    logging.INFO,
                    "Batch History Extraction job succeeded, ingesting results",
                    job_id=job.id,
                    gemini_batch_id=job.gemini_batch_id,
                )

                # Fetch book metadata
                book = await session.scalar(select(Book).where(Book.id == job.book_id))
                book_title = book.title if book else "Unknown Book"
                volume = book.volume if book else None

                dest = getattr(batch_info, "dest", None)
                gcs_output_uri = getattr(dest, "gcs_uri", None) if dest else None
                output_file_name = getattr(dest, "file_name", None) if dest else None

                result_bytes: Optional[bytes] = None
                if gcs_output_uri:
                    parts = gcs_output_uri.replace("gs://", "").split("/", 1)
                    if len(parts) == 2:
                        try:
                            result_bytes = await storage.read_bytes(parts[1])
                        except Exception as e:
                            logger.warning(f"Could not read gcs_uri output: {e}")
                elif output_file_name:
                    try:
                        result_bytes = client.files.download(file=output_file_name)
                    except Exception as e:
                        logger.error(f"Failed to download batch output file: {e}")

                staged_count = 0
                if result_bytes:
                    lines = result_bytes.decode("utf-8").strip().split("\n")
                    for line in lines:
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            candidates = (
                                item.get("response", {})
                                .get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "")
                            )
                            if candidates:
                                entities = parse_extraction_entities(candidates)
                                for ent in entities:
                                    score = ent.get("significance_score", 5)
                                    if score < job.min_significance:
                                        continue

                                    # Commit per entity (default auto_commit=True) rather
                                    # than batching every entity in this job into one
                                    # commit at the end. A large book can have hundreds
                                    # of recurring-figure mentions each needing an
                                    # embedding/classification call, which can take
                                    # longer than one scanner cron interval — if that
                                    # invocation gets evicted before finishing, batching
                                    # would roll back every staged row from this run,
                                    # forcing the next tick to redo the same work from
                                    # scratch and never make forward progress.
                                    await extraction_service._stage_entity(
                                        book_id=job.book_id,
                                        book_title=book_title,
                                        volume=volume,
                                        entity=ent,
                                        model_name=job.model_name,
                                    )
                                    staged_count += 1
                        except Exception as parse_err:
                            logger.warning(
                                f"Error parsing batch output line: {parse_err}"
                            )

                job.status = "succeeded"
                job.completed_at = datetime.now(timezone.utc)
                job.gcs_output_uri = gcs_output_uri or output_file_name
                await session.commit()
                processed_count += 1
                log_json(
                    logger,
                    logging.INFO,
                    "Batch History Extraction job completed successfully",
                    job_id=job.id,
                    staged_count=staged_count,
                )

            elif any(s in state_str for s in ["FAILED", "CANCELLED", "EXPIRED"]):
                log_json(
                    logger,
                    logging.ERROR,
                    "Batch History Extraction job failed",
                    job_id=job.id,
                    state=state_str,
                )
                job.status = "failed"
                job.error = f"Gemini Batch job ended with state {state_str}"
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                processed_count += 1

            elif "RUNNING" in state_str and job.status != "running":
                job.status = "running"
                await session.commit()

        except Exception as exc:
            await session.rollback()
            log_json(
                logger,
                logging.ERROR,
                "Error polling Batch History Extraction job",
                job_id=job.id,
                error=str(exc),
            )

    return processed_count
