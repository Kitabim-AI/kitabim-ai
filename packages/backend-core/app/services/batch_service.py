"""Batch service for managing Gemini Batch API workflows"""
from __future__ import annotations

import json
import logging
import io
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, update, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Page, Chunk, BatchJob, BatchRequest, Book
from app.db.repositories.batch_jobs import BatchJobsRepository, BatchRequestsRepository
from app.db.repositories.books import BooksRepository
from app.services.gemini_batch_client import GeminiBatchClient
from app.services.storage_service import storage
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

class BatchService:
    """
    Manages the lifecycle of Gemini Batch jobs:
    1. Collection of pending work
    2. JSONL generation and upload
    3. Job submission
    4. Result polling and processing
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.batch_client = GeminiBatchClient()
        self.jobs_repo = BatchJobsRepository(session)
        self.requests_repo = BatchRequestsRepository(session)
        self.books_repo = BooksRepository(session)

    async def submit_ocr_batch(self, limit: int = 100) -> Optional[UUID]:
        """
        Collects pending OCR pages and submits them as a batch job.
        """
        from app.core.config import settings
        import os
        import tempfile
        import asyncio
        from pathlib import Path

        # 1. Collect pages with 'pending' status
        stmt = (
            select(Page)
            .where(Page.status == "pending")
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        pages = result.scalars().all()

        if not pages:
            return None

        # 1.5. Group pages by book and upload PDFs to Gemini File API
        # AI Studio API requires files to be in its File API, not gs://
        book_ids = {p.book_id for p in pages}
        book_gemini_uris = {}
        uploaded_gemini_files = [] # Track for cleanup
        
        for book_id in book_ids:
            try:
                # Need to run blocking storage/gemini operations, but keeping it simple
                local_pdf_path = Path(tempfile.gettempdir()) / f"{book_id}.pdf"
                log_json(logger, logging.INFO, "Downloading PDF for Gemini File API", book_id=book_id)
                await storage.download_file(f"uploads/{book_id}.pdf", local_pdf_path)
                
                # Upload to Gemini File API
                log_json(logger, logging.INFO, "Uploading PDF to Gemini File API", book_id=book_id)
                # Run sync client operation in executor to avoid blocking async loop
                loop = asyncio.get_event_loop()
                from google.genai import types
                f_res = await loop.run_in_executor(
                    None,
                    lambda: self.batch_client.client.files.upload(
                        file=str(local_pdf_path),
                        config=types.UploadFileConfig(mime_type="application/pdf")
                    )
                )
                book_gemini_uris[book_id] = f_res.uri
                uploaded_gemini_files.append(f_res.name)
                
                if local_pdf_path.exists():
                    os.remove(local_pdf_path)
            except Exception as e:
                log_json(logger, logging.ERROR, "Failed to prep PDF for Gemini API", book_id=book_id, error=str(e))
                # Will skip pages for this book next
                
        jsonl_lines = []
        request_mappings = []

        # 2. Generate JSONL lines
        for page in pages:
            if page.book_id not in book_gemini_uris:
                continue # Skip if PDF upload failed
                
            custom_id = f"ocr_{page.book_id}_{page.page_number}"
            
            # Request structure for Gemini API using the File API URI
            request = {
                "custom_id": custom_id,
                "request": {
                    "contents": [{
                        "parts": [
                            {"file_data": {"mime_type": "application/pdf", "file_uri": book_gemini_uris[page.book_id]}},
                            {"text": f"Extract and OCR all text from page {page.page_number} of this document. Return ONLY the text content. Maintain original formatting as much as possible."}
                        ]
                    }]
                }
            }
            jsonl_lines.append(json.dumps(request))
            request_mappings.append({
                "book_id": page.book_id,
                "page_number": page.page_number,
                "request_id": custom_id,
                "status": "pending"
            })
            
        if not jsonl_lines:
            # If all PDF uploads failed, clean up and exit
            for f_name in uploaded_gemini_files:
                try: self.batch_client.delete_file(f_name)
                except: pass
            return None

        # 3. Write to local file and submit to Gemini
        fd, input_path = tempfile.mkstemp(suffix=".jsonl")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("\n".join(jsonl_lines) + "\n")
            
            remote_job_id, file_api_name = self.batch_client.create_batch_job(
                input_path, 
                model=settings.gemini_model_name
            )
        finally:
            if os.path.exists(input_path):
                os.remove(input_path)

        # 4. Create job records
        # Store file_api_name in input_file_uri so we can delete it later
        batch_job = await self.jobs_repo.create_job("ocr", len(pages), file_api_name)
        
        for mapping in request_mappings:
            mapping["batch_job_id"] = batch_job.id
        await self.requests_repo.create_requests(request_mappings)

        # 5. Mark pages as 'ocr_processing'
        for page in pages:
            page.status = "ocr_processing"
            page.updated_by = "batch_service"
            
        await self.session.flush()

        # 6. Finalize submission in DB
        try:
            await self.jobs_repo.update_job_status(batch_job.id, "submitted", remote_job_id=remote_job_id)
            await self.session.commit()
            log_json(logger, logging.INFO, "OCR Batch Job submitted", 
                     job_id=str(batch_job.id), remote_id=remote_job_id, count=len(pages))
            return batch_job.id
        except Exception as e:
            await self.jobs_repo.update_job_status(batch_job.id, "failed", error_message=str(e))
            await self.session.commit()
            raise

    async def submit_embedding_batch(self, limit: int = 100) -> Optional[UUID]:
        """
        Collects chunks with NULL embeddings and submits them as a batch job.
        """
        from app.core.config import settings
        import os
        import tempfile

        # 1. Collect chunks where embedding IS NULL
        stmt = (
            select(Chunk)
            .where(Chunk.embedding == None)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()

        if not chunks:
            return None

        jsonl_lines = []
        request_mappings = []

        # 2. Generate JSONL lines
        for chunk in chunks:
            # We use the internal chunk ID as the custom_id for easy mapping back
            custom_id = f"embed_{chunk.id}"
            
            # Since create_embeddings doesn't wrap the request exactly like generateContent
            # We map it to what the SDK might expect for embedContent (with "request" wrapper)
            request = {
                "custom_id": custom_id,
                "request": {
                    "content": {
                        "parts": [{"text": chunk.text}]
                    }
                }
            }
            jsonl_lines.append(json.dumps(request))
            request_mappings.append({
                "book_id": chunk.book_id,
                "page_number": chunk.page_number,
                "request_id": custom_id,
                "status": "pending"
            })

        # 3. Write to local file and submit
        fd, input_path = tempfile.mkstemp(suffix=".jsonl")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("\n".join(jsonl_lines) + "\n")
            
            remote_job_id, file_api_name = self.batch_client.create_embedding_batch_job(
                input_path,
                model=settings.gemini_embedding_model
            )
        finally:
            if os.path.exists(input_path):
                os.remove(input_path)

        # 4. Create job records
        batch_job = await self.jobs_repo.create_job("embedding", len(chunks), file_api_name)
        
        for mapping in request_mappings:
            mapping["batch_job_id"] = batch_job.id
        await self.requests_repo.create_requests(request_mappings)

        await self.session.flush()

        # 5. Finalize submission
        try:
            await self.jobs_repo.update_job_status(batch_job.id, "submitted", remote_job_id=remote_job_id)
            await self.session.commit()
            log_json(logger, logging.INFO, "Embedding Batch Job submitted", 
                     job_id=str(batch_job.id), remote_id=remote_job_id, count=len(chunks))
            return batch_job.id
        except Exception as e:
            await self.jobs_repo.update_job_status(batch_job.id, "failed", error_message=str(e))
            await self.session.commit()
            raise

    async def poll_and_process_jobs(self):
        """
        Main entry point for background polling.
        Checks status of submitted jobs and processes results if completed.
        Enforces that the job is using the current target model based on .env
        """
        from app.core.config import settings

        active_jobs = await self.jobs_repo.get_active_jobs()
        log_json(logger, logging.DEBUG, "Polling active batch jobs", count=len(active_jobs))
        
        for job in active_jobs:
            if not job.remote_job_id:
                continue

            try:
                # 1. Fetch remote job details
                remote_job = self.batch_client.get_job(job.remote_job_id)
                current_status = str(remote_job.state).split(".")[-1].replace("JOB_STATE_", "")
                
                # 2. Extract model name to compare
                raw_model_name = settings.gemini_model_name if not settings.gemini_model_name.startswith("models/") else settings.gemini_model_name.replace("models/", "")
                raw_embed_name = settings.gemini_embedding_model if not settings.gemini_embedding_model.startswith("models/") else settings.gemini_embedding_model.replace("models/", "")
                
                target_model = f"models/{raw_model_name}" if job.job_type == "ocr" else f"models/{raw_embed_name}"
                
                # 3. Handle model mismatch
                if remote_job.model != target_model and not remote_job.model.endswith(target_model):
                    log_json(logger, logging.WARNING, "Model mismatch found. Canceling job and returning items to pending queue.", 
                             job_id=str(job.id), remote_id=job.remote_job_id,
                             expected=target_model, actual=remote_job.model)
                             
                    try:
                        self.batch_client.cancel_job(job.remote_job_id)
                    except Exception as ce:
                        log_json(logger, logging.ERROR, "Failed to cancel mismatched job", error=str(ce))
                    
                    await self.jobs_repo.update_job_status(job.id, "failed", error_message=f"Model mismatch. Exp: {target_model}, Act: {remote_job.model}")
                    
                    if job.job_type == "ocr":
                        stmt = text("UPDATE pages SET status = 'pending' WHERE id IN (SELECT target_id FROM batch_job_requests WHERE batch_job_id = :jid AND status = 'pending')")
                        await self.session.execute(stmt, {'jid': str(job.id)})
                    
                    stmt2 = text("DELETE FROM batch_job_requests WHERE batch_job_id = :jid")
                    await self.session.execute(stmt2, {'jid': str(job.id)})
                    
                    if job.input_file_uri and job.input_file_uri.startswith("files/"):
                        self.batch_client.delete_file(job.input_file_uri)
                        
                    await self.session.commit()
                    continue

                log_json(logger, logging.DEBUG, "Job status check", 
                         job_id=str(job.id), remote_id=job.remote_job_id, status=current_status)
                
                # 4. Save current remote status
                await self.jobs_repo.update_job_status(job.id, job.status, remote_status=current_status)

                # 5. Handle remote job status outcomes
                if current_status == "SUCCEEDED":
                    await self.process_job_results(job)
                elif current_status in ["FAILED", "CANCELLED"]:
                    log_json(logger, logging.WARNING, "Batch job failed on Gemini", 
                             job_id=str(job.id), remote_id=job.remote_job_id, status=current_status)
                    await self.jobs_repo.update_job_status(job.id, "failed", remote_status=current_status, error_message=f"Gemini status: {current_status}")
                    await self.requests_repo.update_status_by_job(job.id, "failed")
                    await self.session.commit()
            except Exception as e:
                log_json(logger, logging.ERROR, "Error polling job", job_id=str(job.id), error=str(e))

    async def process_job_results(self, job: BatchJob):
        """
        Downloads and applies results from a completed batch job.
        """
        try:
            # 1. Download output file from Gemini API
            output_bytes = self.batch_client.download_batch_output(job.remote_job_id)
            if not output_bytes:
                log_json(logger, logging.WARNING, "No output bytes returned for job", job_id=str(job.id))
                return

            lines = output_bytes.decode('utf-8').splitlines()
            log_json(logger, logging.DEBUG, "Downloaded output file", job_id=str(job.id), line_count=len(lines))
            
            for line in lines:
                if not line.strip(): continue
                try:
                    result = json.loads(line)
                    
                    custom_id = None
                    if "custom_id" in result: custom_id = result["custom_id"]
                    elif "metadata" in result and "custom_id" in result["metadata"]: custom_id = result["metadata"]["custom_id"]
                    elif "request" in result and "metadata" in result["request"] and "custom_id" in result["request"]["metadata"]:
                        custom_id = result["request"]["metadata"]["custom_id"]
                    elif "request" in result and "custom_id" in result["request"]: custom_id = result["request"]["custom_id"]

                    response = result.get("response")
                    
                    if not custom_id:
                        log_json(logger, logging.WARNING, "Result missing custom_id", line=line[:100])
                        continue
                        
                    if not response:
                        log_json(logger, logging.WARNING, "Result missing response", custom_id=custom_id)
                        continue
                        
                    # Handle potential error codes in the batch response
                    if "error" in response:
                        log_json(logger, logging.ERROR, "Gemini result error", 
                                 custom_id=custom_id, error=response["error"])
                        continue

                    if job.job_type == "ocr":
                        await self._handle_ocr_result(custom_id, response)
                    else:
                        await self._handle_embedding_result(custom_id, response)
                except Exception as e:
                    log_json(logger, logging.ERROR, "Error parsing result line", error=str(e), line=line[:100])

            # 2. Mark job as completed
            await self.jobs_repo.update_job_status(job.id, "completed")
            await self.requests_repo.update_status_by_job(job.id, "completed")
            await self.session.commit()
            log_json(logger, logging.INFO, "Batch job results processed successfully", job_id=str(job.id))
            
            # 3. Clean up the input file if stored
            if job.input_file_uri and job.input_file_uri.startswith("files/"):
                self.batch_client.delete_file(job.input_file_uri)
                
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to process job results", job_id=str(job.id), error=str(e))
            await self.jobs_repo.update_job_status(job.id, "error", error_message=str(e))
            await self.requests_repo.update_status_by_job(job.id, "error")
            await self.session.commit()

    async def _handle_ocr_result(self, custom_id: str, response: Dict[str, Any]):
        """Parse OCR result and update Page"""
        # custom_id: ocr_{book_id}_{page_number}
        parts = custom_id.split("_")
        if len(parts) < 3: return
        book_id = parts[1]
        page_num = int(parts[2])
        
        try:
            # Extract text from Gemini 2.0 response
            # Candidates structure: response["candidates"][0]["content"]["parts"][0]["text"]
            candidates = response.get("candidates", [])
            if not candidates: return
            
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text: return

            # Atomic update to page
            stmt = (
                update(Page)
                .where(and_(Page.book_id == book_id, Page.page_number == page_num))
                .values(text=text, status="ocr_done", updated_by="batch_ocr", updated_at=datetime.now(timezone.utc))
            )
            result = await self.session.execute(stmt)
            
            if result.rowcount == 0:
                log_json(logger, logging.INFO, "Skipped OCR result (Page deleted)", book_id=book_id, page_number=page_num)
                
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to handle OCR result", custom_id=custom_id, error=str(e))

    async def _handle_embedding_result(self, custom_id: str, response: Dict[str, Any]):
        """Parse embedding result and update Chunk"""
        # custom_id: embed_{chunk_id}
        chunk_id_str = custom_id.replace("embed_", "")
        
        try:
            # Extract embedding from text-embedding-004 response
            # Response structure: response["embedding"]["values"]
            embedding = response.get("embedding", {}).get("values")
            if not embedding: return

            # 1. Update the chunk
            stmt = (
                update(Chunk)
                .where(Chunk.id == chunk_id_str)
                .values(embedding=embedding)
            )
            result = await self.session.execute(stmt)

            if result.rowcount == 0:
                log_json(logger, logging.INFO, "Skipped embedding result (Chunk deleted)", chunk_id=chunk_id_str)

            # 2. Check and update page status if all chunks for that page are now embedded
            # This is a bit complex in a batch results loop, but we can do it efficiently
            # Better approach: After all results are processed, run a sweep to update page statuses
            # For simplicity here, we'll do it per chunk, though a bulk sweep is better for scale.
            
        except Exception as e:
            log_json(logger, logging.ERROR, "Failed to handle embedding result", custom_id=custom_id, error=str(e))

    async def chunk_ocr_done_pages(self, limit: int = 100):
        """
        Finds pages with 'ocr_done' status, chunks their text, 
        and updates status to 'chunked'.
        """
        from app.utils.markdown import strip_markdown
        from app.services.chunking_service import chunking_service
        from sqlalchemy import delete

        stmt = select(Page).where(Page.status == "ocr_done").limit(limit)
        res = await self.session.execute(stmt)
        pages = res.scalars().all()
        
        if not pages:
            return

        log_json(logger, logging.INFO, "Chunking OCR results", count=len(pages))

        for page in pages:
            if not page.text:
                page.status = "error"
                continue

            clean_text = strip_markdown(page.text)
            text_chunks = chunking_service.split_text(clean_text)

            # Delete existing chunks for this page
            await self.session.execute(
                delete(Chunk).where(and_(Chunk.book_id == page.book_id, Chunk.page_number == page.page_number))
            )

            # Insert new chunks with NULL embedding
            for i, chunk_text in enumerate(text_chunks):
                new_chunk = Chunk(
                    book_id=page.book_id,
                    page_number=page.page_number,
                    chunk_index=i,
                    text=chunk_text,
                    embedding=None 
                )
                self.session.add(new_chunk)

            page.status = "chunked"
            page.updated_by = "batch_chunker"
            page.updated_at = datetime.now(timezone.utc)

        await self.session.commit()

    async def finalize_indexed_pages(self):
        """
        Sweeps pages with status 'chunked' and checks if all their chunks have embeddings.
        If so, marks them as 'indexed'.
        Then updates Book statuses based on overall progress.
        """
        # 1. Update Pages
        stmt = select(Page).where(Page.status == "chunked")
        res = await self.session.execute(stmt)
        pages = res.scalars().all()
        
        updated_books = set()
        for p in pages:
            # Check if there are any chunks for this page that STILL have NULL embedding
            check_stmt = select(func.count()).select_from(Chunk).where(
                and_(
                    Chunk.book_id == p.book_id,
                    Chunk.page_number == p.page_number,
                    Chunk.embedding == None
                )
            )
            count_res = await self.session.execute(check_stmt)
            missing_count = count_res.scalar() or 0
            
            if missing_count == 0:
                # All chunks are embedded!
                p.status = "indexed"
                p.updated_by = "batch_finalizer"
                p.updated_at = datetime.now(timezone.utc)
                updated_books.add(p.book_id)
                log_json(logger, logging.DEBUG, "Page fully indexed via batch", 
                         book_id=p.book_id, page=p.page_number)
        
        await self.session.commit()

        # 2. Update Books
        # We only check books that had at least one page indexed in this run
        # OR all currently non-ready books if we want to be thorough
        if not updated_books:
            # Still check everything non-ready periodically
            stmt = select(Book).where(Book.status.in_(["ocr_processing", "ocr_done", "indexing", "chunked", "error"]))
            res = await self.session.execute(stmt)
            books_to_check = res.scalars().all()
        else:
            stmt = select(Book).where(Book.id.in_(list(updated_books)))
            res = await self.session.execute(stmt)
            books_to_check = res.scalars().all()

        for book in books_to_check:
            # Count OCR-done pages
            ocr_stmt = select(func.count()).select_from(Page).where(
                and_(Page.book_id == book.id, Page.status.in_(['ocr_done', 'chunked', 'indexed']))
            )
            ocr_res = await self.session.execute(ocr_stmt)
            ocr_count = ocr_res.scalar() or 0

            # Count Indexed pages
            idx_stmt = select(func.count()).select_from(Page).where(
                and_(Page.book_id == book.id, Page.status == "indexed")
            )
            idx_res = await self.session.execute(idx_stmt)
            idx_count = idx_res.scalar() or 0

            # Count Errors
            err_stmt = select(func.count()).select_from(Page).where(
                and_(Page.book_id == book.id, Page.status == "error")
            )
            err_res = await self.session.execute(err_stmt)
            error_count = err_res.scalar() or 0

            # Update book metadata
            book.ocr_done_count = ocr_count
            book.error_count = error_count
            
            # Determine overall status
            new_status = book.status
            if idx_count == book.total_pages and book.total_pages > 0:
                new_status = "ready"
            elif ocr_count == book.total_pages and book.total_pages > 0:
                new_status = "ocr_done"
            elif error_count > 0:
                # If some pages are error but others are moving, keep it in current state or mark error
                # Usually we only mark the whole book 'error' if it gets stuck
                pass

            if new_status != book.status:
                log_json(logger, logging.INFO, "Book status updated via batch", 
                         book_id=book.id, old_status=book.status, new_status=new_status)
                book.status = new_status
            
            book.last_updated = datetime.now(timezone.utc)

        await self.session.commit()
