from app.utils.text import (
    clean_uyghur_text,
    correct_uyghur_ocr_orthography,
    generate_uyghur_regex,
    is_degenerate_ocr_output,
    is_key_value_line,
    is_metadata_or_key_value_block,
    is_poem_block,
    normalize_uyghur_chars,
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

    question_couplet = [
        "يا سېنىڭكى ئۆگەي ئاناڭ دىل ئازار قىلدىمۇ؟",
        "ياكى قوغلاپ ئۆيدىن سېنى، خارۇزار قىلدىمۇ؟",
    ]
    assert is_poem_block(question_couplet) is True

    ocr_question_couplet = [
        "يا سېنىڭكى ئۆگەي ئاناڭ دىل ئازار قىلدىمۇم",
        "ياكى قوغلاپ ئۆيدىن سېنى، خارۇزار قىلدىمۇم",
    ]
    assert is_poem_block(ocr_question_couplet) is True

    rhyme_couplet = [
        "ئاقتى بۇلاق تاغ باغرىدا شارقىراپ",
        "ياشلار كېلەر مەيدانلاردا پارقىراپ",
    ]
    assert is_poem_block(rhyme_couplet) is True

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
    assert correct_uyghur_ocr_orthography("دىل ئازار قىلدىمۇم") == "دىل ئازار قىلدىمۇ؟"
    assert correct_uyghur_ocr_orthography("") == ""


def test_is_key_value_line():
    assert is_key_value_line("ئاپتورى : ئابدۇرىھىم ئۆتكۈر") is True
    assert is_key_value_line("مەسئۇل كۇررېكتورى: گۈلشەھەر نېغمەت") is True
    assert is_key_value_line("باھاسى : 18.00 يۈەن") is True
    assert is_key_value_line("ISBN: 978-7-228-11683-6") is True
    # Dialogue and prose clauses should be rejected
    assert is_key_value_line("ئەخمەت دېدى: قېنى كىرىڭلار!") is False
    assert is_key_value_line("ئۇ كۈلۈپ تۇرۇپ مۇنداق دېدى: ماقۇل") is False
    assert is_key_value_line("ئانىسى سورىدى: قاچان كېلىسەن؟") is False


def test_is_metadata_or_key_value_block():
    colophon_lines = [
        "ئاپتورى : ئابدۇرىھىم ئۆتكۈر",
        "مەسئۇل مۇھەررىرى : ئابدۇراخمان ئەبەي ، ئەزىز توردى",
        "تېخنىكىلىق كۇررېكتورى : ئەلى زەيدۇن",
        "نەشر قىلىپ تارقاتقۇچى : شىنجاڭ خەلق نەشرىياتى",
        "تېلېفون : 0991_2827472",
        "باھاسى : 18.00 يۈەن",
    ]
    assert is_metadata_or_key_value_block(colophon_lines) is True

    # Standard prose paragraph with 1 colon should be False
    prose_lines = [
        "ئۇ كەچلىك شەپەقكە قاراپ تۇرۇپ مۇنداق دېدى: ھاۋا ناھايىتى گۈزەل بولدى.",
        "بىز ئەتە يەنە مۇشۇ تاغ باغرىغا كېلىپ سەيلە قىلايلى.",
        "ئۇلار ئۆيگە قاراپ ماڭدى.",
    ]
    assert is_metadata_or_key_value_block(prose_lines) is False


def test_clean_uyghur_text_preserves_colophon_and_metadata_lines():
    colophon_text = (
        "ئاپتورى : ئابدۇرىھىم ئۆتكۈر\n"
        "مەسئۇل مۇھەررىرى : ئابدۇراخمان ئەبەي ، ئەزىز توردى\n"
        "تېخنىكىلىق كۇررېكتورى : ئەلى زەيدۇن\n"
        "باھاسى : 18.00 يۈەن"
    )
    cleaned = clean_uyghur_text(colophon_text)
    lines = cleaned.split("\n")
    assert len(lines) == 4
    assert lines[0] == "ئاپتورى : ئابدۇرىھىم ئۆتكۈر"
    assert lines[1] == "مەسئۇل مۇھەررىرى : ئابدۇراخمان ئەبەي ، ئەزىز توردى"
    assert lines[2] == "تېخنىكىلىق كۇررېكتورى : ئەلى زەيدۇن"
    assert lines[3] == "باھاسى : 18.00 يۈەن"


def test_clean_uyghur_text_merges_multi_sentence_prose_paragraph():
    prose = (
        "سارغۇجىدا ئەنەلەر سۇ توشۇمايتتى، قازان بېشىغا ئارىلاشمايتتى، سۇ توشۇش، ئوتۇن يېرىش ئىشلىرى توي\n"
        "ئىشىغا كىرەتتى. ئوي ئىشىنى بولسا، ئاياللار قىلاتتى، ئەرلەر تالا ئىشىنى، ئېتىز - ئېرىق، مال -\n"
        "ۋارانغا قاراش، چۆپ چېپىش، ئوتۇن تارتىش، ئوبىنىك كەم - كۇسىنى تەييارلاپ بېرىشتەك ئىشلارنى\n"
        "قىلاتتى. كۈنلەر مۇشۇ تەرىقىدە ئۆتۈۋەردى."
    )
    cleaned = clean_uyghur_text(prose)
    assert "\n" not in cleaned
    assert "كىرەتتى. ئوي ئىشىنى بولسا" in cleaned
    assert "مال - ۋارانغا قاراش" in cleaned
    assert "قىلاتتى. كۈنلەر" in cleaned


def test_clean_uyghur_text_prose_dialogue_separation():
    mixed = (
        "ئەرلەر قازان بېشىغا ئارىلىشىپ قالسا، ئاياللار: - چىپىلمىسىلا، - دەپ قازان بېشىدىن\n"
        "ھەيدىۋېتەتتى. سارغۇجىا ئاياللىرى دىرەنزە، ھويلىلاردىن مارىشىپ قاقاقلاپ كۈلۈشتى:\n"
        "— ياغلىقلا تاڭسا چىرايلىق چوكان بولغۇدەك! - ھا - ھا - ھا!\n"
        "— پۆرمىلىك كۆينەك كىيسە ئېرىگىنى تارتىۋالامدو تېخى!\n"
        "— ۋاھ - ھا - ھا! ھېيى - ھېي!"
    )
    cleaned = clean_uyghur_text(mixed)
    lines = cleaned.split("\n")
    assert len(lines) == 4
    assert lines[0].endswith("قاقاقلاپ كۈلۈشتى:")
    assert lines[1] == "— ياغلىقلا تاڭسا چىرايلىق چوكان بولغۇدەك! - ھا - ھا - ھا!"
    assert lines[2] == "— پۆرمىلىك كۆينەك كىيسە ئېرىگىنى تارتىۋالامدو تېخى!"
    assert lines[3] == "— ۋاھ - ھا - ھا! ھېيى - ھېي!"
