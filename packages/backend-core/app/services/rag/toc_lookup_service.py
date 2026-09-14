"""Deterministic table-of-contents lookup for named short works (poems,
songs) inside a book -- resolves a title straight to its exact page-range
content via the book's OCR'd ToC (``Page.is_toc`` / ``parse_toc_entries``),
bypassing embedding/keyword retrieval and the agent tool-calling loop
entirely for this one query shape.

Every failure mode (no ToC, no title match, entry too long to be a "short
work") returns ``None`` -- this is a pure additive shortcut. Callers MUST
fall through to the normal retrieval agent whenever it returns ``None``,
never treat a miss here as "content doesn't exist."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.utils.text import (
    clean_known_poem_text,
    normalize_uyghur_chars,
    parse_toc_entries,
)

_DEFAULT_MAX_PAGES = 10


@dataclass(frozen=True)
class ShortWorkMatch:
    book_id: str
    title: str
    text: str
    start_page: int
    end_page: int
    truncated: bool
    book_title: Optional[str] = None
    book_author: Optional[str] = None


def _normalize_title(title: str) -> str:
    return normalize_uyghur_chars(title).strip()


def _parse_book_toc(toc_pages: List[Page]) -> List[Tuple[str, int]]:
    """Parse title/printed-page entries out of a book's (possibly
    multi-page) ToC, in page order -- so entries are returned in the same
    order they're printed, regardless of how many ToC pages they span."""
    entries: List[Tuple[str, int]] = []
    for page in toc_pages:
        entries.extend(parse_toc_entries(page.text or ""))
    return entries


async def _max_pages_config(session: AsyncSession) -> int:
    configs_repo = SystemConfigsRepository(session)
    raw = await configs_repo.get_value(
        "toc_short_work_max_pages", str(_DEFAULT_MAX_PAGES)
    )
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_PAGES


async def resolve_short_work(
    session: AsyncSession,
    title: str,
    book_id: Optional[str] = None,
) -> Optional[ShortWorkMatch]:
    pages_repo = PagesRepository(session)

    target_book_id = book_id
    if target_book_id is None:
        hits = await pages_repo.search_toc_pages_by_phrase(title)
        if not hits:
            return None
        # Highest tsvector rank wins -- good enough for v1; a title
        # appearing in more than one book's ToC isn't disambiguated further.
        target_book_id = hits[0]["book_id"]

    toc_pages = await pages_repo.find_toc_pages(target_book_id)
    if not toc_pages:
        return None

    entries = _parse_book_toc(toc_pages)
    if not entries:
        return None

    normalized_target = _normalize_title(title)
    match_index = next(
        (
            i
            for i, (entry_title, _) in enumerate(entries)
            # A title appearing twice (e.g. two poems both called "غەزەل")
            # is not an error -- the first occurrence wins, deterministically.
            if _normalize_title(entry_title) == normalized_target
        ),
        None,
    )
    if match_index is None:
        return None

    matched_title, printed_start = entries[match_index]
    has_next = match_index + 1 < len(entries)
    max_pages = await _max_pages_config(session)

    if has_next:
        _, next_printed_start = entries[match_index + 1]
        printed_span = next_printed_start - printed_start
        if printed_span > max_pages:
            # Computed straight from the ToC's own printed-page numbers, no
            # DB fetch needed: this entry is a long section (chapter), not a
            # short work -- leave it to the normal retrieval agent entirely.
            return None

    book = await BooksRepository(session).get(target_book_id)
    if book is None:
        return None

    offset = book.content_page_offset or 0
    start_page = printed_start + offset

    if has_next:
        end_page = start_page + printed_span - 1
    else:
        # No next entry to bound the last ToC item -- use the book's total
        # page count instead (see toc_short_work_max_pages: an unusually
        # large last entry is truncated below, not rejected, since we can't
        # cheaply tell whether it's genuinely long or just followed by back
        # matter that inflates total_pages).
        end_page = book.total_pages or start_page
    if end_page < start_page:
        end_page = start_page

    # Heading verification: confirm the offset-resolved start page actually
    # contains the matched title, catching a stale/never-computed
    # content_page_offset before returning mismatched content.
    start_page_row = await pages_repo.find_one(target_book_id, start_page)
    if start_page_row is None or matched_title not in (start_page_row.text or ""):
        return None

    truncated = False
    if end_page - start_page + 1 > max_pages:
        end_page = start_page + max_pages - 1
        truncated = True

    pages = await pages_repo.find_range(target_book_id, start_page, end_page)
    cleaned = "\n\n".join(clean_known_poem_text(p.text or "") for p in pages if p.text)

    return ShortWorkMatch(
        book_id=target_book_id,
        title=matched_title,
        text=cleaned,
        start_page=start_page,
        end_page=end_page,
        truncated=truncated,
        book_title=book.title,
        book_author=book.author,
    )
