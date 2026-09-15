"""Two-up spread detection: some book PDFs scan two facing pages into a
single wide image per PDF page. Left un-split, that image OCRs as one
merged logical page. This maps 1-based logical OCR page numbers onto the
underlying PDF page plus a clip Rect isolating the correct half."""

from __future__ import annotations

import fitz

# A PDF page at least this many times wider than tall is assumed to be a
# two-up spread rather than a genuinely wide single page.
SPREAD_ASPECT_RATIO = 1.2


def is_spread_page(page: "fitz.Page") -> bool:
    rect = page.rect
    return rect.height > 0 and (rect.width / rect.height) >= SPREAD_ASPECT_RATIO


def count_logical_pages(doc: "fitz.Document") -> int:
    """Total OCR page count once two-up spreads are split in half."""
    return sum(2 if is_spread_page(doc.load_page(i)) else 1 for i in range(len(doc)))


def resolve_logical_page(
    doc: "fitz.Document", page_number: int
) -> tuple["fitz.Page", "fitz.Rect | None"]:
    """Map a 1-based logical OCR page number to its PDF page and, for one
    half of a two-up spread, the clip Rect isolating that half (None for a
    normal single page).

    Uyghur is written right-to-left, so within a spread the right half is
    the lower (earlier) logical page and the left half is the higher
    (later) one — matching how the physical book was bound and scanned.
    """
    remaining = page_number
    for i in range(len(doc)):
        page = doc.load_page(i)
        if is_spread_page(page):
            if remaining <= 2:
                rect = page.rect
                mid_x = rect.x0 + rect.width / 2
                clip = (
                    fitz.Rect(mid_x, rect.y0, rect.x1, rect.y1)
                    if remaining == 1
                    else fitz.Rect(rect.x0, rect.y0, mid_x, rect.y1)
                )
                return page, clip
            remaining -= 2
        else:
            if remaining == 1:
                return page, None
            remaining -= 1
    raise IndexError(f"Logical page {page_number} out of range for this document")
