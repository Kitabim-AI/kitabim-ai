import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.spell_check_service import (
    ThreadSafeSpellCheckCache,
    find_unknown_words,
    get_ocr_corrections_batch,
    run_spell_check_for_page
)
from app.db.models import Page, PageSpellIssue, SpellCheckCorrection

@pytest.mark.asyncio
async def test_cache_stats():
    cache = ThreadSafeSpellCheckCache()
    cache._stats['unknown_hits'] = 5
    cache._stats['unknown_misses'] = 5
    stats = cache.get_stats()
    assert stats['unknown_words']['hit_rate'] == 0.5

@pytest.mark.asyncio
async def test_find_unknown_words():
    session = AsyncMock()
    cache = ThreadSafeSpellCheckCache()
    
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [("w1",)]
    session.execute.return_value = mock_res
    
    unknown = await find_unknown_words(session, ["w1", "w2"], cache=cache)
    assert "w1" in unknown
    assert "w2" not in unknown

@pytest.mark.asyncio
async def test_get_ocr_corrections_batch():
    session = AsyncMock()
    cache = ThreadSafeSpellCheckCache()
    
    cache.ocr_corrections["w1"] = ["f1"]
    res = await get_ocr_corrections_batch(session, {"w1"}, cache)
    assert res["w1"] == ["f1"]
    
    # DB search
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [("f2",)]
    session.execute.return_value = mock_res
    
    with patch("app.services.spell_check_service.ocr_variants") as mock_v:
        mock_v.return_value = ["f2"]
        with patch("app.services.spell_check_service.insertion_variants") as mock_i:
            mock_i.return_value = []
            res = await get_ocr_corrections_batch(session, {"w2"}, cache)
            assert res["w2"] == ["f2"]

@pytest.mark.asyncio
async def test_run_spell_check_for_page_with_issues():
    session = AsyncMock()
    # Uyghur: "خاتا" (khata) and "نامەلۇم" (unknown)
    page = Page(id=1, text="خاتا نامەلۇم", book_id="b1")
    
    # 1. Mock Rules: "خاتا" -> "توغرا" (correct)
    mock_rules_row = MagicMock()
    mock_rules_row.misspelled_word = "خاتا"
    mock_rules_row.corrected_word = "توغرا"
    mock_rules_res = MagicMock()
    mock_rules_res.fetchall.return_value = [mock_rules_row]
    
    # 2. find_unknown_words for ["توغرا", "نامەلۇم"]
    # Let's say "نامەلۇم" is unknown
    mock_unknown_res = MagicMock()
    mock_unknown_res.fetchall.return_value = [("نامەلۇم",)]
    
    # 3. get_ocr_corrections_batch for ["نامەلۇم"] -> returns {"نامەلۇم": ["پىلان"]}
    mock_ocr_db_res = MagicMock()
    mock_ocr_db_res.fetchall.return_value = [("پىلان",)]
    
    session.execute.side_effect = [
        mock_rules_res,    # fetch rules
        mock_unknown_res,  # find unknown words
        mock_ocr_db_res,   # dict lookup for ocr variants
        MagicMock(),       # delete
        MagicMock(),       # update
    ]
    
    with patch("app.services.spell_check_service.ocr_variants") as mock_v:
        mock_v.return_value = ["پىلان"]
        with patch("app.services.spell_check_service.insertion_variants") as mock_i:
            mock_i.return_value = []
            
            count = await run_spell_check_for_page(session, page)
            
            assert count == 1
            # "توغرا" is in text
            assert "توغرا" in page.text
            assert session.add_all.called
            issues = session.add_all.call_args[0][0]
            assert issues[0].word == "نامەلۇم"
            assert issues[0].ocr_corrections == ["پىلان"]

@pytest.mark.asyncio
async def test_run_spell_check_for_page_no_tokens():
    session = AsyncMock()
    page = Page(id=1, text="", book_id="b1")
    
    mock_rules_res = MagicMock()
    mock_rules_res.fetchall.return_value = []
    
    session.execute.side_effect = [
        mock_rules_res,
        MagicMock(),
    ]
    
    count = await run_spell_check_for_page(session, page)
    assert count == 0
