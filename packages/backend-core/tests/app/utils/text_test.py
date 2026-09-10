from app.utils.text import (
    normalize_uyghur_chars,
    correct_uyghur_ocr_orthography,
    clean_uyghur_text,
    generate_uyghur_regex,
    is_degenerate_ocr_output,
    is_poem_block,
)


def test_is_degenerate_ocr_output():
    assert is_degenerate_ocr_output("") is False
    assert is_degenerate_ocr_output("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False

    # Runaway repetition
    text = " ".join(["المجتمع"] * 25 + ["ئادەتتىكى", "تېكىست", "مەزمۇن"] * 20)
    assert is_degenerate_ocr_output(text) is True


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


def test_is_poem_block():
    stanzas = [
        "غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،",
        "مېنى كىم كۆرسە پەرق ئەتمەس خازاندىن لالىزارمىنى .",
        "ئاقار سەل ئورنىدا ياشىم، غېرىب بولدى ئەزىز باشىم،",
        "ماڭا تار ئەيلىدى چۈنكى بۇ دەۋران ئۆز دىيارمىنى .",
    ]
    assert is_poem_block(stanzas) is True
    assert is_poem_block(stanzas, width_ratio=0.62) is True

    couplet = [
        "ئەي ئەزىزىم، قەدرىمگە يەتسەڭچۇ سەن،",
        "بۇ جاھاندا مەندەك ۋاپادار كەم سەن.",
    ]
    assert is_poem_block(couplet) is True

    prose = [
        "خەيرىيەت، ئەمدى تاھارىتىڭنى ئال. مەن نامىزىمنى ئۆتۈۋېرەي، -",
        "دېدى شېرىكى كۈلۈمسىرەپ ئۇنىڭغا پىسەنت قىلماي.",
    ]
    assert is_poem_block(prose) is False


def test_clean_uyghur_text_preserves_poem_lines():
    poem = (
        "غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،\n"
        "مېنى كىم كۆرسە پەرق ئەتمەس خازاندىن لالىزارمىنى .\n"
        "ئاقار سەل ئورنىدا ياشىم، غېرىب بولدى ئەزىز باشىم،\n"
        "ماڭا تار ئەيلىدى چۈنكى بۇ دەۋران ئۆز دىيارمىنى ."
    )
    cleaned = clean_uyghur_text(poem)
    lines = cleaned.split("\n")
    assert len(lines) == 4
    assert "غېبى جانان" in lines[0]
    assert "مېنى كىم كۆرسە" in lines[1]
    assert "غېرىپ بولدى ئەزىز باشىم" in lines[2]


def test_correct_uyghur_ocr_orthography():
    assert (
        correct_uyghur_ocr_orthography("مەكتەب ۋە مەكتەبلەر") == "مەكتەپ ۋە مەكتەپلەر"
    )
    assert (
        correct_uyghur_ocr_orthography("مەنسەب ۋە مەنسەبدار") == "مەنسەپ ۋە مەنسەپدار"
    )
    assert correct_uyghur_ocr_orthography("تەلەب قىلدى") == "تەلەپ قىلدى"
    assert correct_uyghur_ocr_orthography("كەسىبداشلار كەسىبى") == "كەسىپداشلار كەسىبى"
    assert (
        correct_uyghur_ocr_orthography("ئەدەبسىز ئەدەبىيات ئەدەبىي")
        == "ئەدەپسىز ئەدەبىيات ئەدەبىي"
    )
    assert (
        correct_uyghur_ocr_orthography("غېرىب غېرىبلىق غېرىبى")
        == "غېرىپ غېرىپلىق غېرىبى"
    )
    assert (
        correct_uyghur_ocr_orthography("ئەجەب ئىش ۋە ئەجەبلەنمەك")
        == "ئەجەپ ئىش ۋە ئەجەبلەنمەك"
    )
    assert (
        correct_uyghur_ocr_orthography("خازاندىن لالىزارىمنى") == "خازاندىن لالىزارىمنى"
    )
    assert (
        correct_uyghur_ocr_orthography("خازاندىن لالىزار ئەيلىدى")
        == "خازاندىن لالەزار ئەيلىدى"
    )
    assert correct_uyghur_ocr_orthography("") == ""
