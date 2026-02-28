"""
GCS Discovery Scanner — lists GCS uploads/ and registers new books in the database.

New books are inserted with status='pending' and v2_pipeline_step=NULL.
PipelineDriver picks them up on its next run and initializes their pages into ocr/idle.

No rate limiting here — the cron interval controls frequency (every 5 minutes).
No auto-OCR triggering — PipelineDriver handles pipeline entry.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.db.repositories.books import BooksRepository
from app.services.storage_service import storage
from app.core.config import settings
from app.utils.observability import log_json
from app.utils.text import normalize_uyghur_chars

logger = logging.getLogger("app.worker_v2.gcs_discovery_scanner")

_JUNK_TITLES = ("untitled", "microsoft word", "document")


async def run_gcs_discovery_scanner(ctx) -> None:
    all_files = await storage.list_files("uploads/")
    pdf_files = [f for f in all_files if f.lower().endswith(".pdf")]

    new_count = 0
    skipped_count = 0
    duplicate_count = 0

    for remote_path in pdf_files:
        file_name = remote_path.split("/")[-1]

        # ── Fast DB checks (no download needed) ───────────────────────────────
        async with db_session.async_session_factory() as session:
            books_repo = BooksRepository(session)

            if await books_repo.find_by_filename(file_name):
                skipped_count += 1
                continue

            # If the filename stem is a known book ID (e.g. uploads/abc123.pdf)
            potential_id = file_name.removesuffix(".pdf")
            if await books_repo.get(potential_id):
                skipped_count += 1
                continue

        # ── Download to compute hash and extract metadata ──────────────────────
        temp_path = (
            settings.data_dir
            / f".v2_discovery_{os.getpid()}_{hashlib.md5(remote_path.encode()).hexdigest()}.pdf"
        )
        try:
            await storage.download_file(remote_path, temp_path)

            content_hash = _sha256(temp_path)

            async with db_session.async_session_factory() as session:
                books_repo = BooksRepository(session)
                if await books_repo.find_by_hash(content_hash):
                    duplicate_count += 1
                    continue

            title_from_pdf, author_from_pdf = _extract_pdf_metadata(temp_path, remote_path)

            book_id = hashlib.md5(
                f"{file_name}{datetime.now(timezone.utc)}".encode()
            ).hexdigest()[:12]

            final_title = _pick_title(title_from_pdf, file_name)

            # ── Standardize GCS path to uploads/{book_id}.pdf ─────────────────
            standard_path = f"uploads/{book_id}.pdf"
            if remote_path != standard_path:
                await storage.upload_file(temp_path, standard_path)
                try:
                    await storage.delete_file(remote_path)
                    log_json(logger, logging.INFO, "V2 discovery: standardized GCS path",
                             original=remote_path, standardized=standard_path)
                except Exception as e:
                    log_json(logger, logging.WARNING,
                             "V2 discovery: failed to delete original after standardization",
                             path=remote_path, error=str(e))

            # ── Insert book record ─────────────────────────────────────────────
            now = datetime.now(timezone.utc)
            async with db_session.async_session_factory() as session:
                books_repo = BooksRepository(session)
                try:
                    await books_repo.create(
                        id=book_id,
                        content_hash=content_hash,
                        title=normalize_uyghur_chars(final_title),
                        author=normalize_uyghur_chars(author_from_pdf) if author_from_pdf else None,
                        file_name=file_name,
                        status="pending",
                        upload_date=now,
                        last_updated=now,
                        categories=[],
                        source="gcs_sync",
                    )
                    await session.commit()
                    new_count += 1
                    log_json(logger, logging.INFO, "V2 discovery: registered new book",
                             title=final_title, book_id=book_id)
                except IntegrityError:
                    duplicate_count += 1
                    log_json(logger, logging.DEBUG,
                             "V2 discovery: book created concurrently, skipping",
                             file_name=file_name)

        except Exception as e:
            log_json(logger, logging.ERROR, "V2 discovery: failed to process GCS file",
                     path=remote_path, error=str(e))
        finally:
            temp_path.unlink(missing_ok=True)

    if new_count or duplicate_count:
        log_json(logger, logging.INFO, "V2 GCS discovery scanner finished",
                 discovered=new_count, skipped=skipped_count, duplicates=duplicate_count)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sha256(path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _extract_pdf_metadata(path, remote_path: str) -> tuple[str | None, str | None]:
    try:
        import fitz
        doc = fitz.open(path)
        meta = doc.metadata or {}
        doc.close()
        return meta.get("title"), meta.get("author")
    except Exception as e:
        log_json(logger, logging.WARNING, "V2 discovery: failed to read PDF metadata",
                 path=remote_path, error=str(e))
        return None, None


def _pick_title(title_from_pdf: str | None, file_name: str) -> str:
    if (
        title_from_pdf
        and len(title_from_pdf.strip()) > 2
        and not any(x in title_from_pdf.lower() for x in _JUNK_TITLES)
    ):
        return title_from_pdf.strip()
    return file_name.removesuffix(".pdf")
