import pytest
from app.utils.text import clean_uyghur_text

def test_clean_uyghur_text_empty():
    assert clean_uyghur_text("") == ""
    assert clean_uyghur_text(None) == ""

def test_clean_uyghur_text_hyphen_join():
    # Words split by hyphen at end of line
    text = "يۇقىرى- \n كۆتۈرۈلدى"
    assert clean_uyghur_text(text) == "يۇقىرىكۆتۈرۈلدى"
    
    # Standardize hyphens at line ends
    text = "بۇ بىر سىناق- \n جۈملە."
    assert clean_uyghur_text(text) == "بۇ بىر سىناقجۈملە."

def test_clean_uyghur_text_tatweels():
    text = "ســـ\nلام"
    assert clean_uyghur_text(text) == "سلام"

def test_clean_uyghur_text_paragraph_preservation():
    text = "بىرىنچى پاراگراف.\n\nئىككىنچى پاراگراف."
    result = clean_uyghur_text(text)
    assert "بىرىنچى پاراگراف." in result
    assert "ئىككىنچى پاراگراف." in result
    assert "\n\n" in result

def test_clean_uyghur_text_sentence_joining():
    # Sentences that are not finished should be joined by space
    text = "بۇ بىر ئۇزۇن\nجۈملىنىڭ باشلىنىشى."
    # The current logic joins with space if it doesn't end with punctuation
    assert clean_uyghur_text(text) == "بۇ بىر ئۇزۇن جۈملىنىڭ باشلىنىشى."

def test_clean_uyghur_text_sentence_splitting():
    # Sentences that are finished should stay on separate lines or be separated correctly
    text = "بۇ بىرىنچى جۈملە.\nبۇ ئىككىنچى جۈملە!"
    # The logic adds \n if is_ending is true
    assert clean_uyghur_text(text) == "بۇ بىرىنچى جۈملە.\nبۇ ئىككىنچى جۈملە!"

def test_clean_uyghur_text_bullet_points():
    text = "تۆۋەندىكىلەر:\n1. بىرىنچى\n2. ئىككىنچى"
    result = clean_uyghur_text(text)
    assert "1. بىرىنچى" in result
    assert "2. ئىككىنچى" in result
