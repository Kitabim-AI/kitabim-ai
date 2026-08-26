"""
Batch OCR Service — Handles Gemini Batch API request formatting, GCS staging,
batch submission, and status polling/result ingestion.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Any, Optional

import fitz
from google import genai
from google.genai import types
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompts import OCR_PROMPT
from app.db.models import BatchOCRJob, Page, PipelineEvent
from app.db.repositories.auto_correct_rules_repository import (
    AutoCorrectRulesRepository,
)
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.llm.models import disabled_thinking_config
from app.services.book_milestone_service import BookMilestoneService
from app.services.storage_service import storage
from app.utils.observability import log_json, make_pipeline_event_payload
from app.utils.text import clean_uyghur_text, is_degenerate_ocr_output, is_toc_page

logger = logging.getLogger("app.services.batch_ocr_service")


async def _build_ocr_prompt(session: AsyncSession) -> str:
    frequent_corrections = await AutoCorrectRulesRepository(
        session
    ).get_frequent_corrections_block()
    return OCR_PROMPT.format(frequent_corrections=frequent_corrections)


def _get_genai_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


async def submit_batch_ocr_job(
    session: AsyncSession,
    book_id: str,
    pages: List[Page],
    doc: fitz.Document,
    gemini_ocr_model: str,
) -> BatchOCRJob:
    """
    Renders page images, builds Gemini Batch API JSONL dataset, uploads to GCS,
    submits batch job to Gemini API, and creates DB tracking record.
    """
    job_id = str(uuid.uuid4())
    prompt = await _build_ocr_prompt(session)

    # 1. Build JSONL request entries
    raw_thinking_config = disabled_thinking_config(gemini_ocr_model)
    gen_config = types.GenerateContentConfig(
        temperature=0.0,
        thinking_config=types.ThinkingConfig(**raw_thinking_config),
        max_output_tokens=settings.ocr_max_output_tokens,
    )
    gen_config_dict = gen_config.model_dump(
        by_alias=True, mode="json", exclude_none=True
    )

    jsonl_lines: List[str] = []
    for page in pages:
        fitz_page = doc.load_page(page.page_number - 1)  # 0-indexed
        pix = fitz_page.get_pixmap(
            matrix=fitz.Matrix(
                settings.ocr_page_zoom_factor, settings.ocr_page_zoom_factor
            )
        )
        img_bytes = pix.tobytes("jpeg")
        base64_img = base64.b64encode(img_bytes).decode("utf-8")

        request_entry = {
            "custom_id": f"page_{page.id}",
            "key": f"page_{page.id}",
            "request": {
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/jpeg",
                                    "data": base64_img,
                                }
                            },
                        ],
                    }
                ],
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE",
                    },
                    {
                        "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                        "threshold": "BLOCK_NONE",
                    },
                ],
                "generationConfig": gen_config_dict,
            },
        }
        jsonl_lines.append(json.dumps(request_entry))

    jsonl_content = "\n".join(jsonl_lines).encode("utf-8")

    # 2. Upload JSONL to storage (our own audit copy of the request payload)
    remote_input_path = f"batch_ocr/inputs/{job_id}.jsonl"
    await storage.upload_bytes(jsonl_content, remote_input_path)
    gcs_input_uri = storage.get_gs_uri(remote_input_path)

    # 3. Upload the same JSONL to Gemini's Files API and submit the batch job.
    # The Gemini Developer API (API-key auth) only accepts `inlined_requests` or
    # a `files/...` reference as the batch source — a raw gs:// URI is only
    # valid for a Vertex AI client, which this service does not use.
    model = (
        gemini_ocr_model.replace("models/", "", 1)
        if gemini_ocr_model.startswith("models/")
        else gemini_ocr_model
    )
    gemini_batch_id: Optional[str] = None
    status = "submitted"
    err_msg: Optional[str] = None

    try:
        client = _get_genai_client()
        uploaded_file = client.files.upload(
            file=io.BytesIO(jsonl_content),
            config=types.UploadFileConfig(
                display_name=f"batch_ocr_{job_id}", mime_type="application/jsonl"
            ),
        )
        batch_job = client.batches.create(
            model=model,
            src=uploaded_file.name,
        )
        gemini_batch_id = batch_job.name
        log_json(
            logger,
            logging.INFO,
            "Submitted Gemini Batch OCR job",
            job_id=job_id,
            gemini_batch_id=gemini_batch_id,
            book_id=book_id,
            page_count=len(pages),
        )
    except Exception as exc:
        err_msg = str(exc)[:500]
        log_json(
            logger,
            logging.ERROR,
            "Failed to submit Gemini Batch OCR job",
            job_id=job_id,
            book_id=book_id,
            error=err_msg,
        )
        status = "failed"

    # 4. Save BatchOCRJob to database
    batch_job_row = BatchOCRJob(
        id=job_id,
        gemini_batch_id=gemini_batch_id,
        book_id=book_id,
        page_ids=[p.id for p in pages],
        status=status,
        gcs_input_uri=gcs_input_uri,
        total_pages=len(pages),
        error=err_msg,
        submitted_at=datetime.now(timezone.utc) if status == "submitted" else None,
    )
    session.add(batch_job_row)

    if status == "failed":
        # Mark pages as failed so scanner can retry
        await session.execute(
            update(Page)
            .where(Page.id.in_([p.id for p in pages]))
            .values(
                ocr_milestone="failed",
                retry_count=Page.retry_count + 1,
                error=f"Batch OCR submission failed: {err_msg}",
                last_updated=func.now(),
            )
        )
        await session.commit()
        await BookMilestoneService.update_book_milestone_for_step(
            session, book_id, "ocr"
        )
        await session.commit()
    else:
        await session.commit()

    return batch_job_row


async def poll_and_process_batch_ocr_jobs(session: AsyncSession) -> int:
    """
    Polls active batch OCR jobs, retrieves status from Gemini API,
    and ingests completed results or records failures.
    """
    config_repo = SystemConfigsRepository(session)
    timeout_hours = float(await config_repo.get_value("ocr_batch_timeout_hours", "24"))
    ocr_max_retry_count = int(await config_repo.get_value("ocr_max_retry_count", "3"))

    # Find jobs in submitting, submitted, or running status
    result = await session.execute(
        select(BatchOCRJob).where(
            BatchOCRJob.status.in_(["submitting", "submitted", "running"])
        )
    )
    active_jobs = list(result.scalars().all())

    if not active_jobs:
        return 0

    processed_count = 0
    client = _get_genai_client()

    for job in active_jobs:
        now = datetime.now(timezone.utc)
        # Check timeout
        if (
            job.created_at
            and (now - job.created_at).total_seconds() > timeout_hours * 3600
        ):
            log_json(
                logger,
                logging.WARNING,
                "Batch OCR job timed out",
                job_id=job.id,
                gemini_batch_id=job.gemini_batch_id,
            )
            job.status = "failed"
            job.error = f"Batch OCR job timed out after {timeout_hours} hours"
            job.completed_at = now

            await session.execute(
                update(Page)
                .where(Page.id.in_(job.page_ids))
                .values(
                    ocr_milestone="failed",
                    retry_count=Page.retry_count + 1,
                    error="Batch OCR job timed out",
                    last_updated=func.now(),
                )
            )
            await session.commit()
            await BookMilestoneService.update_book_milestone_for_step(
                session, job.book_id, "ocr"
            )
            await session.commit()
            continue

        if not job.gemini_batch_id:
            continue

        try:
            batch_job_info = client.batches.get(name=job.gemini_batch_id)
            state_str = str(batch_job_info.state).upper()

            if "RUNNING" in state_str:
                if job.status != "running":
                    job.status = "running"
                    await session.commit()
                continue

            elif "PENDING" in state_str or "SUBMITTED" in state_str:
                continue

            elif "SUCCEEDED" in state_str:
                log_json(
                    logger,
                    logging.INFO,
                    "Batch OCR job succeeded, processing results",
                    job_id=job.id,
                    gemini_batch_id=job.gemini_batch_id,
                )
                await _ingest_batch_ocr_results(
                    session, job, batch_job_info, client, ocr_max_retry_count
                )
                processed_count += 1

            elif "FAILED" in state_str or "CANCELLED" in state_str:
                log_json(
                    logger,
                    logging.ERROR,
                    "Batch OCR job failed or cancelled",
                    job_id=job.id,
                    gemini_batch_id=job.gemini_batch_id,
                    state=state_str,
                )
                job.status = "failed"
                job.error = f"Gemini Batch job end state: {state_str}"
                job.completed_at = now

                await session.execute(
                    update(Page)
                    .where(Page.id.in_(job.page_ids))
                    .values(
                        ocr_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        error=f"Gemini Batch OCR failed ({state_str})",
                        last_updated=func.now(),
                    )
                )
                await session.commit()
                await BookMilestoneService.update_book_milestone_for_step(
                    session, job.book_id, "ocr"
                )
                await session.commit()

        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "Error checking status for batch job",
                job_id=job.id,
                gemini_batch_id=job.gemini_batch_id,
                error=str(exc),
            )

    return processed_count


async def _record_page_ocr_failure(
    session: AsyncSession,
    page_id: int,
    current_retry_count: int,
    ocr_max_retry_count: int,
    error_msg: str,
) -> bool:
    """
    Marks a batch OCR page result as failed (retryable), or — once
    ocr_max_retry_count is exhausted — gracefully skips it (succeeded with
    blank text), mirroring the online OCR path so a single bad page doesn't
    block the whole book from completing. Returns True if the page was
    skipped (counts toward succeeded_pages).
    """
    next_retry_count = current_retry_count + 1

    if next_retry_count >= ocr_max_retry_count:
        skip_error = (
            f"Batch OCR failed after {ocr_max_retry_count} retries: "
            f"{error_msg}. Page skipped."
        )
        await session.execute(
            update(Page)
            .where(Page.id == page_id)
            .values(
                text="",
                is_toc=False,
                ocr_milestone="succeeded",
                retry_count=next_retry_count,
                error=skip_error,
                last_updated=func.now(),
            )
        )
        session.add(
            PipelineEvent(
                page_id=page_id,
                event_type="ocr_succeeded",
                payload=make_pipeline_event_payload(
                    extra_fields={
                        "skipped": True,
                        "batch": True,
                        "error": error_msg,
                    }
                ),
            )
        )
        return True

    await session.execute(
        update(Page)
        .where(Page.id == page_id)
        .values(
            ocr_milestone="failed",
            retry_count=next_retry_count,
            error=error_msg,
            last_updated=func.now(),
        )
    )
    session.add(
        PipelineEvent(
            page_id=page_id,
            event_type="ocr_failed",
            payload=make_pipeline_event_payload(
                extra_fields={"error": error_msg, "batch": True}
            ),
        )
    )
    return False


async def _ingest_batch_ocr_results(
    session: AsyncSession,
    job: BatchOCRJob,
    batch_job_info: Any,
    client: genai.Client,
    ocr_max_retry_count: int,
) -> None:
    """
    Downloads result dataset, parses output JSONL, updates page records,
    and emits pipeline events.
    """
    dest = getattr(batch_job_info, "dest", None)
    gcs_output_uri = getattr(dest, "gcs_uri", None) if dest else None
    output_file_name = getattr(dest, "file_name", None) if dest else None

    result_bytes: Optional[bytes] = None
    output_ref: Optional[str] = None

    if gcs_output_uri:
        # Vertex AI destinations report results as a gs:// URI in our own bucket.
        output_ref = gcs_output_uri
        parts = gcs_output_uri.replace("gs://", "").split("/", 1)
        if len(parts) == 2:
            try:
                result_bytes = await storage.read_bytes(parts[1])
            except Exception as e:
                log_json(
                    logger,
                    logging.WARNING,
                    "Could not read gcs_uri output directly",
                    job_id=job.id,
                    gcs_uri=gcs_output_uri,
                    error=str(e),
                )

    elif output_file_name:
        # The Gemini Developer API (the mode this service uses) returns results
        # as a Gemini Files API reference, not a GCS URI — must be downloaded
        # via the Files API, not our own storage service.
        output_ref = output_file_name
        try:
            result_bytes = client.files.download(file=output_file_name)
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "Failed to download batch OCR output file",
                job_id=job.id,
                file_name=output_file_name,
                error=str(exc),
            )

    if result_bytes is None:
        log_json(
            logger,
            logging.ERROR,
            "Batch OCR job succeeded but produced no retrievable output",
            job_id=job.id,
        )
        job.status = "failed"
        job.error = "Batch OCR job succeeded but produced no retrievable output"
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()
        return

    # Fetch current retry counts once so per-page failures below can decide
    # whether to retry again or give up gracefully (avoids an N+1 query).
    retry_count_rows = (
        await session.execute(
            select(Page.id, Page.retry_count).where(Page.id.in_(job.page_ids))
        )
    ).fetchall()
    retry_counts = {pid: rc for pid, rc in retry_count_rows}

    # Parse JSONL results
    lines = result_bytes.decode("utf-8").strip().split("\n")
    succeeded_pages = 0

    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            custom_id = (
                item.get("custom_id") or item.get("customId") or item.get("key") or ""
            )
            if not custom_id.startswith("page_"):
                continue

            page_id = int(custom_id.replace("page_", ""))
            response = item.get("response") or item
            error = item.get("error") or (
                item.get("response", {}).get("error")
                if isinstance(item.get("response"), dict)
                else None
            )

            if error:
                err_msg = str(error)[:500]
                log_json(
                    logger,
                    logging.WARNING,
                    "Batch OCR page returned error from Gemini API",
                    job_id=job.id,
                    book_id=job.book_id,
                    page_id=page_id,
                    error=err_msg,
                )
                skipped = await _record_page_ocr_failure(
                    session,
                    page_id,
                    retry_counts.get(page_id, 0),
                    ocr_max_retry_count,
                    err_msg,
                )
                if skipped:
                    succeeded_pages += 1
            else:
                prompt_feedback = response.get("promptFeedback") or {}
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    err_msg = f"Prompt blocked: {block_reason}"
                    log_json(
                        logger,
                        logging.WARNING,
                        "Batch OCR page prompt was blocked by Gemini API",
                        job_id=job.id,
                        book_id=job.book_id,
                        page_id=page_id,
                        block_reason=block_reason,
                    )
                    skipped = await _record_page_ocr_failure(
                        session,
                        page_id,
                        retry_counts.get(page_id, 0),
                        ocr_max_retry_count,
                        err_msg,
                    )
                    if skipped:
                        succeeded_pages += 1
                    continue

                # Extract text from response candidates
                candidates = response.get("candidates", [])
                text = ""
                finish_reason = None
                if candidates:
                    finish_reason = candidates[0].get("finishReason")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")

                if finish_reason in (
                    "SAFETY",
                    "RECITATION",
                    "BLOCKLIST",
                    "PROHIBITED_CONTENT",
                    "SPII",
                    "MALICIOUS",
                ):
                    err_msg = f"Candidate blocked: {finish_reason}"
                    log_json(
                        logger,
                        logging.WARNING,
                        "Batch OCR page candidate blocked by safety filter",
                        job_id=job.id,
                        book_id=job.book_id,
                        page_id=page_id,
                        finish_reason=finish_reason,
                    )
                    skipped = await _record_page_ocr_failure(
                        session,
                        page_id,
                        retry_counts.get(page_id, 0),
                        ocr_max_retry_count,
                        err_msg,
                    )
                    if skipped:
                        succeeded_pages += 1
                    continue

                cleaned_text = clean_uyghur_text(text or "")

                if is_degenerate_ocr_output(cleaned_text):
                    skipped = await _record_page_ocr_failure(
                        session,
                        page_id,
                        retry_counts.get(page_id, 0),
                        ocr_max_retry_count,
                        f"degenerate/repetitive OCR output ({len(cleaned_text)} chars)",
                    )
                    if skipped:
                        succeeded_pages += 1
                    continue

                is_toc = is_toc_page(cleaned_text) if cleaned_text.strip() else False

                await session.execute(
                    update(Page)
                    .where(Page.id == page_id)
                    .values(
                        text=cleaned_text,
                        is_toc=is_toc,
                        ocr_milestone="succeeded",
                        error=None,
                        last_updated=func.now(),
                    )
                )
                session.add(
                    PipelineEvent(
                        page_id=page_id,
                        event_type="ocr_succeeded",
                        payload=make_pipeline_event_payload(
                            extra_fields={"batch": True}
                        ),
                    )
                )
                succeeded_pages += 1

        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "Error parsing batch OCR result line",
                job_id=job.id,
                error=str(exc),
            )

    # Mark batch job succeeded
    job.status = "succeeded"
    job.processed_pages = succeeded_pages
    job.completed_at = datetime.now(timezone.utc)
    job.gcs_output_uri = output_ref
    await session.commit()

    # Update book milestone
    await BookMilestoneService.update_book_milestone_for_step(
        session, job.book_id, "ocr"
    )
    await session.commit()

    log_json(
        logger,
        logging.INFO,
        "Batch OCR job completed & ingested",
        job_id=job.id,
        book_id=job.book_id,
        succeeded_pages=succeeded_pages,
        total_pages=job.total_pages,
    )
