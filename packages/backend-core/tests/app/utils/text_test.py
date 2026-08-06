from app.utils.text import (
    normalize_uyghur_chars,
    clean_uyghur_text,
    generate_uyghur_regex,
)


def test_normalize_uyghur_chars():
    # Presentation forms
    assert normalize_uyghur_chars("\ufb8a") == "ژ"
    # ZWNJ, ZWJ, ZWS, Tatweel
    assert normalize_uyghur_chars("u\u200cyghur\u200d\u200b\u0640") == "uyghur"
    # Yeh + Hamza
    assert normalize_uyghur_chars("\u064a\u0654") == "\u0626"
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


def test_clean_uyghur_text_strips_ocr_markers():
    # Marker alone on its own line is dropped entirely
    text = "line one\n[Footer] 3\nline two"
    cleaned = clean_uyghur_text(text)
    assert "[Footer]" not in cleaned
    assert "line one" in cleaned
    assert "line two" in cleaned

    # Marker glued to the end of a real content line: content before it is
    # kept, the marker and everything after it is dropped
    text = "بۇ جۈملە.[Footer] 3"
    cleaned = clean_uyghur_text(text)
    assert "[Footer]" not in cleaned
    assert "بۇ جۈملە." in cleaned

    # [Header] variant, case-insensitive
    text = "content[header] 12"
    cleaned = clean_uyghur_text(text)
    assert "[header]" not in cleaned.lower()
    assert "content" in cleaned


def test_generate_uyghur_regex():
    # Hamza seat mapping
    reg = generate_uyghur_regex("\u0626")
    assert reg == "(\u0626|\u064a\u0654)"

    reg2 = generate_uyghur_regex("\u064a\u0654")
    assert reg2 == "(\u0626|\u064a\u0654)"

    # Regex escape
    reg3 = generate_uyghur_regex("word.")
    assert "word\\." in reg3

    # Empty
    assert generate_uyghur_regex("") == ""
