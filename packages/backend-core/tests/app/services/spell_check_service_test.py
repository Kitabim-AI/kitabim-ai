import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.spell_check_service import (
    ThreadSafeSpellCheckCache,
    classify_transform,
    find_unknown_words,
    get_ocr_corrections_batch,
    run_spell_check_for_page,
    score_confidence,
)
from app.db.models import Page


@pytest.fixture(autouse=True)
def mock_cache_service():
    with patch("app.services.spell_check_service.cache_service") as mock:
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        yield mock


@pytest.mark.asyncio
async def test_cache_stats():
    cache = ThreadSafeSpellCheckCache()
    cache._stats["unknown_hits"] = 5
    cache._stats["unknown_misses"] = 5
    stats = cache.get_stats()
    assert stats["unknown_words"]["hit_rate"] == 0.5


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
    session.add_all = MagicMock()
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
        mock_rules_res,  # fetch rules
        mock_unknown_res,  # find unknown words
        mock_ocr_db_res,  # dict lookup for ocr variants
        MagicMock(),  # delete
        MagicMock(),  # update
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


def test_classify_transform_single_substitution():
    # و -> ۇ is a known OCR-confusable pair; one occurrence swapped.
    assert classify_transform("بو", "بۇ") == "substitution_1"


def test_classify_transform_double_substitution():
    # Both occurrences of و swapped requires two rounds of _apply_single.
    assert classify_transform("وو", "ۇۇ") == "substitution_2"


def test_classify_transform_insertion():
    # Any length mismatch is classified as insertion, regardless of content.
    assert classify_transform("سوز", "سووز") == "insertion"


def test_score_confidence_weight_ordering():
    # Same original ("وو") and candidate_count: substitution_1 > substitution_2 > insertion.
    single = score_confidence("بو", "بۇ", candidate_count=1)
    double = score_confidence("وو", "ۇۇ", candidate_count=1)
    insertion = score_confidence("وو", "ووو", candidate_count=1)
    assert single > double > insertion


def test_score_confidence_length_weight_caps_at_one():
    long_word = "تولۇقلاشتۇرۇش"  # 13 chars, well over the length_weight=1.0 cap of 8
    assert len(long_word) >= 8
    score = score_confidence(long_word, long_word[:-1] + "ۇ", candidate_count=1)
    # length_weight should be capped at 1.0, not scale past it
    assert score <= 1.0


def test_score_confidence_count_weight_scales_down():
    one_candidate = score_confidence("بو", "بۇ", candidate_count=1)
    two_candidates = score_confidence("بو", "بۇ", candidate_count=2)
    # Rounded to 2 decimals, so allow for rounding error rather than exact halving.
    assert two_candidates == pytest.approx(one_candidate / 2, abs=0.01)
    assert two_candidates < one_candidate


def test_score_confidence_rounds_to_two_decimals():
    score = score_confidence("بو", "بۇ", candidate_count=3)
    assert score == round(score, 2)


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
