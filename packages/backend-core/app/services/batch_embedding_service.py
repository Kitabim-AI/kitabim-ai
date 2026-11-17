"""
Batch Embedding Service — Handles Gemini Batch API embedding request formatting, GCS staging,
batch submission, and status polling/result ingestion.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from google import genai
from google.genai import types
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    PAGE_MILESTONE_COMPLETE,
)
from app.db.models import BatchEmbeddingJob, Book, Chunk, Page, PipelineEvent
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.services.cache_service import cache_service
from app.services.storage_service import storage
from app.utils.observability import log_json, make_pipeline_event_payload

logger = logging.getLogger("app.services.batch_embedding_service")


def _get_genai_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def _get_embedding_dimensionality(model_name: str) -> int:
    return 3072 if "gemini-embedding-2" in model_name else 768


async def _get_active_in_flight_chunk_ids_for_book(
    session: AsyncSession,
    book_id: str,
    *,
    exclude_job_id: Optional[str] = None,
) -> tuple[bool, set[int]]:
    """Return `(has_active_job_for_book, in_flight_chunk_ids)` across active `BatchEmbeddingJob` rows."""
    stmt = select(BatchEmbeddingJob).where(
        BatchEmbeddingJob.status.in_(["submitting", "submitted", "running"])
    )
    if exclude_job_id is not None:
        stmt = stmt.where(BatchEmbeddingJob.id != exclude_job_id)

    res = await session.execute(stmt)
    scalars = res.scalars() if hasattr(res, "scalars") else None
    rows = (
        list(scalars.all()) if scalars is not None and hasattr(scalars, "all") else []
    )
    has_active = False
    chunk_ids: set[int] = set()
    for row in rows:
        b_ids = getattr(row, "book_ids", None) or []
        if isinstance(b_ids, list) and book_id in b_ids:
            has_active = True
            for cid in getattr(row, "chunk_ids", None) or []:
                if isinstance(cid, int):
                    chunk_ids.add(cid)
    return has_active, chunk_ids


async def _finalize_book_after_batch_job_failure(
    session: AsyncSession,
    book_id: str,
    *,
    exclude_job_id: Optional[str] = None,
) -> None:
    """Mark `Book.embedding_milestone = 'failed'` only when no other sub-batch for `book_id` is still active."""
    has_active, _ = await _get_active_in_flight_chunk_ids_for_book(
        session, book_id, exclude_job_id=exclude_job_id
    )
    if has_active:
        return
    await session.execute(
        update(Book)
        .where(Book.id == book_id)
        .values(
            embedding_milestone=BOOK_MILESTONE_FAILED,
            embedding_retry_count=Book.embedding_retry_count + 1,
            embedding_claimed_at=None,
        )
    )


async def submit_batch_embedding_job_for_book(
    session: AsyncSession,
    book_id: str,
) -> List[BatchEmbeddingJob]:
    """
    Book-scoped Gemini Batch API submission for all unembedded chunks in `book_id`.
    Deduplicates JSONL requests by `Chunk.text_hash` and slices at `embed_batch_max_chunks_per_job` (default 5000).
    """
    if not book_id:
        return []

    config_repo = SystemConfigsRepository(session)
    gemini_embedding_model = await config_repo.get_value("embed_gemini_model")
    if not gemini_embedding_model:
        raise RuntimeError("system_config 'embed_gemini_model' is not set")

    max_chunks_per_job = int(
        await config_repo.get_value("embed_batch_max_chunks_per_job", "5000")
    )

    model = (
        gemini_embedding_model.replace("models/", "", 1)
        if gemini_embedding_model.startswith("models/")
        else gemini_embedding_model
    )
    output_dim = _get_embedding_dimensionality(model)

    result = await session.execute(
        select(Chunk)
        .where(
            Chunk.book_id == book_id,
            Chunk.embedding.is_(None),
        )
        .order_by(Chunk.id)
    )
    unembedded_chunks = list(result.scalars().all())

    if not unembedded_chunks:
        await session.execute(
            update(Page)
            .where(
                Page.book_id == book_id,
                Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
            )
            .values(
                embedding_milestone="succeeded",
                is_indexed=True,
                last_updated=func.now(),
            )
        )
        await session.execute(
            update(Book)
            .where(Book.id == book_id)
            .values(
                embedding_milestone=BOOK_MILESTONE_COMPLETE,
                embedding_retry_count=0,
                embedding_claimed_at=None,
            )
        )
        await session.commit()
        try:
            await cache_service.delete_pattern(f"rag:search:{book_id}:*")
        except Exception:
            pass
        return []

    (
        has_active_before,
        in_flight_chunk_ids,
    ) = await _get_active_in_flight_chunk_ids_for_book(session, book_id)
    if in_flight_chunk_ids:
        unembedded_chunks = [
            ch for ch in unembedded_chunks if ch.id not in in_flight_chunk_ids
        ]
        if not unembedded_chunks:
            return []

    # Deduplicate requests by text_hash while tracking all unembedded chunk IDs
    representative_chunks: List[Chunk] = []
    seen_hashes: set[str] = set()
    for ch in unembedded_chunks:
        t_hash = getattr(ch, "text_hash", None)
        if t_hash:
            if t_hash in seen_hashes:
                continue
            seen_hashes.add(t_hash)
        representative_chunks.append(ch)

    sub_batches: List[List[Chunk]] = [
        representative_chunks[i : i + max_chunks_per_job]
        for i in range(0, len(representative_chunks), max_chunks_per_job)
    ]

    created_jobs: List[BatchEmbeddingJob] = []
    any_failed = False
    any_submitted = False

    for batch_idx, batch_chunks in enumerate(sub_batches):
        job_id = str(uuid.uuid4())
        jsonl_lines: List[str] = []
        for chunk in batch_chunks:
            request_entry = {
                "custom_id": f"chunk_{chunk.id}",
                "request": {
                    "content": {
                        "parts": [{"text": chunk.text}],
                    },
                    "output_dimensionality": output_dim,
                },
            }
            jsonl_lines.append(json.dumps(request_entry))

        jsonl_content = "\n".join(jsonl_lines).encode("utf-8")
        remote_input_path = f"batch_embedding/inputs/{job_id}.jsonl"
        gcs_input_uri: Optional[str] = None

        gemini_batch_id: Optional[str] = None
        status = "submitted"
        err_msg: Optional[str] = None

        try:
            await storage.upload_bytes(jsonl_content, remote_input_path)
            gcs_input_uri = storage.get_gs_uri(remote_input_path)

            client = _get_genai_client()
            uploaded_file = client.files.upload(
                file=io.BytesIO(jsonl_content),
                config=types.UploadFileConfig(
                    display_name=f"batch_embedding_{job_id}", mime_type="jsonl"
                ),
            )
            batch_job = client.batches.create_embeddings(
                model=model,
                src=types.EmbeddingsBatchJobSource(file_name=uploaded_file.name),
            )
            gemini_batch_id = batch_job.name
            any_submitted = True
            log_json(
                logger,
                logging.INFO,
                "Submitted book-scoped Gemini Batch Embedding job",
                job_id=job_id,
                book_id=book_id,
                gemini_batch_id=gemini_batch_id,
                chunk_count=len(batch_chunks),
            )
        except Exception as exc:
            err_msg = str(exc)[:500]
            log_json(
                logger,
                logging.ERROR,
                "Failed to submit book-scoped Gemini Batch Embedding job",
                job_id=job_id,
                book_id=book_id,
                error=err_msg,
            )
            status = "failed"
            any_failed = True

        batch_hashes = {
            getattr(c, "text_hash", None)
            for c in batch_chunks
            if getattr(c, "text_hash", None)
        }
        batch_rep_ids = {c.id for c in batch_chunks}
        slice_chunk_ids = [
            c.id
            for c in unembedded_chunks
            if c.id in batch_rep_ids
            or (
                getattr(c, "text_hash", None)
                and getattr(c, "text_hash", None) in batch_hashes
            )
        ]

        batch_job_row = BatchEmbeddingJob(
            id=job_id,
            gemini_batch_id=gemini_batch_id,
            book_ids=[book_id],
            page_ids=[],
            chunk_ids=slice_chunk_ids,
            status=status,
            gcs_input_uri=gcs_input_uri,
            total_chunks=len(slice_chunk_ids),
            error=err_msg,
            submitted_at=datetime.now(timezone.utc) if status == "submitted" else None,
        )
        session.add(batch_job_row)
        created_jobs.append(batch_job_row)

    if any_failed and not any_submitted and not has_active_before:
        await session.execute(
            update(Book)
            .where(Book.id == book_id)
            .values(
                embedding_milestone=BOOK_MILESTONE_FAILED,
                embedding_retry_count=Book.embedding_retry_count + 1,
                embedding_claimed_at=None,
            )
        )
    await session.commit()
    return created_jobs


async def submit_batch_embedding_job(
    session: AsyncSession,
    page_ids_or_book_id: Union[List[int], str],
) -> List[BatchEmbeddingJob]:
    """
    Builds Gemini Batch API JSONL embedding dataset for a book (str) or claimed pages (list[int]),
    uploads to GCS and Gemini Files API, submits batch job(s) to Gemini API,
    and creates DB tracking record(s).
    """
    if isinstance(page_ids_or_book_id, str):
        return await submit_batch_embedding_job_for_book(session, page_ids_or_book_id)

    page_ids = page_ids_or_book_id
    if not page_ids:
        return []

    config_repo = SystemConfigsRepository(session)
    gemini_embedding_model = await config_repo.get_value("embed_gemini_model")
    if not gemini_embedding_model:
        raise RuntimeError("system_config 'embed_gemini_model' is not set")

    max_chunks_per_job = int(
        await config_repo.get_value("embed_batch_max_chunks_per_job", "5000")
    )

    model = (
        gemini_embedding_model.replace("models/", "", 1)
        if gemini_embedding_model.startswith("models/")
        else gemini_embedding_model
    )
    output_dim = _get_embedding_dimensionality(model)

    # Find all unembedded chunks belonging to the claimed pages
    stmt = (
        select(Chunk, Page.id.label("page_id"))
        .join(
            Page,
            (Chunk.book_id == Page.book_id) & (Chunk.page_number == Page.page_number),
        )
        .where(
            Page.id.in_(page_ids),
            Chunk.embedding.is_(None),
        )
        .order_by(Chunk.id)
    )
    result = await session.execute(stmt)
    rows = result.fetchall()

    if not rows:
        # No unembedded chunks found — mark all pages succeeded immediately
        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(
                embedding_milestone="succeeded",
                is_indexed=True,
                last_updated=func.now(),
            )
        )
        for p_id in page_ids:
            session.add(
                PipelineEvent(
                    page_id=p_id,
                    event_type="embedding_succeeded",
                    payload=make_pipeline_event_payload(duration_ms=0),
                )
            )
        await session.commit()

        # Update book milestones for all distinct books
        page_res = await session.execute(
            select(Page.book_id).where(Page.id.in_(page_ids)).distinct()
        )
        distinct_books = [r[0] for r in page_res.fetchall()]
        for book_id in distinct_books:
            await BookMilestoneService.update_book_milestone_for_step(
                session, book_id, "embedding"
            )
        await session.commit()
        return []

    chunk_page_map = {r[0].id: r[1] for r in rows}

    # Group unembedded chunks by page_id to keep page boundaries intact
    page_chunks_map: Dict[int, List[Chunk]] = {}
    for chunk, page_id in rows:
        if page_id not in page_chunks_map:
            page_chunks_map[page_id] = []
        page_chunks_map[page_id].append(chunk)

    sub_batches: List[List[Chunk]] = []
    current_batch: List[Chunk] = []

    for p_id, p_chunks in page_chunks_map.items():
        if current_batch and (len(current_batch) + len(p_chunks) > max_chunks_per_job):
            sub_batches.append(current_batch)
            current_batch = []
        current_batch.extend(p_chunks)

    if current_batch:
        sub_batches.append(current_batch)

    created_jobs: List[BatchEmbeddingJob] = []

    for batch_chunks in sub_batches:
        job_id = str(uuid.uuid4())

        # Build JSONL payload entries
        jsonl_lines: List[str] = []
        for chunk in batch_chunks:
            request_entry = {
                "custom_id": f"chunk_{chunk.id}",
                "request": {
                    "content": {
                        "parts": [{"text": chunk.text}],
                    },
                    "output_dimensionality": output_dim,
                },
            }
            jsonl_lines.append(json.dumps(request_entry))

        jsonl_content = "\n".join(jsonl_lines).encode("utf-8")

        # Upload JSONL payload to audit storage
        remote_input_path = f"batch_embedding/inputs/{job_id}.jsonl"
        await storage.upload_bytes(jsonl_content, remote_input_path)
        gcs_input_uri = storage.get_gs_uri(remote_input_path)

        gemini_batch_id: Optional[str] = None
        status = "submitted"
        err_msg: Optional[str] = None

        try:
            client = _get_genai_client()
            uploaded_file = client.files.upload(
                file=io.BytesIO(jsonl_content),
                config=types.UploadFileConfig(
                    display_name=f"batch_embedding_{job_id}", mime_type="jsonl"
                ),
            )
            batch_job = client.batches.create_embeddings(
                model=model,
                src=types.EmbeddingsBatchJobSource(file_name=uploaded_file.name),
            )
            gemini_batch_id = batch_job.name
            log_json(
                logger,
                logging.INFO,
                "Submitted Gemini Batch Embedding job",
                job_id=job_id,
                gemini_batch_id=gemini_batch_id,
                chunk_count=len(batch_chunks),
            )
        except Exception as exc:
            err_msg = str(exc)[:500]
            log_json(
                logger,
                logging.ERROR,
                "Failed to submit Gemini Batch Embedding job",
                job_id=job_id,
                error=err_msg,
            )
            status = "failed"

        slice_book_ids = list(set(c.book_id for c in batch_chunks))
        slice_page_ids = list(
            set(chunk_page_map[c.id] for c in batch_chunks if c.id in chunk_page_map)
        )
        slice_chunk_ids = [c.id for c in batch_chunks]

        batch_job_row = BatchEmbeddingJob(
            id=job_id,
            gemini_batch_id=gemini_batch_id,
            book_ids=slice_book_ids,
            page_ids=slice_page_ids,
            chunk_ids=slice_chunk_ids,
            status=status,
            gcs_input_uri=gcs_input_uri,
            total_chunks=len(slice_chunk_ids),
            error=err_msg,
            submitted_at=datetime.now(timezone.utc) if status == "submitted" else None,
        )
        session.add(batch_job_row)
        created_jobs.append(batch_job_row)

        if status == "failed":
            await session.execute(
                update(Page)
                .where(Page.id.in_(slice_page_ids))
                .values(
                    embedding_milestone="failed",
                    retry_count=Page.retry_count + 1,
                    error=f"Batch embedding submission failed: {err_msg}",
                    last_updated=func.now(),
                )
            )
            await session.commit()
            for book_id in slice_book_ids:
                await BookMilestoneService.update_book_milestone_for_step(
                    session, book_id, "embedding"
                )
            await session.commit()
        else:
            await session.commit()

    return created_jobs


async def poll_and_process_batch_embedding_jobs(session: AsyncSession) -> int:
    """
    Polls active batch embedding jobs, retrieves status from Gemini API,
    and ingests completed embedding vectors or records failures.
    """
    config_repo = SystemConfigsRepository(session)
    timeout_hours = float(
        await config_repo.get_value("embed_batch_timeout_hours", "24")
    )
    max_retries = int(await config_repo.get_value("embed_batch_max_retry_count", "3"))

    # Query active jobs
    result = await session.execute(
        select(BatchEmbeddingJob).where(
            BatchEmbeddingJob.status.in_(["submitting", "submitted", "running"])
        )
    )
    active_jobs = list(result.scalars().all())

    if not active_jobs:
        return 0

    processed_count = 0
    client = _get_genai_client()

    for job in active_jobs:
        now = datetime.now(timezone.utc)

        # 1. Timeout Check
        if (
            job.created_at
            and (now - job.created_at).total_seconds() > timeout_hours * 3600
        ):
            log_json(
                logger,
                logging.WARNING,
                "Batch Embedding job timed out",
                job_id=job.id,
                gemini_batch_id=job.gemini_batch_id,
            )
            job.status = "failed"
            job.error = f"Batch embedding job timed out after {timeout_hours} hours"
            job.completed_at = now

            if job.page_ids:
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(job.page_ids))
                    .values(
                        embedding_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        error="Batch embedding job timed out",
                        last_updated=func.now(),
                    )
                )
                await session.commit()
                for book_id in job.book_ids:
                    await BookMilestoneService.update_book_milestone_for_step(
                        session, book_id, "embedding"
                    )
                await session.commit()
            else:
                for book_id in job.book_ids:
                    await _finalize_book_after_batch_job_failure(
                        session, book_id, exclude_job_id=job.id
                    )
                await session.commit()
            processed_count += 1
            continue

        if not job.gemini_batch_id:
            continue

        # 2. Query Gemini Batch API Status
        try:
            batch_job_info = client.batches.get(name=job.gemini_batch_id)
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "Failed to get Gemini Batch Embedding job status",
                job_id=job.id,
                gemini_batch_id=job.gemini_batch_id,
                error=str(exc),
            )
            continue

        state_str = str(getattr(batch_job_info, "state", ""))
        log_json(
            logger,
            logging.INFO,
            "Polled Gemini Batch Embedding job",
            job_id=job.id,
            state=state_str,
        )

        if "RUNNING" in state_str:
            if job.status != "running":
                job.status = "running"
                await session.commit()
            continue

        if "SUCCEEDED" in state_str:
            dest = getattr(batch_job_info, "dest", None)
            gcs_output_uri = getattr(dest, "gcs_uri", None) if dest else None
            output_file_name = getattr(dest, "file_name", None) if dest else None

            if not output_file_name and isinstance(dest, str):
                output_file_name = dest
            if (
                not output_file_name
                and hasattr(batch_job_info, "output_file")
                and batch_job_info.output_file
            ):
                output_file_name = str(batch_job_info.output_file)

            jsonl_content: Optional[bytes] = None
            if output_file_name:
                try:
                    jsonl_content = client.files.download(file=output_file_name)
                except Exception as exc:
                    log_json(
                        logger,
                        logging.ERROR,
                        "Failed downloading Batch Embedding results file",
                        job_id=job.id,
                        output_file=output_file_name,
                        error=str(exc),
                    )

            target_gcs_uri = gcs_output_uri or job.gcs_output_uri
            if not jsonl_content and target_gcs_uri:
                try:
                    bucket_name = settings.gcs_data_bucket or ""
                    relative_path = target_gcs_uri.replace(f"gs://{bucket_name}/", "")
                    if uri_parts := relative_path.split("/", 1):
                        if len(uri_parts) == 2 and target_gcs_uri.startswith("gs://"):
                            relative_path = uri_parts[1]
                    jsonl_content = await storage.read_bytes(relative_path)
                except Exception as exc:
                    log_json(
                        logger,
                        logging.ERROR,
                        "Failed downloading Batch Embedding GCS output file",
                        job_id=job.id,
                        error=str(exc),
                    )

            if not jsonl_content:
                job.status = "failed"
                job.error = "Batch embedding completed but output payload could not be downloaded"
                job.completed_at = now
                if job.page_ids:
                    await session.execute(
                        update(Page)
                        .where(Page.id.in_(job.page_ids))
                        .values(
                            embedding_milestone="failed",
                            retry_count=Page.retry_count + 1,
                            error="Batch embedding output download failed",
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()
                    for book_id in job.book_ids:
                        await BookMilestoneService.update_book_milestone_for_step(
                            session, book_id, "embedding"
                        )
                    await session.commit()
                else:
                    for book_id in job.book_ids:
                        await session.execute(
                            update(Book)
                            .where(Book.id == book_id)
                            .values(
                                embedding_milestone=BOOK_MILESTONE_FAILED,
                                embedding_retry_count=Book.embedding_retry_count + 1,
                                embedding_claimed_at=None,
                            )
                        )
                    await session.commit()
                processed_count += 1
                continue

            # Parse JSONL results
            lines = jsonl_content.decode("utf-8").strip().split("\n")
            succeeded_vectors = {}
            failed_chunk_ids = set()

            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    custom_id = entry.get("custom_id", "")
                    if not custom_id.startswith("chunk_"):
                        continue
                    chunk_id = int(custom_id.replace("chunk_", ""))

                    if "error" in entry:
                        failed_chunk_ids.add(chunk_id)
                        continue

                    response = entry.get("response", {})
                    # Response can be direct embedding or wrapper
                    embedding_obj = response.get("embedding", {}) or response
                    values = embedding_obj.get("values")
                    if values and isinstance(values, list):
                        succeeded_vectors[chunk_id] = values
                    else:
                        failed_chunk_ids.add(chunk_id)
                except Exception as exc:
                    logger.warning("Error parsing embedding JSONL line: %s", exc)

            # 1. Update succeeded chunks
            for chunk_id, vector in succeeded_vectors.items():
                await session.execute(
                    update(Chunk).where(Chunk.id == chunk_id).values(embedding=vector)
                )

            if not job.page_ids:
                # Book-scoped job completion path: propagate vectors across duplicate text_hash rows
                if succeeded_vectors:
                    hash_rows = await session.execute(
                        select(Chunk.id, Chunk.book_id, Chunk.text_hash).where(
                            Chunk.id.in_(list(succeeded_vectors.keys())),
                            Chunk.text_hash.isnot(None),
                        )
                    )
                    for rep_id, rep_book_id, rep_hash in hash_rows.fetchall():
                        vec = succeeded_vectors.get(rep_id)
                        if vec and rep_hash:
                            await session.execute(
                                update(Chunk)
                                .where(
                                    Chunk.book_id == rep_book_id,
                                    Chunk.text_hash == rep_hash,
                                    Chunk.embedding.is_(None),
                                )
                                .values(embedding=vec)
                            )

                job.status = "succeeded"
                job.processed_chunks = len(succeeded_vectors)
                job.completed_at = now
                await session.commit()

                for book_id in job.book_ids:
                    (
                        has_other_active,
                        _,
                    ) = await _get_active_in_flight_chunk_ids_for_book(
                        session, book_id, exclude_job_id=job.id
                    )
                    if has_other_active:
                        continue

                    rem_res = await session.execute(
                        select(func.count(Chunk.id)).where(
                            Chunk.book_id == book_id,
                            Chunk.embedding.is_(None),
                        )
                    )
                    rem_unembedded = int(rem_res.scalar() or 0)
                    if rem_unembedded == 0 and not failed_chunk_ids:
                        await session.execute(
                            update(Page)
                            .where(
                                Page.book_id == book_id,
                                Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
                            )
                            .values(
                                embedding_milestone="succeeded",
                                is_indexed=True,
                                last_updated=func.now(),
                            )
                        )
                        await session.execute(
                            update(Book)
                            .where(Book.id == book_id)
                            .values(
                                embedding_milestone=BOOK_MILESTONE_COMPLETE,
                                embedding_retry_count=0,
                                embedding_claimed_at=None,
                            )
                        )
                        try:
                            await cache_service.delete_pattern(
                                f"rag:search:{book_id}:*"
                            )
                        except Exception:
                            pass
                    else:
                        await session.execute(
                            update(Book)
                            .where(Book.id == book_id)
                            .values(
                                embedding_milestone=BOOK_MILESTONE_FAILED,
                                embedding_retry_count=Book.embedding_retry_count + 1,
                                embedding_claimed_at=None,
                            )
                        )
                await session.commit()
                processed_count += 1
                continue

            # Map chunks to pages (legacy page-scoped path)
            chunk_rows = await session.execute(
                select(Chunk.id, Chunk.book_id, Chunk.page_number).where(
                    Chunk.id.in_(job.chunk_ids)
                )
            )
            c_info = chunk_rows.fetchall()

            page_rows = await session.execute(
                select(Page.id, Page.book_id, Page.page_number, Page.retry_count).where(
                    Page.id.in_(job.page_ids)
                )
            )
            pages_list = page_rows.fetchall()

            failed_pages = set()
            succeeded_pages = set()

            for p_id, b_id, p_num, r_count in pages_list:
                # Find all chunks for this page in job
                p_chunks = [c[0] for c in c_info if c[1] == b_id and c[2] == p_num]
                p_failed = [c for c in p_chunks if c in failed_chunk_ids]

                if p_failed:
                    if r_count + 1 >= max_retries:
                        # Exceeded retries — mark page succeeded anyway to avoid blocking
                        succeeded_pages.add(p_id)
                    else:
                        failed_pages.add(p_id)
                else:
                    succeeded_pages.add(p_id)

            if succeeded_pages:
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(list(succeeded_pages)))
                    .values(
                        embedding_milestone="succeeded",
                        is_indexed=True,
                        last_updated=func.now(),
                    )
                )
                for p_id in succeeded_pages:
                    session.add(
                        PipelineEvent(
                            page_id=p_id,
                            event_type="embedding_succeeded",
                            payload=make_pipeline_event_payload(duration_ms=0),
                        )
                    )

            if failed_pages:
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(list(failed_pages)))
                    .values(
                        embedding_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        error="One or more chunks failed embedding generation",
                        last_updated=func.now(),
                    )
                )

            job.status = "succeeded"
            job.processed_chunks = len(succeeded_vectors)
            job.completed_at = now
            await session.commit()

            for book_id in job.book_ids:
                await BookMilestoneService.update_book_milestone_for_step(
                    session, book_id, "embedding"
                )
            await session.commit()
            processed_count += 1

        elif "FAILED" in state_str or "CANCELLED" in state_str:
            job.status = "failed"
            job.error = f"Gemini batch job failed with state {state_str}"
            job.completed_at = now

            if job.page_ids:
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(job.page_ids))
                    .values(
                        embedding_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        error=f"Gemini batch job failed ({state_str})",
                        last_updated=func.now(),
                    )
                )
                await session.commit()

                for book_id in job.book_ids:
                    await BookMilestoneService.update_book_milestone_for_step(
                        session, book_id, "embedding"
                    )
                await session.commit()
            else:
                for book_id in job.book_ids:
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            embedding_milestone=BOOK_MILESTONE_FAILED,
                            embedding_retry_count=Book.embedding_retry_count + 1,
                            embedding_claimed_at=None,
                        )
                    )
                await session.commit()
            processed_count += 1

    return processed_count
