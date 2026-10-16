"""
Batch LLM Spell Check Service — Gemini Batch API request formatting, GCS
staging, batch submission, and status polling/result ingestion for the
on-demand LLM-based spell correction pass. Mirrors
batch_history_extraction_service.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.pipeline import (
    PAGE_MILESTONE_FAILED,
    PAGE_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_SUCCEEDED,
)
from app.db.models import BatchLlmSpellCheckJob, Page
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.llm_spell_check_service import (
    apply_llm_page_correction,
    build_correction_prompt,
)
from app.services.storage_service import storage
from app.utils.observability import log_json

logger = logging.getLogger("app.services.batch_llm_spell_check_service")


def _get_genai_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


async def _get_llm_spell_check_model(session: AsyncSession) -> str:
    config_repo = SystemConfigsRepository(session)
    val = await config_repo.get_value(
        "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
    )
    model = val.strip() if val else "gemini-3.1-flash-lite"
    return model.replace("models/", "", 1) if model.startswith("models/") else model


async def submit_batch_llm_spell_check(
    book_id: str, page_ids: List[int], session: AsyncSession
) -> BatchLlmSpellCheckJob:
    """Builds one JSONL request per page (with prev/next page context),
    uploads the dataset to GCS (audit copy) and the Gemini Files API, submits
    the batch job, creates the tracking row, and bulk-sets the pages' status
    to in_progress."""
    job_uuid = str(uuid.uuid4())
    model_name = await _get_llm_spell_check_model(session)
    pages_repo = PagesRepository(session)

    pages = await pages_repo.get_pages_by_ids(page_ids)
    pages_by_id = {p.id: p for p in pages}
    if not pages_by_id:
        raise ValueError(f"No pages found for ids {page_ids}")

    all_pages = await pages_repo.get_pages_by_book_id(book_id)
    pages_by_number = {p.page_number: p for p in all_pages}

    requests_jsonl = []
    for page_id, page in pages_by_id.items():
        prev_page = pages_by_number.get(page.page_number - 1)
        next_page = pages_by_number.get(page.page_number + 1)
        prompt = build_correction_prompt(
            page.text or "",
            prev_page.text if prev_page else None,
            next_page.text if next_page else None,
        )
        req_item = {
            "custom_id": str(page.id),
            "request": {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0},
            },
        }
        requests_jsonl.append(json.dumps(req_item, ensure_ascii=False))

    jsonl_bytes = "\n".join(requests_jsonl).encode("utf-8")
    remote_input_path = f"batch_llm_spell_check/inputs/{job_uuid}.jsonl"
    await storage.upload_bytes(jsonl_bytes, remote_input_path)
    gcs_input_uri = storage.get_gs_uri(remote_input_path)

    client = _get_genai_client()
    uploaded_file = await asyncio.to_thread(
        client.files.upload,
        file=io.BytesIO(jsonl_bytes),
        config=types.UploadFileConfig(
            display_name=f"batch_llm_spell_check_{job_uuid}", mime_type="jsonl"
        ),
    )

    batch_job = await asyncio.to_thread(
        client.batches.create, model=model_name, src=uploaded_file.name
    )

    now = datetime.now(timezone.utc)
    job_record = BatchLlmSpellCheckJob(
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        page_ids=list(pages_by_id.keys()),
        status="submitting",
        gcs_input_uri=gcs_input_uri,
        total_batches=1,
        model_name=model_name,
        submitted_at=now,
    )
    session.add(job_record)

    await pages_repo.bulk_set_llm_spell_check_status(
        list(pages_by_id.keys()), PAGE_MILESTONE_IN_PROGRESS
    )

    await session.commit()
    await session.refresh(job_record)

    log_json(
        logger,
        logging.INFO,
        "Submitted Gemini Batch LLM Spell Check job",
        job_id=job_record.id,
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        page_count=len(pages_by_id),
    )
    return job_record


async def poll_and_process_batch_llm_spell_check_jobs(session: AsyncSession) -> int:
    """Polls active BatchLlmSpellCheckJob records, applies completed
    corrections to pages.text, and updates job/page statuses."""
    active_jobs_res = await session.execute(
        select(BatchLlmSpellCheckJob).where(
            BatchLlmSpellCheckJob.status.in_(["submitting", "submitted", "running"])
        )
    )
    active_jobs = list(active_jobs_res.scalars().all())
    if not active_jobs:
        return 0

    client = _get_genai_client()
    pages_repo = PagesRepository(session)
    processed_count = 0

    for job in active_jobs:
        try:
            batch_info = await asyncio.to_thread(
                client.batches.get, name=job.gemini_batch_id
            )
            state_str = str(batch_info.state).upper()

            if "SUCCEEDED" in state_str:
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
                            log_json(
                                logger,
                                logging.WARNING,
                                "could not read gcs_uri output",
                                uri=gcs_output_uri,
                                error=str(e),
                            )
                elif output_file_name:
                    try:
                        result_bytes = await asyncio.to_thread(
                            client.files.download, file=output_file_name
                        )
                    except Exception as e:
                        log_json(
                            logger,
                            logging.ERROR,
                            "failed to download batch output file",
                            file=output_file_name,
                            error=str(e),
                        )

                if result_bytes is None:
                    # Download failure must fail the job, not succeed it
                    error_msg = (
                        "Batch succeeded in Gemini but output could not be downloaded"
                    )
                    await pages_repo.bulk_set_llm_spell_check_status(
                        job.page_ids, PAGE_MILESTONE_FAILED
                    )
                    job.status = "failed"
                    job.error = error_msg
                    job.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    processed_count += 1
                    log_json(
                        logger,
                        logging.ERROR,
                        "batch output download failed",
                        job_id=job.id,
                        error=error_msg,
                    )
                    continue

                succeeded_page_ids: set[int] = set()
                lines = result_bytes.decode("utf-8").strip().split("\n")
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        page_id = int(item.get("custom_id"))
                        page = await session.get(Page, page_id)
                        if page is None:
                            continue

                        # Guard against overwriting concurrent manual edits during 24h batch
                        if job.submitted_at and page.last_updated:
                            sub_at = (
                                job.submitted_at
                                if job.submitted_at.tzinfo
                                else job.submitted_at.replace(tzinfo=timezone.utc)
                            )
                            page_upd = (
                                page.last_updated
                                if page.last_updated.tzinfo
                                else page.last_updated.replace(tzinfo=timezone.utc)
                            )
                            if page_upd > sub_at:
                                log_json(
                                    logger,
                                    logging.WARNING,
                                    "skipping batch spell check overwrite due to subsequent manual page edit",
                                    page_id=page.id,
                                    submitted_at=sub_at.isoformat(),
                                    last_updated=page_upd.isoformat(),
                                )
                                page.llm_spell_check_status = PAGE_MILESTONE_SUCCEEDED
                                page.llm_spell_check_at = datetime.now(timezone.utc)
                                succeeded_page_ids.add(page_id)
                                await session.commit()
                                continue

                        text = (
                            item.get("response", {})
                            .get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        ).strip()

                        await apply_llm_page_correction(session, page, text)
                        succeeded_page_ids.add(page_id)
                        # Commit per page so scanner eviction doesn't discard progress
                        await session.commit()
                    except Exception as parse_err:
                        await session.rollback()
                        log_json(
                            logger,
                            logging.WARNING,
                            "error parsing batch llm spell check output line",
                            job_id=job.id,
                            error=str(parse_err),
                        )

                failed_page_ids = [
                    pid for pid in job.page_ids if pid not in succeeded_page_ids
                ]
                if failed_page_ids:
                    await pages_repo.bulk_set_llm_spell_check_status(
                        failed_page_ids, PAGE_MILESTONE_FAILED
                    )

                job.status = "succeeded"
                job.completed_at = datetime.now(timezone.utc)
                job.gcs_output_uri = gcs_output_uri or output_file_name
                await session.commit()
                processed_count += 1
                log_json(
                    logger,
                    logging.INFO,
                    "Batch LLM Spell Check job completed",
                    job_id=job.id,
                    succeeded=len(succeeded_page_ids),
                    failed=len(failed_page_ids),
                )

            elif any(s in state_str for s in ["FAILED", "CANCELLED", "EXPIRED"]):
                await pages_repo.bulk_set_llm_spell_check_status(
                    job.page_ids, PAGE_MILESTONE_FAILED
                )
                job.status = "failed"
                job.error = f"Gemini Batch job ended with state {state_str}"
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                processed_count += 1
                log_json(
                    logger,
                    logging.ERROR,
                    "Batch LLM Spell Check job failed",
                    job_id=job.id,
                    state=state_str,
                )

            elif "RUNNING" in state_str and job.status != "running":
                job.status = "running"
                await session.commit()

        except Exception as exc:
            await session.rollback()
            log_json(
                logger,
                logging.ERROR,
                "Error polling Batch LLM Spell Check job",
                job_id=job.id,
                error=str(exc),
            )

    return processed_count
