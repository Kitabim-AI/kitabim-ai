import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.spell_check_service import (
    ocr_variants, 
    insertion_variants,
)

def test_ocr_variants():
    # Test with a word that contains characters from _OCR_PAIRS
    # \u0626 is ئ, \u0649 is ى
    word = "\u0643" # ك (k)
    variants = ocr_variants(word)
    # _OCR_PAIRS has ("\u0643", "\u06AD", "ك→ڭ")
    assert "\u06AD" in variants
    
    # Double substitution
    word2 = "\u0643\u0643"
    variants2 = ocr_variants(word2)
    assert len(variants2) > 0

def test_insertion_variants():
    word = "ABC"
    variants = insertion_variants(word)
    # len(word)+1 positions * len(_VOWEL_INSERTIONS)
    # _VOWEL_INSERTIONS has 5 elements now (lines 169-175)
    assert len(variants) == (len(word) + 1) * 5 
    assert " ABC" not in variants

@pytest.mark.asyncio
async def test_insertion_variants_uyghur():
    word = "مكتەب"
    variants = insertion_variants(word)
    assert len(variants) > 0
