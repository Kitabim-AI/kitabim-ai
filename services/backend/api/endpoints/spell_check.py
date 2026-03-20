"""
Spell Check API — dictionary-based spell check results per book/page.

All endpoints require editor or admin role.
"""
from __future__ import annotations

import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select, text, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import (
    PAGE_MILESTONE_IDLE,
    PAGE_MILESTONE_SUCCEEDED,
    PIPELINE_STEP_CHUNKING,
    PIPELINE_STEP_EMBEDDING,
)
from app.db.session import get_session
from app.db.models import Book, Page, PageSpellIssue, Dictionary
from app.core.config import settings
from app.models.user import User
from app.services.spell_check_service import run_spell_check_for_page
from auth.dependencies import require_editor, require_admin

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────────────

class SpellIssueOut(BaseModel):
    id: int
    word: str
    char_offset: Optional[int]
    char_end: Optional[int]
    ocr_corrections: List[str]
    status: str

    model_config = {"from_attributes": True}


class PageSpellCheckOut(BaseModel):
    milestone: Optional[str]
    issues: List[SpellIssueOut]


class PageSpellSummary(BaseModel):
    page_number: int
    open_count: int
    total_count: int
    spell_check_milestone: Optional[str]


class BookSpellSummaryOut(BaseModel):
    total_open: int
    total_issues: int
    pages: List[PageSpellSummary]


# ── Request schemas ───────────────────────────────────────────────────────────

class CorrectionItem(BaseModel):
    issue_id: int
    corrected_word: str
    original_word: Optional[str] = None
    range: Optional[List[int]] = None
    is_auto_correction: bool = False
    is_dictionary_addition: bool = False


class ApplyCorrectionsRequest(BaseModel):
    corrections: List[CorrectionItem]


class IgnoreIssuesRequest(BaseModel):
    issue_ids: List[int]


class RandomBookOut(BaseModel):
    book_id: str
    title: str
    author: Optional[str]
    volume: Optional[int]
    total_pages: int
    total_issues: int
    pages_with_issues: List[int]
    first_issue_page: int


class AddToDictionaryRequest(BaseModel):
    word: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/spell-check/random-book", response_model=RandomBookOut)
async def get_random_book_with_issues(
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Return a random book that has at least one open spell check issue.

    Uses a two-step approach for better performance:
    1. Fast random sampling to get candidate book IDs
    2. Detailed query for the selected book
    """
    # Step 1: Get a random book ID with open issues using a faster approach
    # We pick a random open issue and get its book_id.
    # This is much faster than GROUP BY + ORDER BY RANDOM() on large datasets.
    book_id_result = await session.execute(
        text("""
            WITH random_id AS (
                SELECT floor(random() * (max(id) - min(id) + 1) + min(id)) as target_id
                FROM page_spell_issues
                WHERE status = 'open'
            ),
            selected_issue AS (
                SELECT page_id
                FROM page_spell_issues
                WHERE status = 'open'
                  AND id >= (SELECT target_id FROM random_id)
                ORDER BY id
                LIMIT 1
            )
            SELECT book_id
            FROM pages
            WHERE id = (SELECT page_id FROM selected_issue)
        """)
    )

    book_row = book_id_result.fetchone()
    if not book_row:
        raise HTTPException(status_code=404, detail="No books with open spell check issues found")

    selected_book_id = book_row.book_id

    # Step 2: Get all the details for this specific book
    result = await session.execute(
        text("""
            WITH pages_with_issues AS (
                SELECT DISTINCT p.page_number
                FROM pages p
                INNER JOIN page_spell_issues psi ON psi.page_id = p.id
                WHERE p.book_id = :book_id AND psi.status = 'open'
            ),
            issue_count AS (
                SELECT COUNT(psi.id) as total
                FROM pages p
                INNER JOIN page_spell_issues psi ON psi.page_id = p.id
                WHERE p.book_id = :book_id AND psi.status = 'open'
            )
            SELECT
                b.id as book_id,
                b.title,
                b.author,
                b.volume,
                b.total_pages,
                COALESCE(ic.total, 0) as total_issues,
                COALESCE(
                    (SELECT json_agg(page_number ORDER BY page_number)
                     FROM pages_with_issues),
                    '[]'::json
                ) as pages_with_issues
            FROM books b
            CROSS JOIN issue_count ic
            WHERE b.id = :book_id
        """),
        {"book_id": selected_book_id}
    )

    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No books with open spell check issues found")

    pages_list = row.pages_with_issues if row.pages_with_issues else []

    return RandomBookOut(
        book_id=row.book_id,
        title=row.title,
        author=row.author,
        volume=row.volume,
        total_pages=row.total_pages,
        total_issues=row.total_issues,
        pages_with_issues=pages_list,
        first_issue_page=pages_list[0] if pages_list else 1,
    )


@router.get("/{book_id}/spell-check/summary", response_model=BookSpellSummaryOut)
async def get_spell_check_summary(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Issue counts per page for a book. Accessible by editors and admins."""
    pages_result = await session.execute(
        select(Page.id, Page.page_number, Page.spell_check_milestone)
        .where(Page.book_id == book_id)
        .order_by(Page.page_number)
    )
    pages = pages_result.fetchall()

    if not pages:
        raise HTTPException(status_code=404, detail="Book not found or has no pages")

    page_ids = [p.id for p in pages]

    counts_result = await session.execute(
        select(
            PageSpellIssue.page_id,
            func.count().label("total"),
            func.sum(
                case((PageSpellIssue.status == "open", 1), else_=0)
            ).label("open"),
        )
        .where(PageSpellIssue.page_id.in_(page_ids))
        .group_by(PageSpellIssue.page_id)
    )
    counts_by_page = {row.page_id: row for row in counts_result.fetchall()}

    page_summaries = []
    total_open = 0
    total_issues = 0

    for page in pages:
        counts = counts_by_page.get(page.id)
        open_count = int(counts.open or 0) if counts else 0
        total_count = int(counts.total or 0) if counts else 0
        total_open += open_count
        total_issues += total_count
        page_summaries.append(PageSpellSummary(
            page_number=page.page_number,
            open_count=open_count,
            total_count=total_count,
            spell_check_milestone=page.spell_check_milestone,
        ))

    return BookSpellSummaryOut(
        total_open=total_open,
        total_issues=total_issues,
        pages=page_summaries,
    )


@router.get("/{book_id}/pages/{page_num}/spell-check", response_model=PageSpellCheckOut)
async def get_page_spell_issues(
    book_id: str,
    page_num: int,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """All spell check issues for a specific page, ordered by position."""
    page_result = await session.execute(
        select(Page).where(Page.book_id == book_id, Page.page_number == page_num)
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Proactively apply any matching auto-correction rules so the user doesn't see them
    from app.services.auto_correct_service import apply_auto_corrections_to_page
    applied_count = await apply_auto_corrections_to_page(session, page.id)
    if applied_count > 0:
        await session.commit()
        await session.refresh(page)

    issues_result = await session.execute(
        select(PageSpellIssue)
        .where(PageSpellIssue.page_id == page.id)
        .order_by(PageSpellIssue.char_offset)
    )
    return PageSpellCheckOut(
        milestone=page.spell_check_milestone,
        issues=list(issues_result.scalars().all()),
    )


@router.post("/{book_id}/pages/{page_num}/spell-check/apply")
async def apply_spell_corrections(
    book_id: str,
    page_num: int,
    body: ApplyCorrectionsRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    Apply corrections to page text.

    Replaces each corrected word by char offset (processed in reverse order so
    earlier offsets are not invalidated by later replacements). Marks the page
    as is_indexed=False to trigger re-embedding, and records the editor.

    If is_auto_correction is True and user is admin, also creates a global
    auto-correction rule.
    """
    from app.db.models import PageSpellIssue, AutoCorrectRule, Page

    page_result = await session.execute(
        select(Page).where(Page.book_id == book_id, Page.page_number == page_num)
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if not body.corrections:
        return {"applied": 0}

    issue_ids = [c.issue_id for c in body.corrections]
    issues_result = await session.execute(
        select(PageSpellIssue).where(
            PageSpellIssue.id.in_(issue_ids),
            PageSpellIssue.page_id == page.id,
        )
    )
    issues_by_id = {issue.id: issue for issue in issues_result.scalars().all()}

    # Sort by offset descending so we apply from end → start, preserving positions
    replacements = []
    processed_auto_corrections = set()  # Track unique misspelled words to avoid redundant rule creation
    processed_dict_additions = set()
    
    for c in body.corrections:
        issue = issues_by_id.get(c.issue_id)
        if not issue:
            continue
            
        # Global auto-correction rule creation 
        # (Editors and Admins both allowed to help build the global ruleset)
        word_to_save = c.original_word or issue.word
        if c.is_auto_correction and word_to_save not in processed_auto_corrections:
            processed_auto_corrections.add(word_to_save)
            
            # Upsert into auto_correct_rules
            existing_stmt = select(AutoCorrectRule).where(
                AutoCorrectRule.misspelled_word == word_to_save
            )
            existing_res = await session.execute(existing_stmt)
            existing_rule = existing_res.scalar_one_or_none()
            
            if existing_rule:
                existing_rule.corrected_word = c.corrected_word
                existing_rule.is_active = True
                existing_rule.updated_at = func.now()
            else:
                new_rule = AutoCorrectRule(
                    misspelled_word=word_to_save,
                    corrected_word=c.corrected_word,
                    is_active=True,
                    created_by=current_user.id
                )
                session.add(new_rule)

        # Global Dictionary addition
        if c.is_dictionary_addition and word_to_save not in processed_dict_additions:
            processed_dict_additions.add(word_to_save)
            
            # Check if already in dictionary
            dict_stmt = select(Dictionary).where(Dictionary.word == word_to_save)
            dict_res = await session.execute(dict_stmt)
            if not dict_res.scalar_one_or_none():
                session.add(Dictionary(word=word_to_save))
                
                # Proactively mark all matching OPEN issues everywhere as 'ignored'
                await session.execute(
                    update(PageSpellIssue)
                    .where(PageSpellIssue.word == word_to_save, PageSpellIssue.status == "open")
                    .values(status="ignored")
                )

        # Use provided range if available (for phrase edits), otherwise use issue defaults
        if c.range and len(c.range) == 2:
            start, end = c.range
        else:
            if issue.char_offset is None or issue.char_end is None:
                continue
            start, end = issue.char_offset, issue.char_end
            
        replacements.append((start, end, c.corrected_word, issue.id))
    
    replacements.sort(key=lambda x: x[0], reverse=True)

    # Apply updates to the Page object
    page_text = page.text or ""
    for start, end, corrected, _ in replacements:
        page_text = page_text[:start] + corrected + page_text[end:]
    
    page.text = page_text
    page.is_indexed = False
    page.chunking_milestone = PAGE_MILESTONE_IDLE
    page.embedding_milestone = PAGE_MILESTONE_IDLE
    page.updated_by = current_user.id
    page.last_updated = func.now()

    # Mark issues as corrected
    corrected_ids = [r[3] for r in replacements]
    for issue_id in corrected_ids:
        issue = issues_by_id.get(issue_id)
        if issue:
            issue.status = "corrected"

    # Flush changes so the milestone statistics see the new states
    await session.flush()
    
    # Update book milestones (calculates from flushed page states)
    from app.services.book_milestone_service import BookMilestoneService
    await BookMilestoneService.update_book_milestone_for_step(session, book_id, PIPELINE_STEP_CHUNKING)
    await BookMilestoneService.update_book_milestone_for_step(session, book_id, PIPELINE_STEP_EMBEDDING)
    
    await session.commit()

    return {"applied": len(corrected_ids)}


@router.post("/{book_id}/spell-check/trigger")
async def trigger_spell_check(
    book_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    Reset spell_check_milestone to 'idle' for all OCR-complete pages in a book.
    The spell check scanner will pick them up within its next cycle (~1 min).
    """
    result = await session.execute(
        update(Page)
        .where(
            and_(
                Page.book_id == book_id,
                or_(
                    Page.pipeline_step == PIPELINE_STEP_EMBEDDING,
                    Page.pipeline_step.is_(None),
                ),
                Page.milestone == PAGE_MILESTONE_SUCCEEDED,
            )
        )
        .values(spell_check_milestone=PAGE_MILESTONE_IDLE)
        .returning(Page.id)
    )
    queued = len(result.fetchall())
    await session.commit()

    if queued == 0:
        raise HTTPException(
            status_code=400,
            detail="No OCR-complete pages found for this book. Ensure the book has finished processing first.",
        )

    return {"queued": queued}


@router.post("/{book_id}/pages/{page_num}/spell-check/trigger")
async def trigger_page_spell_check(
    book_id: str,
    page_num: int,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """
    Run spell check on a single page immediately (inline, no worker needed).
    Returns the number of issues found.
    """
    page_result = await session.execute(
        select(Page).where(Page.book_id == book_id, Page.page_number == page_num)
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.milestone != PAGE_MILESTONE_SUCCEEDED or (page.pipeline_step is not None and page.pipeline_step != PIPELINE_STEP_EMBEDDING):
        raise HTTPException(
            status_code=400,
            detail="Page has not completed OCR/embedding pipeline yet.",
        )

    issue_count = await run_spell_check_for_page(session, page)
    await session.commit()

    return {"issues_found": issue_count}


@router.post("/{book_id}/pages/{page_num}/spell-check/ignore")
async def ignore_spell_issues(
    book_id: str,
    page_num: int,
    body: IgnoreIssuesRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Mark spell check issues as ignored (will not be re-flagged on next scan)."""
    page_result = await session.execute(
        select(Page).where(Page.book_id == book_id, Page.page_number == page_num)
    )
    page = page_result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    await session.execute(
        update(PageSpellIssue)
        .where(
            PageSpellIssue.id.in_(body.issue_ids),
            PageSpellIssue.page_id == page.id,
        )
        .values(status="ignored")
    )
    await session.commit()

    return {"ignored": len(body.issue_ids)}


@router.post("/spell-check/dictionary")
async def add_to_dictionary(
    body: AddToDictionaryRequest,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Add a word to the global spell check dictionary. Editor and Admin allowed."""
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")

    # Check if already exists
    stmt = select(Dictionary).where(Dictionary.word == word)
    res = await session.execute(stmt)
    if res.scalar_one_or_none():
        return {"added": 0, "message": "Word already in dictionary"}

    new_word = Dictionary(word=word)
    session.add(new_word)
    
    # Also mark all matching OPEN issues across the entire system as 'ignored'
    # since the word is now valid.
    await session.execute(
        update(PageSpellIssue)
        .where(PageSpellIssue.word == word, PageSpellIssue.status == "open")
        .values(status="ignored")
    )
    
    await session.commit()
    return {"added": 1}
