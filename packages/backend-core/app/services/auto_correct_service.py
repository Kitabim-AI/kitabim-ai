"""
Auto-Correction Service — applies automatic corrections to spell check issues.

This service finds open spell check issues that match entries in the
spell_check_corrections table and applies the corrections to page text.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional
from datetime import datetime

from sqlalchemy import select, update, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page, PageSpellIssue, SpellCheckCorrection
from app.utils.observability import log_json

logger = logging.getLogger("app.services.auto_correct")


async def get_correction_rules(
    session: AsyncSession,
    auto_apply_only: bool = False
) -> Dict[str, str]:
    """
    Fetch all correction rules as a dictionary {misspelled_word: corrected_word}.

    Args:
        session: Database session
        auto_apply_only: If True, only return rules with auto_apply=True

    Returns:
        Dictionary mapping misspelled words to their corrections
    """
    stmt = select(
        SpellCheckCorrection.misspelled_word,
        SpellCheckCorrection.corrected_word
    )

    if auto_apply_only:
        stmt = stmt.where(SpellCheckCorrection.auto_apply == True)

    result = await session.execute(stmt)
    return {row.misspelled_word: row.corrected_word for row in result.fetchall()}


async def get_correction_for_word(
    session: AsyncSession,
    word: str
) -> Optional[str]:
    """
    Get the correction for a specific word if it exists.

    Args:
        session: Database session
        word: The misspelled word to look up

    Returns:
        The corrected word, or None if no correction exists
    """
    result = await session.execute(
        select(SpellCheckCorrection.corrected_word)
        .where(SpellCheckCorrection.misspelled_word == word)
    )
    row = result.fetchone()
    return row.corrected_word if row else None


async def apply_auto_corrections_to_page(
    session: AsyncSession,
    page_id: int,
    correction_rules: Optional[Dict[str, str]] = None
) -> int:
    """
    Apply all applicable auto-corrections to a single page.

    Finds open spell issues on the page that match correction rules,
    applies the corrections to the page text in reverse order (to preserve offsets),
    and marks the issues as corrected.

    Args:
        session: Database session
        page_id: The page to apply corrections to
        correction_rules: Optional pre-fetched correction rules dict.
                         If None, will fetch rules with auto_apply=True

    Returns:
        Number of corrections applied
    """
    # Fetch the page
    page_result = await session.execute(
        select(Page).where(Page.id == page_id)
    )
    page = page_result.scalar_one_or_none()
    if not page:
        logger.warning(f"Page {page_id} not found")
        return 0

    # Fetch correction rules if not provided
    if correction_rules is None:
        correction_rules = await get_correction_rules(session, auto_apply_only=True)

    if not correction_rules:
        return 0

    # Find open issues on this page that have correction rules
    issues_result = await session.execute(
        select(PageSpellIssue)
        .where(
            PageSpellIssue.page_id == page_id,
            PageSpellIssue.status == "open",
            PageSpellIssue.word.in_(correction_rules.keys())
        )
        .order_by(PageSpellIssue.char_offset.desc())  # Process from end to start
    )
    issues = list(issues_result.scalars().all())

    if not issues:
        return 0

    # Apply corrections to page text (from end to start to preserve offsets)
    page_text = page.text or ""
    corrected_issue_ids = []

    for issue in issues:
        if issue.char_offset is None or issue.char_end is None:
            logger.warning(f"Issue {issue.id} has no offset information, skipping")
            continue

        corrected_word = correction_rules.get(issue.word)
        if not corrected_word:
            continue

        # Apply the correction
        start, end = issue.char_offset, issue.char_end
        page_text = page_text[:start] + corrected_word + page_text[end:]
        corrected_issue_ids.append(issue.id)

        log_json(logger, logging.DEBUG, "applied auto-correction",
                 page_id=page_id,
                 issue_id=issue.id,
                 original=issue.word,
                 corrected=corrected_word,
                 offset=start)

    if not corrected_issue_ids:
        return 0

    # Mark issues as corrected with auto_corrected_at timestamp
    await session.execute(
        update(PageSpellIssue)
        .where(PageSpellIssue.id.in_(corrected_issue_ids))
        .values(
            status="corrected",
            auto_corrected_at=func.now()
        )
    )

    # Update the page text and mark for re-indexing
    await session.execute(
        update(Page)
        .where(Page.id == page_id)
        .values(
            text=page_text,
            is_indexed=False,  # Trigger re-embedding
            is_verified=True,
            last_updated=func.now()
        )
    )

    # Invalidate word index so the scanner re-builds it with the corrected words
    await session.execute(
        text("DELETE FROM book_word_index WHERE book_id = :book_id"),
        {"book_id": page.book_id}
    )

    log_json(logger, logging.INFO, "auto-corrections applied to page",
             page_id=page_id,
             book_id=page.book_id,
             page_number=page.page_number,
             corrections_count=len(corrected_issue_ids))

    return len(corrected_issue_ids)


async def find_pages_with_auto_correctable_issues(
    session: AsyncSession,
    limit: int = 50
) -> List[int]:
    """
    Find page IDs that have open spell issues matching auto-correction rules.

    Args:
        session: Database session
        limit: Maximum number of pages to return

    Returns:
        List of page IDs that have auto-correctable issues
    """
    # Query for pages with open issues that match correction rules with auto_apply=True
    # Using a CTE for better performance
    result = await session.execute(
        text("""
            WITH auto_correct_words AS (
                SELECT misspelled_word
                FROM spell_check_corrections
                WHERE auto_apply = true
            )
            SELECT DISTINCT psi.page_id
            FROM page_spell_issues psi
            INNER JOIN auto_correct_words acw ON psi.word = acw.misspelled_word
            WHERE psi.status = 'open'
              AND psi.char_offset IS NOT NULL
              AND psi.char_end IS NOT NULL
            LIMIT :limit
        """),
        {"limit": limit}
    )

    return [row.page_id for row in result.fetchall()]


async def get_auto_correction_stats(session: AsyncSession) -> Dict:
    """
    Get statistics about auto-corrections.

    Returns:
        Dictionary with statistics:
        - total_rules: Total number of correction rules
        - active_rules: Number of rules with auto_apply=True
        - total_auto_corrected: Total issues that have been auto-corrected
        - pending_corrections: Number of open issues that match correction rules
    """
    # Total correction rules
    total_rules_result = await session.execute(
        select(func.count()).select_from(SpellCheckCorrection)
    )
    total_rules = total_rules_result.scalar() or 0

    # Active correction rules
    active_rules_result = await session.execute(
        select(func.count())
        .select_from(SpellCheckCorrection)
        .where(SpellCheckCorrection.auto_apply == True)
    )
    active_rules = active_rules_result.scalar() or 0

    # Total auto-corrected issues
    auto_corrected_result = await session.execute(
        select(func.count())
        .select_from(PageSpellIssue)
        .where(PageSpellIssue.auto_corrected_at.isnot(None))
    )
    total_auto_corrected = auto_corrected_result.scalar() or 0

    # Pending corrections (open issues matching active rules)
    pending_result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT psi.id)
            FROM page_spell_issues psi
            INNER JOIN spell_check_corrections scc ON psi.word = scc.misspelled_word
            WHERE psi.status = 'open'
              AND scc.auto_apply = true
              AND psi.char_offset IS NOT NULL
              AND psi.char_end IS NOT NULL
        """)
    )
    pending_corrections = pending_result.scalar() or 0

    return {
        "total_rules": total_rules,
        "active_rules": active_rules,
        "total_auto_corrected": total_auto_corrected,
        "pending_corrections": pending_corrections
    }
