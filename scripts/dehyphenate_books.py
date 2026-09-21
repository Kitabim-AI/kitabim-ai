#!/usr/bin/env python3
"""Operational Backfill Script: Global De-Hyphenation for Existing Books.

Scans pages with hyphenated Uyghur words ('-' or '-\\n') and applies the global
de-hyphenation rule:
1. cand_hyphen (p1-p2) does NOT exist in the 'words' dictionary.
2. cand_merged (p1p2) DOES exist in the 'words' dictionary.

When a page's text is modified:
- Updates page.text with the merged spelling.
- Resets chunking_milestone = 'idle', embedding_milestone = 'idle', is_indexed = False.
- Deletes stale PageSpellIssue records for that page.
- Resets spell_check_milestone = 'idle' so the spell-check worker re-evaluates the clean text.

Usage:
    # Dry run across all books (report only, no writes):
    python scripts/dehyphenate_books.py --dry-run

    # Dry run on a specific book:
    python scripts/dehyphenate_books.py --dry-run --book-id <book-id>

    # Apply backfill to a specific book:
    python scripts/dehyphenate_books.py --book-id <book-id>

    # Apply backfill to all books with batch size 100:
    python scripts/dehyphenate_books.py --batch-size 100
"""

import argparse
import asyncio
import logging
import time
from collections import Counter
from typing import Set

from sqlalchemy import delete, func, select, text, update

from app.db import session as db_session
from app.db.models import Page, PageSpellIssue
from app.utils.text import (
    _DEHYPHEN_INLINE_RE,
    _DEHYPHEN_NL_RE,
    dehyphenate_uyghur_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("dehyphenate_books")


async def load_all_words(session) -> Set[str]:
    """Pre-load all dictionary words into a memory set for lightning-fast lookups."""
    logger.info("Loading dictionary words from 'words' table...")
    t0 = time.perf_counter()
    result = await session.execute(text("SELECT word FROM words"))
    words = {row[0] for row in result.fetchall()}
    duration = time.perf_counter() - t0
    logger.info("Loaded %d dictionary words in %.2fs", len(words), duration)
    return words


async def main():
    parser = argparse.ArgumentParser(
        description="Global auto-correction line-break de-hyphenation backfill script."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate changes without writing to database.",
    )
    parser.add_argument(
        "--book-id",
        type=str,
        default=None,
        help="Optional specific book ID to process.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate pages to scan.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Commit batch size (default: 100 pages).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed word replacement samples.",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("Kitabim.AI: Global Auto-Correction De-Hyphenation Backfill")
    print(
        f"Mode: {'DRY RUN (read-only)' if args.dry_run else 'APPLY CHANGES (writes enabled)'}"
    )
    if args.book_id:
        print(f"Target Book ID: {args.book_id}")
    print("=" * 65)

    await db_session.init_db()

    start_time = time.perf_counter()
    scanned_pages = 0
    modified_pages = 0
    total_replacements = 0
    word_change_counter: Counter[str] = Counter()
    modified_book_ids: Set[str] = set()

    async with db_session.async_session_factory() as session:
        valid_words = await load_all_words(session)

        # Build candidate page query
        query = (
            select(Page.id, Page.book_id, Page.page_number, Page.text)
            .where(
                Page.text.like("%-%"),
            )
            .order_by(Page.book_id, Page.page_number)
        )

        if args.book_id:
            query = query.where(Page.book_id == args.book_id)
        if args.limit:
            query = query.limit(args.limit)

        logger.info("Querying candidate pages containing '-'...")
        result = await session.execute(query)
        candidates = result.fetchall()
        logger.info("Found %d candidate page(s) containing hyphens.", len(candidates))

        pending_updates = 0

        for page_id, book_id, page_number, raw_text in candidates:
            scanned_pages += 1
            if not raw_text:
                continue

            cleaned_text, repl_count = dehyphenate_uyghur_text(
                raw_text, lambda w: w in valid_words
            )

            if repl_count > 0:
                modified_pages += 1
                total_replacements += repl_count
                modified_book_ids.add(book_id)

                # Track word changes for reporting
                for m in _DEHYPHEN_NL_RE.finditer(raw_text):
                    p1, p2 = m.group(1), m.group(2)
                    ch, cm = f"{p1}-{p2}", f"{p1}{p2}"
                    if ch not in valid_words and cm in valid_words:
                        word_change_counter[f"{ch} -> {cm}"] += 1

                for m in _DEHYPHEN_INLINE_RE.finditer(raw_text):
                    p1, p2 = m.group(1), m.group(2)
                    ch, cm = f"{p1}-{p2}", f"{p1}{p2}"
                    if ch not in valid_words and cm in valid_words:
                        word_change_counter[f"{ch} -> {cm}"] += 1

                if args.verbose or modified_pages <= 5:
                    logger.info(
                        "Page %s (book: %s): %d de-hyphenation(s)",
                        page_number,
                        book_id,
                        repl_count,
                    )

                if not args.dry_run:
                    # 1. Update page text and reset milestones
                    await session.execute(
                        update(Page)
                        .where(Page.id == page_id)
                        .values(
                            text=cleaned_text,
                            chunking_milestone="idle",
                            embedding_milestone="idle",
                            is_indexed=False,
                            spell_check_milestone="idle",
                            last_updated=func.now(),
                        )
                    )
                    # 2. Delete stale spell check issues for this page
                    await session.execute(
                        delete(PageSpellIssue).where(PageSpellIssue.page_id == page_id)
                    )
                    pending_updates += 1

                    if pending_updates >= args.batch_size:
                        await session.commit()
                        logger.info(
                            "Committed batch of %d modified pages.", pending_updates
                        )
                        pending_updates = 0

        if not args.dry_run and pending_updates > 0:
            await session.commit()
            logger.info("Committed final batch of %d modified pages.", pending_updates)

    elapsed = time.perf_counter() - start_time
    print("\n" + "=" * 65)
    print("BACKFILL SUMMARY")
    print("=" * 65)
    print(f"Candidate pages scanned:  {scanned_pages}")
    print(f"Pages modified:           {modified_pages}")
    print(f"Total words de-hyphenated:{total_replacements}")
    print(f"Books affected:           {len(modified_book_ids)}")
    print(f"Elapsed time:             {elapsed:.2f}s")
    if word_change_counter:
        print("\nTop word replacements:")
        for pair, cnt in word_change_counter.most_common(15):
            print(f"  - {pair} ({cnt}x)")
    if args.dry_run:
        print(
            "\n[Dry Run] No database changes were written. Remove '--dry-run' to execute."
        )
    else:
        print("\n[Complete] Database successfully updated.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
