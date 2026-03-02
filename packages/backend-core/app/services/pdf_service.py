"""Shared PDF utilities used by both the upload endpoint and GCS discovery scanner."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page

logger = logging.getLogger(__name__)


def read_pdf_page_count(path: Path) -> int:
    """Return the number of pages in a PDF, or 0 on failure."""
    try:
        import fitz
        doc = fitz.open(path)
        count = len(doc)
        doc.close()
        return count
    except Exception as e:
        logger.warning("pdf_service: failed to read page count path=%s error=%s", path, e)
        return 0


def extract_pdf_cover(pdf_path: Path, cover_path: Path) -> bool:
    """Render the first page of a PDF to a JPEG at cover_path. Returns True on success."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            pix.save(str(cover_path))
            doc.close()
            return True
        doc.close()
    except Exception as e:
        logger.warning("pdf_service: failed to extract cover path=%s error=%s", pdf_path, e)
    return False


def create_page_stubs(session: AsyncSession, book_id: str, page_count: int) -> None:
    """Add Page stub rows to the session (caller must commit)."""
    if page_count > 0:
        session.add_all([
            Page(book_id=book_id, page_number=n)
            for n in range(1, page_count + 1)
        ])
