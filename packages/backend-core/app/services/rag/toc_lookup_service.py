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

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page
from app.db.repositories.book_sections_repository import BookSectionsRepository
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_structure_service import parse_page_blocks
from app.utils.text import (
    clean_known_poem_text,
    normalize_section_title,
    normalize_uyghur_chars,
    parse_toc_entries,
)

_DEFAULT_MAX_PAGES = 10
_MAX_UNFILTERED_SHORT_WORK_MATCHES = 20


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
    content_start_page: Optional[str] = None
    content_end_page: Optional[str] = None
    other_matches: Tuple["ShortWorkMatch", ...] = field(default_factory=tuple)


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


def _slice_section_pages_text(
    pages: List[Page],
    *,
    start_page: int,
    start_block_index: int,
    end_page: int,
    end_block_index: Optional[int],
) -> str:
    """Slice `pages` to `[start_block_index .. end_block_index]` on boundary pages
    so adjacent works on the same page are excluded."""
    page_parts: list[str] = []
    for p in pages:
        raw_text = p.text or ""
        if not raw_text.strip():
            continue
        need_start_slice = p.page_number == start_page and start_block_index > 0
        need_end_slice = p.page_number == end_page and end_block_index is not None
        if need_start_slice or need_end_slice:
            blocks = parse_page_blocks(
                raw_text, is_toc=bool(getattr(p, "is_toc", False))
            )
            kept = [
                b.raw_text
                for b in blocks
                if (not need_start_slice or b.block_index >= start_block_index)
                and (
                    not need_end_slice
                    or end_block_index is None
                    or b.block_index <= end_block_index
                )
                and b.kind != "meta_noise"
            ]
            sliced = "\n\n".join(kept)
        else:
            sliced = raw_text
        cleaned = clean_known_poem_text(sliced)
        if cleaned:
            page_parts.append(cleaned)
    return "\n\n".join(page_parts)


async def resolve_short_work(
    session: AsyncSession,
    title: str,
    book_id: Optional[str] = None,
    *,
    candidate_book_ids: Optional[List[str]] = None,
    question: Optional[str] = None,
) -> Optional[ShortWorkMatch]:
    pages_repo = PagesRepository(session)
    books_repo = BooksRepository(session)
    sections_repo = BookSectionsRepository(session)
    norm_title = normalize_section_title(title)

    # 1. Primary path: resolve via `book_sections` (supports both ToC-backed and ToC-less books)
    scope_book_ids: Optional[List[str]] = (
        [book_id]
        if book_id
        else (list(candidate_book_ids) if candidate_book_ids else None)
    )
    scoped_from_question = False
    if scope_book_ids is None and question:
        try:
            author_books = await books_repo.find_books_by_author_in_question(question)
            if isinstance(author_books, list) and author_books:
                scope_book_ids = [
                    str(b.id) for b in author_books if getattr(b, "id", None)
                ]
                scoped_from_question = bool(scope_book_ids)
        except Exception:
            pass

    section_hits: list[dict] = []
    if norm_title:
        try:
            raw_hits = await sections_repo.search_by_normalized_title(
                norm_title,
                book_ids=scope_book_ids,
                limit=_MAX_UNFILTERED_SHORT_WORK_MATCHES + 5,
            )
            if isinstance(raw_hits, list) and all(
                isinstance(r, dict) for r in raw_hits
            ):
                section_hits = raw_hits
        except Exception:
            section_hits = []

    if section_hits:
        max_pages = await _max_pages_config(session)
        is_unfiltered_global = (
            book_id is None and not candidate_book_ids and not scoped_from_question
        )
        if (
            is_unfiltered_global
            and len(section_hits) > _MAX_UNFILTERED_SHORT_WORK_MATCHES
        ):
            return None

        top = section_hits[0]
        top_start = int(top["start_page"])
        top_end = int(top.get("end_page") or top_start)
        if top_end < top_start:
            top_end = top_start
        span_pages = top_end - top_start + 1
        book_total_pages = int(top.get("book_total_pages") or 0)
        is_last_section_in_book = book_total_pages > 0 and top_end >= book_total_pages
        truncated = False
        if span_pages > max_pages:
            if is_last_section_in_book:
                top_end = top_start + max_pages - 1
                truncated = True
            else:
                return None

        top_book_id = str(top["book_id"])
        pages = await pages_repo.find_range(top_book_id, top_start, top_end)
        if pages:
            cleaned = _slice_section_pages_text(
                pages,
                start_page=top_start,
                start_block_index=int(top.get("start_block_index") or 0),
                end_page=top_end,
                end_block_index=(
                    None
                    if truncated
                    else (
                        int(top["end_block_index"])
                        if top.get("end_block_index") is not None
                        else None
                    )
                ),
            )
            if cleaned:
                content_start = getattr(pages[0], "content_page_number", None)
                content_end = getattr(pages[-1], "content_page_number", None)
                if not content_start and top.get("toc_printed_page") is not None:
                    content_start = str(top["toc_printed_page"])

                alternates: list[ShortWorkMatch] = []
                for alt in section_hits[1:_MAX_UNFILTERED_SHORT_WORK_MATCHES]:
                    alt_start = int(alt["start_page"])
                    alt_end = int(alt.get("end_page") or alt_start)
                    alt_total = int(alt.get("book_total_pages") or 0)
                    alt_truncated = False
                    if alt_end - alt_start + 1 > max_pages:
                        if alt_total > 0 and alt_end >= alt_total:
                            alt_end = alt_start + max_pages - 1
                            alt_truncated = True
                        else:
                            continue
                    alt_printed = (
                        str(alt["toc_printed_page"])
                        if alt.get("toc_printed_page") is not None
                        else None
                    )
                    alternates.append(
                        ShortWorkMatch(
                            book_id=str(alt["book_id"]),
                            title=str(alt.get("title") or title),
                            text="",
                            start_page=alt_start,
                            end_page=max(alt_start, alt_end),
                            truncated=alt_truncated,
                            book_title=alt.get("book_title"),
                            book_author=alt.get("book_author"),
                            content_start_page=alt_printed,
                            content_end_page=None,
                        )
                    )

                return ShortWorkMatch(
                    book_id=top_book_id,
                    title=str(top.get("title") or title),
                    text=cleaned,
                    start_page=top_start,
                    end_page=top_end,
                    truncated=truncated,
                    book_title=top.get("book_title"),
                    book_author=top.get("book_author"),
                    content_start_page=content_start,
                    content_end_page=content_end,
                    other_matches=tuple(alternates),
                )

    # 2. Fallback path: parse `toc_pages` directly when `book_sections` is empty
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
    content_start_page = getattr(start_page_row, "content_page_number", None) or (
        str(printed_start) if printed_start else None
    )
    content_end_page = (
        getattr(pages[-1], "content_page_number", None) if pages else None
    )

    return ShortWorkMatch(
        book_id=target_book_id,
        title=matched_title,
        text=cleaned,
        start_page=start_page,
        end_page=end_page,
        truncated=truncated,
        book_title=book.title,
        book_author=book.author,
        content_start_page=content_start_page,
        content_end_page=content_end_page,
    )
