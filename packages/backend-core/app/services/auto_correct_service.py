"""
Auto-Correction Service — applies automatic corrections to spell check issues.

This service finds open spell check issues that match entries in the
auto_correct_rules table and applies the corrections to page text.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Optional

from sqlalchemy import select, update, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import PAGE_MILESTONE_IDLE
from app.db.models import Page, PageSpellIssue, AutoCorrectRule
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
        auto_apply_only: If True, only return rules with is_active=True

    Returns:
        Dictionary mapping misspelled words to their corrections
    """
    stmt = select(
        AutoCorrectRule.misspelled_word,
        AutoCorrectRule.corrected_word
    )

    if auto_apply_only:
        stmt = stmt.where(AutoCorrectRule.is_active)

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
        select(AutoCorrectRule.corrected_word)
        .where(AutoCorrectRule.misspelled_word == word)
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
    # Fetch the page with a lock to prevent concurrent updates
    page_result = await session.execute(
        select(Page).where(Page.id == page_id).with_for_update()
    )
    page = page_result.scalar_one_or_none()
    if not page:
        logger.warning(f"Page {page_id} not found")
        return 0

    # Fetch correction rules if not provided (default to active ones)
    if correction_rules is None:
        correction_rules = await get_correction_rules(session, auto_apply_only=True)

    if not correction_rules:
        return 0

    # Find issues on this page that were claimed for processing
    issues_result = await session.execute(
        select(PageSpellIssue)
        .where(
            PageSpellIssue.page_id == page_id,
            PageSpellIssue.status == "processing",
        )
        .order_by(PageSpellIssue.char_offset.desc())  # Process from end to start
    )
    issues = list(issues_result.scalars().all())

    # Fallback: if no processing issues, check for open ones (e.g. if manually triggered)
    if not issues:
        issues_result = await session.execute(
            select(PageSpellIssue)
            .where(
                PageSpellIssue.page_id == page_id,
                PageSpellIssue.status == "open",
                PageSpellIssue.word.in_(correction_rules.keys())
            )
            .order_by(PageSpellIssue.char_offset.desc())
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
            chunking_milestone=PAGE_MILESTONE_IDLE,  # Force re-chunking of modified text
            embedding_milestone=PAGE_MILESTONE_IDLE, # Force re-embedding of modified text
            last_updated=func.now()
        )
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
    Find page IDs that have open spell issues matching auto-correction rules,
    and mark those specific issues as 'processing' to claim them.

    This ensures that multiple worker processes don't work on the same page
    simultaneously.

    Args:
        session: Database session
        limit: Maximum number of pages to return

    Returns:
        List of page IDs that were successfully claimed
    """
    # Step 1: Identify candidate issues and lock them
    # We query for up to limit * 10 issues to get a good number of unique pages
    candidates_result = await session.execute(
        text("""
            SELECT psi.id, psi.page_id
            FROM page_spell_issues psi
            INNER JOIN auto_correct_rules scc ON psi.word = scc.misspelled_word
            WHERE psi.status = 'open'
              AND scc.is_active = true
              AND psi.char_offset IS NOT NULL
              AND psi.char_end IS NOT NULL
            LIMIT :issue_limit
            FOR UPDATE OF psi SKIP LOCKED
        """),
        {"issue_limit": limit * 10}
    )
    rows = candidates_result.fetchall()

    if not rows:
        return []

    # Map issue IDs to their page IDs
    unique_page_ids = []
    seen_pages = set()
    claimed_issue_ids = []
    
    for row in rows:
        if row.page_id not in seen_pages:
            if len(unique_page_ids) >= limit:
                break
            unique_page_ids.append(row.page_id)
            seen_pages.add(row.page_id)
        
        # Only claim issues for the pages we are actually returning
        if row.page_id in seen_pages:
            claimed_issue_ids.append(row.id)

    if not claimed_issue_ids:
        return []

    # Step 2: Mark the relevant 'open' issues as 'processing'
    # This officially "claims" them for the worker.
    await session.execute(
        update(PageSpellIssue)
        .where(PageSpellIssue.id.in_(claimed_issue_ids))
        .values(
            status="processing",
            claimed_at=func.now()
        )
    )

    # Commit to release the locks and save the 'processing' status
    await session.commit()

    return unique_page_ids


async def get_auto_correction_stats(session: AsyncSession) -> Dict:
    """
    Get statistics about auto-corrections.

    Returns:
        Dictionary with statistics:
        - total_rules: Total number of correction rules
        - active_rules: Number of rules with is_active=True
        - total_auto_corrected: Total issues that have been auto-corrected
        - pending_corrections: Number of open issues that match correction rules
    """
    # Total correction rules
    total_rules_result = await session.execute(
        select(func.count()).select_from(AutoCorrectRule)
    )
    total_rules = total_rules_result.scalar() or 0

    # Active correction rules
    active_rules_result = await session.execute(
        select(func.count())
        .select_from(AutoCorrectRule)
        .where(AutoCorrectRule.is_active)
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
            INNER JOIN auto_correct_rules scc ON psi.word = scc.misspelled_word
            WHERE psi.status = 'open'
              AND scc.is_active = true
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


async def cleanup_stale_auto_corrections(
    session: AsyncSession,
    timeout_minutes: int = 15
) -> int:
    """
    Revert 'processing' issues that have been stuck for too long back to 'open'.
    This handles cases where a worker crashed while processing a page.

    Args:
        session: Database session
        timeout_minutes: How long to wait before considering an issue stuck

    Returns:
        Number of issues reverted
    """
    result = await session.execute(
        update(PageSpellIssue)
        .where(
            and_(
                PageSpellIssue.status == "processing",
                PageSpellIssue.claimed_at < func.now() - text(f"interval '{timeout_minutes} minutes'")
            )
        )
        .values(status="open")
    )
    await session.commit()
    return result.rowcount
