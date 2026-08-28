from app.utils.ocr_corrections import apply_auto_corrections


def test_apply_auto_corrections_basic():
    pairs = [
        ("مۇئەللىم", "مۇئەللىم"),  # identity - should do nothing
        ("كىتاپ", "كىتاب"),
        ("مەكتەپكە", "مەكتەپكە"),
    ]
    text = "بۇ كىتاپ ناھايىتى ياخشى كىتاپ ئىكەن."
    corrected = apply_auto_corrections(text, pairs)
    assert corrected == "بۇ كىتاب ناھايىتى ياخشى كىتاب ئىكەن."


def test_apply_auto_corrections_word_boundary():
    pairs = [("ئان", "ئانا")]
    # Should replace standalone "ئان", but not inside "ئانىلار"
    text = "ئان كەلدى ئانىلار بىلەن."
    corrected = apply_auto_corrections(text, pairs)
    assert corrected == "ئانا كەلدى ئانىلار بىلەن."


def test_apply_auto_corrections_empty_and_punctuation():
    pairs = [("تېكىست", "تېكىستى")]
    assert apply_auto_corrections("", pairs) == ""
    assert apply_auto_corrections("تېكىست!", pairs) == "تېكىستى!"
