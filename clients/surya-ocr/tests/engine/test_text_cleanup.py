from engine.text_cleanup import (
    normalize_uyghur_chars,
    clean_uyghur_text,
    is_toc_page,
    is_degenerate_ocr_output,
)


def test_normalize_uyghur_chars_removes_zero_width_chars():
    assert normalize_uyghur_chars("سا‌لام") == "سالام"


def test_clean_uyghur_text_strips_header_footer_markers():
    result = clean_uyghur_text("بۇ مەزمۇن.[Footer] 3")
    assert "[Footer]" not in result
    assert "3" not in result


def test_clean_uyghur_text_empty_input():
    assert clean_uyghur_text("") == ""


def test_clean_uyghur_text_never_merges_into_a_following_table_row():
    # A plain line with no ending punctuation, immediately followed by a
    # pipe-table row, must not get merged into that row's front - the row
    # boundary itself is the signal to break, regardless of the current
    # line's own properties.
    text = "Some heading with no punctuation\n| Title | 42 |"
    cleaned = clean_uyghur_text(text)
    assert "| Title | 42 |" in cleaned.split("\n")
    assert not any(
        line.strip().startswith("Some") and "|" in line for line in cleaned.split("\n")
    )


def test_is_toc_page_detects_munderije_keyword():
    assert is_toc_page("مۇندەرىجە\nباب بىر") is True


def test_is_toc_page_false_for_plain_paragraph():
    assert is_toc_page("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False


def test_is_degenerate_ocr_output_flags_repeated_word():
    text = " ".join(["مۇزىكا"] * 300)
    assert is_degenerate_ocr_output(text) is True


def test_is_degenerate_ocr_output_false_for_normal_text():
    assert is_degenerate_ocr_output("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False
