import pytest
from app.utils.text import normalize_uyghur_chars, clean_uyghur_text, generate_uyghur_regex

def test_normalize_uyghur_chars():
    assert normalize_uyghur_chars("") == ""
    assert normalize_uyghur_chars("ی ه \u064A\u0654") == "ي ە \u0626"
    assert normalize_uyghur_chars("ياخشىمۇسىز") == "ياخشىمۇسىز"

def test_clean_uyghur_text():
    assert clean_uyghur_text("") == ""
    
    # Hyphenated words at line endings
    assert clean_uyghur_text("word-\npart") == "wordpart"
    assert clean_uyghur_text("كىتا-\nب") == "كىتاب"
    
    # Multiple newlines
    assert clean_uyghur_text("Para 1\n\nPara 2") == "Para 1\n\nPara 2"
    
    # Line joins
    assert clean_uyghur_text("first part of line\nsecond part of line") == "first part of line second part of line"
    
    # Markdown list preservation
    assert clean_uyghur_text("- List 1\n- List 2") == "- List 1\n- List 2"
    
    # Header preservation
    assert clean_uyghur_text("# Header\nContent") == "# Header\nContent"

def test_generate_uyghur_regex():
    assert generate_uyghur_regex("") == ""
    
    # Escapes regex chars
    assert generate_uyghur_regex("a.b$") == r"a\.b\$"
    
    # Maps specific characters to alternation groups
    # \u0626 (ء) maps to (\u0626|\u064A\u0654)
    res = generate_uyghur_regex("\u0626")
    assert "(\u0626|\\u064a\\u0654)" in res.lower() or "(\u0626|\u064a\u0654)" in res.lower() or "(\u0626|" in res
