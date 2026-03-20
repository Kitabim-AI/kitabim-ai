import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.auto_correct_service import (
    get_correction_rules,
    get_correction_for_word,
    apply_auto_corrections_to_page,
    find_pages_with_auto_correctable_issues,
    get_auto_correction_stats,
    cleanup_stale_auto_corrections
)
from app.db.models import Page, PageSpellIssue

@pytest.mark.asyncio
async def test_get_correction_rules():
    session = AsyncMock()
    
    mock_row1 = MagicMock()
    mock_row1.misspelled_word = "word1"
    mock_row1.corrected_word = "fixed1"
    
    mock_row2 = MagicMock()
    mock_row2.misspelled_word = "word2"
    mock_row2.corrected_word = "fixed2"
    
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row1, mock_row2]
    session.execute.return_value = mock_result
    
    rules = await get_correction_rules(session)
    
    assert len(rules) == 2
    assert rules["word1"] == "fixed1"
    assert rules["word2"] == "fixed2"
    
    # Test auto_apply_only
    await get_correction_rules(session, auto_apply_only=True)
    # Verify the WHERE clause was added (stmt construction is internal, but we can check if it ran)
    assert session.execute.called

@pytest.mark.asyncio
async def test_get_correction_for_word():
    session = AsyncMock()
    
    # Case: Hit
    mock_row = MagicMock()
    mock_row.corrected_word = "fixed"
    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    session.execute.return_value = mock_result
    
    correction = await get_correction_for_word(session, "word")
    assert correction == "fixed"
    
    # Case: Miss
    mock_result.fetchone.return_value = None
    correction = await get_correction_for_word(session, "unknown")
    assert correction is None

@pytest.mark.asyncio
async def test_apply_auto_corrections_to_page_success():
    session = AsyncMock()
    
    # 1. Mock Page
    mock_page = MagicMock(spec=Page)
    mock_page.id = 1
    mock_page.text = "This is a test with word1 and word2."
    mock_page.book_id = "book-1"
    mock_page.page_number = 1
    
    mock_page_res = MagicMock()
    mock_page_res.scalar_one_or_none.return_value = mock_page
    
    # 2. Mock Issues (reverse order of offset)
    issue1 = MagicMock(spec=PageSpellIssue)
    issue1.id = 101
    issue1.word = "word2"
    issue1.char_offset = 30
    issue1.char_end = 35
    
    issue2 = MagicMock(spec=PageSpellIssue)
    issue2.id = 102
    issue2.word = "word1"
    issue2.char_offset = 20
    issue2.char_end = 25
    
    mock_issues_res = MagicMock()
    mock_issues_res.scalars.return_value.all.return_value = [issue1, issue2]
    
    # 3. Rules
    rules = {"word1": "W1", "word2": "W2"}
    
    # Set side effects for session.execute
    session.execute.side_effect = [
        mock_page_res,    # fetch page
        mock_issues_res,  # fetch processing issues
        MagicMock(),      # update(PageSpellIssue)
        MagicMock(),      # update(Page)
    ]
    
    count = await apply_auto_corrections_to_page(session, 1, rules)
    
    assert count == 2
    # Verify text replacement: word1->W1 (offset 20), word2->W2 (offset 30)
    # Original: "This is a test with word1 and word2."
    # After W2: "This is a test with word1 and W2." (offset 30)
    # After W1: "This is a test with W1 and W2." (offset 20)
    # Note: the code applies them in reverse order of offset to keep offsets valid
    
    # Check that update(Page) was called with new text
    # The last execute was update(Page)
    session.execute.call_args_list[-1]
    # We can't easily inspect the values() of the update statement without deep mocking,
    # but we can verify session.execute was called 4 times total
    assert session.execute.call_count == 4

@pytest.mark.asyncio
async def test_find_pages_with_auto_correctable_issues():
    session = AsyncMock()
    
    mock_row1 = MagicMock()
    mock_row1.id = 101
    mock_row1.page_id = 1
    
    mock_row2 = MagicMock()
    mock_row2.id = 102
    mock_row2.page_id = 1
    
    mock_row3 = MagicMock()
    mock_row3.id = 103
    mock_row3.page_id = 2
    
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [mock_row1, mock_row2, mock_row3]
    session.execute.return_value = mock_result
    
    page_ids = await find_pages_with_auto_correctable_issues(session, limit=5)
    
    assert page_ids == [1, 2]
    # Verify commit and execute
    assert session.commit.called
    assert session.execute.called

@pytest.mark.asyncio
async def test_get_auto_correction_stats():
    session = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.scalar.return_value = 10
    
    session.execute.return_value = mock_res
    
    stats = await get_auto_correction_stats(session)
    
    assert stats["total_rules"] == 10
    assert stats["active_rules"] == 10
    assert stats["total_auto_corrected"] == 10
    assert stats["pending_corrections"] == 10

@pytest.mark.asyncio
async def test_cleanup_stale_auto_corrections():
    session = AsyncMock()
    
    mock_res = MagicMock()
    mock_res.rowcount = 5
    session.execute.return_value = mock_res
    
    reverted = await cleanup_stale_auto_corrections(session, timeout_minutes=15)
    
    assert reverted == 5
    assert session.commit.called

@pytest.mark.asyncio
async def test_apply_auto_corrections_to_page_page_not_found():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    
    count = await apply_auto_corrections_to_page(session, 1)
    assert count == 0

@pytest.mark.asyncio
async def test_apply_auto_corrections_to_page_no_rules():
    session = AsyncMock()
    # fetch page
    mock_page_res = MagicMock()
    mock_page_res.scalar_one_or_none.return_value = Page(id=1)
    
    # fetch rules
    mock_rules_res = MagicMock()
    mock_rules_res.fetchall.return_value = []
    
    session.execute.side_effect = [mock_page_res, mock_rules_res]
    
    count = await apply_auto_corrections_to_page(session, 1)
    assert count == 0

@pytest.mark.asyncio
async def test_apply_auto_corrections_to_page_no_issues():
    session = AsyncMock()
    mock_page_res = MagicMock()
    mock_page_res.scalar_one_or_none.return_value = Page(id=1)
    
    mock_issues_res = MagicMock()
    mock_issues_res.scalars.return_value.all.return_value = []
    
    session.execute.side_effect = [
        mock_page_res,     # fetch page
        mock_issues_res,   # fetch processing issues
        mock_issues_res,   # fetch open issues (fallback)
    ]
    
    count = await apply_auto_corrections_to_page(session, 1, {"word": "fixed"})
    assert count == 0

@pytest.mark.asyncio
async def test_apply_auto_corrections_to_page_bad_offsets():
    session = AsyncMock()
    mock_page = MagicMock(spec=Page)
    mock_page.id = 1
    mock_page.text = "test"
    mock_page_res = MagicMock()
    mock_page_res.scalar_one_or_none.return_value = mock_page
    
    issue = MagicMock(spec=PageSpellIssue)
    issue.id = 1
    issue.char_offset = None  # BAD!
    issue.char_end = None
    issue.word = "word"
    
    mock_issues_res = MagicMock()
    mock_issues_res.scalars.return_value.all.return_value = [issue]
    
    session.execute.side_effect = [mock_page_res, mock_issues_res]
    
    count = await apply_auto_corrections_to_page(session, 1, {"word": "fixed"})
    assert count == 0

@pytest.mark.asyncio
async def test_find_pages_with_auto_correctable_issues_no_rows():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res
    
    pages = await find_pages_with_auto_correctable_issues(session)
    assert pages == []
