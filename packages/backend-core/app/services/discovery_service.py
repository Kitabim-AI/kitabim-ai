import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db import session as db_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.repositories.jobs import JobsRepository
from app.services.storage_service import storage
from app.core.config import settings
from app.utils.observability import log_json
from app.langchain.models import is_llm_available

logger = logging.getLogger("app.discovery")

class DiscoveryService:
    """Service to discover and index PDF books stored in GCS"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.books_repo = BooksRepository(session)
        self.configs_repo = SystemConfigsRepository(session)
        self.jobs_repo = JobsRepository(session)

    async def sync_gcs_books(self, force: bool = False) -> dict:
        """Scan GCS uploads/ and add new books to the database"""

        # Ensure default configs exist
        await self._ensure_configs()

        # 1. Check worker capacity (unless forced)
        if not force:
            active_jobs = await self.jobs_repo.count_active()
            if active_jobs >= settings.queue_max_jobs:
                return {"status": "skipped", "reason": "Workers at capacity"}

        # 2. Check circuit breaker (unless forced)
        if not force:
            if not await is_llm_available():
                return {"status": "skipped", "reason": "Circuit breaker open"}

        # 3. Check if sync is due (unless forced)
        if not force:
            is_due = await self._is_sync_due()
            if not is_due:
                return {"status": "skipped", "reason": "Not due yet"}

        log_json(logger, logging.INFO, "Starting GCS book discovery sync")

        # 4. List files in uploads/
        # Storage provider already handles bucket routing
        all_files = await storage.list_files("uploads/")
        pdf_files = [f for f in all_files if f.lower().endswith(".pdf")]
        
        new_count = 0
        discovered_ids = []
        skipped_count = 0
        duplicate_count = 0
        
        for remote_path in pdf_files:
            # remote_path is like 'uploads/some_id.pdf' or 'uploads/Book Title.pdf'
            file_name = remote_path.split("/")[-1]
            
            # Check if filename is already in DB (by file_name or ID)
            # 1. Check by file_name
            existing = await self.books_repo.find_by_filename(file_name)
            if existing:
                skipped_count += 1
                continue

            # 2. Check if the filename IS the book ID (e.g. {id}.pdf)
            potential_id = file_name.replace(".pdf", "")
            existing_by_id = await self.books_repo.get(potential_id)
            if existing_by_id:
                skipped_count += 1
                continue
            
            # Download temporarily to compute hash
            # Include process ID to prevent temp file collisions between concurrent discoveries
            temp_path = settings.data_dir / f".discovery_{os.getpid()}_{hashlib.md5(remote_path.encode()).hexdigest()}.pdf"
            try:
                await storage.download_file(remote_path, temp_path)
                
                # Compute SHA-256 for deduplication
                hasher = hashlib.sha256()
                with open(temp_path, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        hasher.update(chunk)
                content_hash = hasher.hexdigest()
                
                # Check if this content already exists under a different filename
                existing_hash = await self.books_repo.find_by_hash(content_hash)
                if existing_hash:
                    duplicate_count += 1
                    temp_path.unlink(missing_ok=True)
                    continue
                
                # It's a truly new book!
                # Generate a unique ID (MD5 of filename + current time for uniqueness)
                book_id = hashlib.md5(f"{file_name}{datetime.now(timezone.utc)}".encode()).hexdigest()[:12]
                
                # If the remote filename isn't the standard ID-style, we might want to rename it in GCS
                # but for simplicity now, we just link to the existing path.
                # However, the app expects uploads/{id}.pdf.
                # Let's move/copy it to the standard location if needed.
                standard_path = f"uploads/{book_id}.pdf"
                if remote_path != standard_path:
                    # Upload the file to the new standard path
                    await storage.upload_file(temp_path, standard_path)
                    # Delete the original to prevent duplicates
                    try:
                        await storage.delete_file(remote_path)
                        log_json(logger, logging.INFO, "Cleaned up original file after standardization",
                                 original=remote_path, standardized=standard_path)
                    except Exception as e:
                        log_json(logger, logging.WARNING, "Failed to delete original file",
                                 path=remote_path, error=str(e))
                
                now = datetime.now(timezone.utc)
                try:
                    await self.books_repo.create(
                        id=book_id,
                        content_hash=content_hash,
                        title=file_name.replace(".pdf", ""),
                        file_name=file_name,
                        status="pending",
                        upload_date=now,
                        last_updated=now,
                        categories=[],
                        source="gcs_sync"
                    )
                    new_count += 1
                    discovered_ids.append(book_id)
                    log_json(logger, logging.INFO, "Discovered new book from GCS", file_name=file_name, book_id=book_id)
                except IntegrityError as ie:
                    # Another discovery process created this book concurrently (race condition)
                    # The unique constraint on content_hash prevents duplicates
                    duplicate_count += 1
                    log_json(logger, logging.INFO, "Book already created by concurrent discovery",
                             file_name=file_name, error=str(ie))
                    await self.session.rollback()  # Rollback the failed transaction
                
            except Exception as e:
                log_json(logger, logging.ERROR, "Failed to index GCS file", path=remote_path, error=str(e))
            finally:
                temp_path.unlink(missing_ok=True)

        # 5. Update last sync time
        await self.configs_repo.set_value("gcs_last_sync_at", datetime.now(timezone.utc).isoformat())
        await self.session.commit()

        # 6. Auto-trigger OCR if enabled
        auto_ocr = await self.configs_repo.get_value("gcs_auto_ocr_enabled", "true")
        if auto_ocr.lower() == "true" and discovered_ids:
            from app.queue import enqueue_pdf_processing
            for book_id in discovered_ids:
                log_json(logger, logging.INFO, "Auto-triggering OCR for discovered book", book_id=book_id)
                try:
                    await enqueue_pdf_processing(book_id, reason="auto_discovery")
                except Exception as e:
                    log_json(logger, logging.ERROR, "Failed to enqueue OCR for discovered book", book_id=book_id, error=str(e))

        result = {
            "status": "completed",
            "discovered": new_count,
            "discovered_ids": discovered_ids,
            "skipped": skipped_count,
            "duplicates": duplicate_count
        }
        log_json(logger, logging.INFO, "GCS discovery sync finished", **result)
        return result

    async def _ensure_configs(self) -> None:
        """Enusre default GCS sync configurations exist in the database"""
        interval = await self.configs_repo.get_value("gcs_auto_sync_interval_minutes")
        if interval is None:
            await self.configs_repo.set_value(
                "gcs_auto_sync_interval_minutes",
                "15",
                "Minimum interval between GCS bucket scans (rate limiting for both event-driven and cron-based discovery)"
            )
            log_json(logger, logging.INFO, "Initialized gcs_auto_sync_interval_minutes with default value 15")
        
        last_sync = await self.configs_repo.get_value("gcs_last_sync_at")
        if last_sync is None:
            await self.configs_repo.set_value(
                "gcs_last_sync_at",
                datetime.now(timezone.utc).isoformat(),
                "Timestamp of the last GCS bucket scan (used for rate limiting)"
            )
            log_json(logger, logging.INFO, "Initialized gcs_last_sync_at with current timestamp")
        
        auto_ocr = await self.configs_repo.get_value("gcs_auto_ocr_enabled")
        if auto_ocr is None:
            await self.configs_repo.set_value(
                "gcs_auto_ocr_enabled",
                "true",
                "Whether to automatically start OCR for books discovered via GCS sync"
            )
            log_json(logger, logging.INFO, "Initialized gcs_auto_ocr_enabled with default value true")
        
        await self.session.commit()

    async def _is_sync_due(self) -> bool:
        """Check if enough time has passed since the last sync"""
        interval_str = await self.configs_repo.get_value("gcs_auto_sync_interval_minutes", "60")
        last_sync_str = await self.configs_repo.get_value("gcs_last_sync_at")
        
        try:
            interval = int(interval_str)
        except ValueError:
            interval = 60
            
        if not last_sync_str:
            return True
            
        try:
            last_sync = datetime.fromisoformat(last_sync_str)
            # Handle naive datetime if timezone info is missing in the string
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
            
        return datetime.now(timezone.utc) > last_sync + timedelta(minutes=interval)
