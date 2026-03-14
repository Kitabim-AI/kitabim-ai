import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.spell_check_service import (
    ocr_normalize_page, 
    tokenize, 
    ocr_variants, 
    insertion_variants,
    run_spell_check_for_page
)
from app.db.models import Page

def test_ocr_normalize_page():
    # Test ZWNJ removal
    assert ocr_normalize_page("u\u200Cyghur") == "uyghur"
    # Test presentation forms normalization
    # U+FB8A is 'ژ' presentation form
    assert ocr_normalize_page("\uFB8A") == "ژ"

def test_tokenize():
    text = "بۇ بىر سىناق."
    tokens = tokenize(text)
    # "بۇ" (2 chars), "بىر" (3 chars), "سىناق" (5 chars)
    # سىناق is >= 4 chars, others are not (MIN_WORD_LEN=4)
    assert len(tokens) == 1
    word_norm, word_raw, start, end = tokens[0]
    assert word_raw == "سىناق"
    assert text[start:end] == "سىناق"

def test_ocr_variants():
    # "ك" -> "ك", "ڭ", "گ" etc based on _OCR_PAIRS
    variants = ocr_variants("كتاب")
    assert "ڭتاب" in variants
    assert "گتاب" in variants

def test_insertion_variants():
    variants = insertion_variants("كتاب")
    # Should insert vowels at various positions
    # Service uses \u064A (ي) for insertion
    assert "كيتاب" in variants 
    assert "كاتاب" in variants

@pytest.mark.asyncio
async def test_run_spell_check_for_page_no_tokens():
    session = AsyncMock()
    page = Page(id=1, book_id="b1", text="abc") # too short to tokenize
    
    count = await run_spell_check_for_page(session, page)
    
    assert count == 0
    session.execute.assert_called() # Should update milestone to "done"

@pytest.mark.asyncio
async def test_run_spell_check_for_page_with_issues():
    session = AsyncMock()
    # add_all is synchronous in sqlalchemy
    session.add_all = MagicMock()
    
    # Mock find_unknown_words to return our word as unknown
    from app.services import spell_check_service
    
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("app.services.spell_check_service.find_unknown_words", AsyncMock(return_value={"خاتالىق"}))
        mp.setattr("app.services.spell_check_service.get_ocr_corrections_batch", AsyncMock(return_value={}))
        mp.setattr("app.services.spell_check_service.index_book_words", AsyncMock())
        mp.setattr("app.services.spell_check_service.find_words_unique_to_book", AsyncMock(return_value={"خاتالىق"}))
        
        page = Page(id=1, book_id="b1", text="بۇ بىر خاتالىق.") # "خاتالىق" is 6 chars
        count = await run_spell_check_for_page(session, page)
        
        assert count == 1
        # Check if PageSpellIssue was added
        args, _ = session.add_all.call_args
        issues = args[0]
        assert len(issues) == 1
        assert issues[0].word == "خاتالىق"
