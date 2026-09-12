from app.services.rag.short_work_intent import detect_short_work_intent


def test_single_quote_with_find_verb_applies():
    intent = detect_short_work_intent("«ئۇچراشقاندا» ناملىق شېئىرنى تېپىپ بەر")
    assert intent.applies is True
    assert intent.title == "ئۇچراشقاندا"


def test_single_quote_with_content_marker_applies():
    # Real failing production query shape.
    intent = detect_short_work_intent(
        "«ئۆمۈر مەنزىللىرى» ناملىق ئەسەردىكى «ئۇچراشقاندا» ناملىق شېئىرنىڭ مەزمۇنى نىمە؟"
    )
    assert intent.applies is True
    # Two quotes: book (already resolved upstream) + work -- the SECOND wins.
    assert intent.title == "ئۇچراشقاندا"


def test_single_quote_full_text_marker_applies():
    intent = detect_short_work_intent(
        "«ئۇچراشقاندا» ناملىق شېئىرنىڭ تولۇق تېكىستىنى كۆرسەت"
    )
    assert intent.applies is True
    assert intent.title == "ئۇچراشقاندا"


def test_no_quotes_does_not_apply():
    intent = detect_short_work_intent("ئۇچراشقاندا دېگەن شېئىرنى تېپىپ بەر")
    assert intent.applies is False
    assert intent.title is None


def test_quote_without_locate_marker_does_not_apply():
    intent = detect_short_work_intent("«ئۇچراشقاندا» قانداق ئوقۇلىدۇ؟")
    assert intent.applies is False


def test_authorship_question_does_not_apply_even_with_locate_style_wording():
    intent = detect_short_work_intent("«ئۇچراشقاندا» ناملىق شېئىر كىمنىڭ ئەسىرى؟")
    assert intent.applies is False


def test_three_quotes_does_not_apply():
    intent = detect_short_work_intent("«A» ۋە «B» ۋە «C» نى تېپىپ بەر")
    assert intent.applies is False


def test_empty_text_does_not_apply():
    intent = detect_short_work_intent("")
    assert intent.applies is False


def test_two_quotes_linking_book_and_work_uses_second_as_title():
    intent = detect_short_work_intent(
        "«ئۆمۈر مەنزىللىرى» ناملىق ئەسەردىكى «ئۇچراشقاندا» ناملىق شېئىرنى تېپىپ بەر"
    )
    assert intent.applies is True
    assert intent.title == "ئۇچراشقاندا"
