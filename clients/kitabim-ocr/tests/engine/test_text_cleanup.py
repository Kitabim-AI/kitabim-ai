from engine.text_cleanup import (
    normalize_uyghur_chars,
    correct_uyghur_ocr_orthography,
    clean_uyghur_text,
    is_toc_page,
    is_degenerate_ocr_output,
    is_block_repetition_loop,
    is_hallucinated_arabic_block,
    is_poem_block,
)


def test_normalize_uyghur_chars_removes_zero_width_chars():
    assert normalize_uyghur_chars("سا‌لام") == "سالام"


def test_normalize_uyghur_chars_normalizes_urdu_and_arabic_variants():
    assert normalize_uyghur_chars("قلعة") == "قلعە"
    assert normalize_uyghur_chars("مكتوبہ") == "مكتوبە"
    assert normalize_uyghur_chars("ہوججەت") == "ەوججەت"
    assert normalize_uyghur_chars("كتاب كے") == "كتاب كې"


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


def test_is_degenerate_ocr_output_flags_moderate_repetition():
    # 25 repeated words in an 80-word text (> 20 occurrences and > 20% frequency)
    text = " ".join(["المجتمع"] * 25 + ["ئادەتتىكى", "تېكىست", "مەزمۇن"] * 20)
    assert is_degenerate_ocr_output(text) is True


def test_is_degenerate_ocr_output_false_for_normal_text():
    assert is_degenerate_ocr_output("بۇ ئادەتتىكى بىر پارچە تېكىست.") is False


def test_clean_uyghur_text_strips_trailing_footer_page_numbers():
    text = "بۇ بىرىنچى ئابزاس.\n\nبۇ ئىككىنچى ئابزاس.\n\n4"
    cleaned = clean_uyghur_text(text)
    assert "4" not in cleaned
    assert "بۇ ئىككىنچى ئابزاس." in cleaned


def test_clean_uyghur_text_strips_decorated_footer_page_numbers():
    assert clean_uyghur_text("تېكىست.\n\n- 4 -") == "تېكىست."
    assert clean_uyghur_text("تېكىست.\n\n— 12 —") == "تېكىست."
    assert clean_uyghur_text("تېكىست.\n\n( 42 )") == "تېكىست."
    assert clean_uyghur_text("تېكىست.\n\n[ 4 ]") == "تېكىست."
    assert clean_uyghur_text("تېكىست.\n\n4 - بەت") == "تېكىست."
    assert clean_uyghur_text("تېكىست.\n\nبەت: 12") == "تېكىست."


def test_clean_uyghur_text_strips_leading_header_page_numbers():
    text = "4\n\nبۇ بىرىنچى ئابزاس."
    cleaned = clean_uyghur_text(text)
    assert cleaned == "بۇ بىرىنچى ئابزاس."


def test_clean_uyghur_text_preserves_numbered_lists_and_tables():
    text = "1. بىرىنچى تۈر\n2. ئىككىنچى تۈر"
    cleaned = clean_uyghur_text(text)
    assert "1. بىرىنچى تۈر" in cleaned
    assert "2. ئىككىنچى تۈر" in cleaned


def test_is_block_repetition_loop_detects_repeated_phrase():
    loop_text = (
        "والشقي بالشقي لاف فماليه . وهو . والشقي بالشقي لاف فماليه . وهو . "
        "والشقي بالشقي لاف فماليه . وهو . والشقي بالشقي لاف فماليه . وهو . "
        "والشقي بالشقي لاف فماليه"
    )
    assert is_block_repetition_loop(loop_text) is True


def test_is_block_repetition_loop_detects_consecutive_words():
    repeated_words = "في ولك في ولك في ولك في ولك في ولك في ولك في ولك في ولك"
    assert is_block_repetition_loop(repeated_words) is True


def test_is_block_repetition_loop_false_for_normal_text():
    normal = (
        "قىلالىدىم. ناھايىتى بىراقتا ... ۋاھ، مەن يۇلتۇزنى كۆرمىگىلى قانچە ۋاقىتلار بولغاندۇ. "
        "يىراقتىن، يىراق كۆكتىن بىر جۈپ يۇلتۇزنى كۆردۈم. يۇلتۇز شۇنچە روشەن كۆرۈندى."
    )
    assert is_block_repetition_loop(normal) is False


def test_is_hallucinated_arabic_block_flags_hallucinated_bleed_through():
    hallucinated = (
        "في المثال رفاعه وعنايه ولسسنه ؟ فمستولهم من القنبله ولا وعلا عليه للـهلمه "
        "ولقلا بـوا فرعه وفحيب وهو عبر بالشقي لالـه بـم وفق الولا وعلا علينا معنا ؟"
    )
    assert is_hallucinated_arabic_block(hallucinated) is True


def test_is_hallucinated_arabic_block_flags_runaway_arabic_words():
    hallucinated = (
        "في زمن السبحان والمستحقين والأبيات والأمريكيين في الشرق الشرقي حول الشرق الشرقي السامح "
        "والأمريكيين في الشرق الشرقي والأمريكيين في الشرق الشرقي"
    )
    assert is_hallucinated_arabic_block(hallucinated) is True


def test_is_hallucinated_arabic_block_false_for_genuine_uyghur():
    uyghur = (
        "قىلالىدىم. ناھايىتى بىراقتا ... ۋاھ، مەن يۇلتۇزنى كۆرمىگىلى قانچە ۋاقىتلار بولغاندۇ. "
        "يىراقتىن، يىراق كۆكتىن بىر جۈپ يۇلتۇزنى كۆردۈم. يۇلتۇز شۇنچە روشەن كۆرۈندى."
    )
    assert is_hallucinated_arabic_block(uyghur) is False


def test_is_degenerate_ocr_output_flags_multiword_loops():
    loop_text = "بۇ نورمال كىرىش سۆز. " + ("والشقي بالشقي لاف فماليه وهو ") * 6
    assert is_degenerate_ocr_output(loop_text) is True


def test_is_poem_block_detects_uyghur_poem_stanzas():
    poem_lines = [
        "غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،",
        "مېنى كىم كۆرسە پەرق ئەتمەس خازاندىن لالىزارمىنى .",
        "ئاقار سەل ئورنىدا ياشىم، غېرىب بولدى ئەزىز باشىم،",
        "ماڭا تار ئەيلىدى چۈنكى بۇ دەۋران ئۆز دىيارمىنى .",
        "يۈرەك يارە، جىگەر پارە، ئەجەب بىچاردۇر ھالىم،",
        "ۋاپادار غەمگۈزارىم يوق ئىشتىمەككە بۇ زارمىنى .",
    ]
    assert is_poem_block(poem_lines) is True
    assert is_poem_block(poem_lines, width_ratio=0.62) is True


def test_is_poem_block_detects_couplets():
    couplet = [
        "ئەي ئەزىزىم، قەدرىمگە يەتسەڭچۇ سەن،",
        "بۇ جاھاندا مەندەك ۋاپادار كەم سەن.",
    ]
    assert is_poem_block(couplet) is True


def test_is_poem_block_rejects_prose_and_dialogue():
    # Dialogue with dashes
    dialogue = [
        "- دېدى شېرىكى كۈلۈمسىرەپ ئۇنىڭغا پىسەنت قىلماي.",
        "- ماقۇل، ئۇنداقتا مەن كۈتەي.",
    ]
    assert is_poem_block(dialogue) is False

    # Wrapped prose with mid-line terminal periods
    prose = [
        "خەيرىيەت، ئەمدى تاھارىتىڭنى ئال. مەن نامىزىمنى ئۆتۈۋېرەي، -",
        "دېدى شېرىكى كۈلۈمسىرەپ ئۇنىڭغا پىسەنت قىلماي.",
    ]
    assert is_poem_block(prose) is False

    # Irregular line lengths (typical prose paragraph with short last line)
    prose_ragged = [
        "ياساۋۇل بېلىگە چىڭ تارتىلغان كۆندىن ئىشلەنگەن كەمىرىنى",
        "يېشىپ، قىلىچى بىلەن سۆيىغا قويدى. ئانچە چوڭ ئەمەس مەزكۇر",
        "سۆيىدا ياساۋۇللار نۆۋەت بىلەن ئارام ئالاتتى، قورال - ياراغنى",
        "قويۇشاتتى.",
    ]
    assert is_poem_block(prose_ragged) is False


def test_clean_uyghur_text_preserves_poem_lines_while_reflowing_prose():
    poem = (
        "غېبى جانان، دېفى ھىجران تۇگەتتى ياش باھارمىنى،\n"
        "مېنى كىم كۆرسە پەرق ئەتمەس خازاندىن لالىزارمىنى .\n"
        "ئاقار سەل ئورنىدا ياشىم، غېرىب بولدى ئەزىز باشىم،\n"
        "ماڭا تار ئەيلىدى چۈنكى بۇ دەۋران ئۆز دىيارمىنى ."
    )
    cleaned_poem = clean_uyghur_text(poem)
    # Each verse must stay on its own line
    poem_lines = cleaned_poem.split("\n")
    assert len(poem_lines) == 4
    assert "غېبى جانان" in poem_lines[0]
    assert "مېنى كىم كۆرسە" in poem_lines[1]
    assert "غېرىپ بولدى ئەزىز باشىم" in poem_lines[2]

    # Prose paragraph should still be merged
    prose = (
        "بۇ بىر ئادەتتىكى تېكىست قۇرى بولۇپ كېيىنكى قۇرغا تۇتىشىدۇ\n"
        "ۋە ئاخىرقى قۇرمۇ مۇشۇ ئابزاسقا تەۋە بولىدۇ."
    )
    cleaned_prose = clean_uyghur_text(prose)
    assert "\n" not in cleaned_prose


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
