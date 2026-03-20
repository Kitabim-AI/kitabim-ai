from app.utils.text import normalize_uyghur_chars, clean_uyghur_text, generate_uyghur_regex

def test_normalize_uyghur_chars():
    # Presentation forms
    assert normalize_uyghur_chars("\uFB8A") == "ژ"
    # ZWNJ, ZWJ, ZWS, Tatweel
    assert normalize_uyghur_chars("u\u200Cyghur\u200D\u200B\u0640") == "uyghur"
    # Yeh + Hamza
    assert normalize_uyghur_chars("\u064A\u0654") == "\u0626"
    # Empty
    assert normalize_uyghur_chars("") == ""

def test_clean_uyghur_text():
    # Hyphen at line end
    text = "بۇ كىت-\nاب"
    # Note: re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    # The hyphen is removed
    assert "بۇ كىتاب" in clean_uyghur_text(text)
    
    # Paragraph splitting
    text = "P1 line 1\nP1 line 2\n\nP2"
    cleaned = clean_uyghur_text(text)
    assert "P1 line 1 P1 line 2" in cleaned
    assert "P2" in cleaned
    assert "\n\n" in cleaned
    
    # List markers
    text = "- item 1\n- item 2"
    cleaned = clean_uyghur_text(text)
    assert "- item 1\n- item 2" in cleaned
    
    # Empty
    assert clean_uyghur_text("") == ""

def test_generate_uyghur_regex():
    # Hamza seat mapping
    reg = generate_uyghur_regex("\u0626")
    assert reg == "(\u0626|\u064A\u0654)"
    
    reg2 = generate_uyghur_regex("\u064A\u0654")
    assert reg2 == "(\u0626|\u064A\u0654)"
    
    # Regex escape
    reg3 = generate_uyghur_regex("word.")
    assert "word\\." in reg3
    
    # Empty
    assert generate_uyghur_regex("") == ""
