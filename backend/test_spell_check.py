#!/usr/bin/env python3
"""
Test script for spell check service

Usage:
    python test_spell_check.py <book_id> [page_num]

Examples:
    python test_spell_check.py abc123           # Check all pages
    python test_spell_check.py abc123 5         # Check page 5 only
"""

import sys
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.spell_check_service import spell_check_service
from app.db.mongodb import db_manager


async def test_page_check(book_id: str, page_num: int):
    """Test spell checking on a single page"""
    print(f"\n{'='*60}")
    print(f"Testing spell check on Book: {book_id}, Page: {page_num}")
    print(f"{'='*60}\n")
    
    # Connect to database
    await db_manager.connect()
    db = db_manager.db
    
    # Find the book
    book = await db.books.find_one({"id": book_id})
    if not book:
        print(f"❌ Book {book_id} not found")
        return
    
    print(f"📖 Book found: {book.get('title', 'Unknown')}")
    
    # Find the page
    page_result = None
    for page in book.get("results", []):
        if page.get("pageNumber") == page_num:
            page_result = page
            break
    
    if not page_result:
        print(f"❌ Page {page_num} not found")
        return
    
    page_text = page_result.get("text", "")
    if not page_text:
        print(f"❌ Page {page_num} has no text")
        return
    
    print(f"📄 Page {page_num} - Text length: {len(page_text)} characters")
    print(f"\nFirst 200 characters:")
    print(f"{page_text[:200]}...\n")
    
    # Run spell check
    print("🔍 Running spell check...")
    result = await spell_check_service.check_page_text(page_text, page_num)
    
    print(f"\n{'='*60}")
    print(f"✅ Spell Check Results")
    print(f"{'='*60}")
    print(f"Total Issues Found: {result.totalIssues}")
    print(f"Checked At: {result.checkedAt}")
    
    if result.totalIssues > 0:
        print(f"\n📝 Corrections:\n")
        for i, correction in enumerate(result.corrections, 1):
            print(f"{i}. '{correction.original}' → '{correction.corrected}'")
            print(f"   Confidence: {correction.confidence:.1%}")
            print(f"   Reason: {correction.reason}")
            if correction.context:
                print(f"   Context: {correction.context}")
            print()
    else:
        print("\n✅ No spelling issues detected on this page!")
    
    await db_manager.disconnect()


async def test_book_check(book_id: str):
    """Test spell checking on all pages of a book"""
    print(f"\n{'='*60}")
    print(f"Testing spell check on entire book: {book_id}")
    print(f"{'='*60}\n")
    
    # Connect to database
    await db_manager.connect()
    db = db_manager.db
    
    # Find the book
    book = await db.books.find_one({"id": book_id})
    if not book:
        print(f"❌ Book {book_id} not found")
        return
    
    print(f"📖 Book: {book.get('title', 'Unknown')}")
    print(f"📄 Total Pages: {book.get('totalPages', 0)}")
    print(f"\n🔍 Running spell check on all pages...\n")
    
    # Run spell check
    results = await spell_check_service.check_book(book_id, db)
    
    print(f"\n{'='*60}")
    print(f"✅ Spell Check Results")
    print(f"{'='*60}")
    print(f"Pages with Issues: {len(results)} / {book.get('totalPages', 0)}")
    
    if len(results) > 0:
        total_issues = sum(r.totalIssues for r in results.values())
        print(f"Total Issues Found: {total_issues}")
        
        print(f"\n📊 Summary by Page:\n")
        for page_num in sorted(results.keys()):
            result = results[page_num]
            print(f"  Page {page_num}: {result.totalIssues} issues")
        
        print(f"\n📝 All Corrections:\n")
        for page_num in sorted(results.keys()):
            result = results[page_num]
            print(f"  --- Page {page_num} ---")
            for i, correction in enumerate(result.corrections, 1):
                print(f"  {i}. '{correction.original}' → '{correction.corrected}' ({correction.confidence:.1%})")
            print()
    else:
        print("\n✅ No spelling issues detected in this book!")
    
    await db_manager.disconnect()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_spell_check.py <book_id> [page_num]")
        print("\nExamples:")
        print("  python test_spell_check.py abc123           # Check all pages")
        print("  python test_spell_check.py abc123 5         # Check page 5 only")
        sys.exit(1)
    
    book_id = sys.argv[1]
    
    if len(sys.argv) >= 3:
        # Test single page
        page_num = int(sys.argv[2])
        await test_page_check(book_id, page_num)
    else:
        # Test entire book
        await test_book_check(book_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
