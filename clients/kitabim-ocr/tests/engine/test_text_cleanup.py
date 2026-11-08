from engine.text_cleanup import (
    add_word_spans,
    clean_uyghur_text,
    has_repeated_word_span,
    is_block_repetition_loop,
    is_degenerate_ocr_output,
    is_hallucinated_arabic_block,
    is_hallucinated_ghost_text,
    is_isolated_page_number,
    is_key_value_line,
    is_metadata_or_key_value_block,
    is_poem_block,
    is_toc_page,
    normalize_uyghur_chars,
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


def test_is_hallucinated_ghost_text_flags_pseudo_uyghur_bleed_through():
    syllable_loop = (
        "نەچەچە قىلتقامه - نەقەغ رختسملىملىم تىك مەنه قىلشىم لىخنامه\n"
        "رامه مە ن قەغ نەقىمى املى مىقامه قىلىملىم مە ن قىلىمىم مىلىشى اميليم"
    )
    assert is_hallucinated_ghost_text(syllable_loop) is True

    repeated_word_block = "نەچچە ئالىقاندا - نەشەر رىخى بىلىملىرى مىنىڭ ئەرشى بىلىملىرى لىغىنى بىلىملىرى . نەشەر رىخى بىلىملىرى"
    assert is_hallucinated_ghost_text(repeated_word_block) is True


def test_is_hallucinated_ghost_text_false_for_genuine_uyghur():
    normal = (
        "ئەي زېرەك، ئەقىللىق ئوغلۇم، ئىستىكىم ئەۋلادلىرىم ئۈچۈن تېگىشلىك سۆزلىرىمنى "
        "يادىكار قالدۇرۇش ئىدى. ئەقلىم قارشى قوپۇپ ئېيتتىكى : ئەي يۈسۈپ دىققەت قىلغىن."
    )
    assert is_hallucinated_ghost_text(normal) is False

    # Genuine line from Romance of the Three Kingdoms with '-ىشىش' reciprocal verbal nouns
    reciprocal_line = (
        "كېيىن، مۇقەررەر بىرلىشىش، ئۇزۇن بىرلىشىشتىن كېيىن، چوقۇم بۆلۈنۈش بولۇپ كەلدى"
    )
    assert is_hallucinated_ghost_text(reciprocal_line) is False

    # Poem stanza with recurring refrain (radif) across lines
    radif_poem = (
        "ئىلىم بىلەن يورۇيدۇ بۇ گۈزەل جاھان،\n"
        "ئەقىل بىلەن يورۇيدۇ بۇ گۈزەل جاھان،\n"
        "ئەمگەك بىلەن يورۇيدۇ بۇ گۈزەل جاھان،\n"
        "ھىممەت بىلەن يورۇيدۇ بۇ گۈزەل جاھان."
    )
    assert is_hallucinated_ghost_text(radif_poem) is False

    # Literary dialogue with repeated sobbing/laughing onomatopoeia (regression: page 9)
    sobbing_dialogue = (
        "— ئون مېتىر ئورۇس تىرىكىسى، ئۈچ مېتىر مەخمەل، يېپىپڭى چەكمەن، مەسكاپ ئۆتۈك، "
        "ھۈ - ھۈ - ھۈ ... ئىلاھىم قولىغا كۆيدۈرگۈ چىقار، سىل بولۇپ ئۆلەر ... ھۈ - ھۈ - ھۈ ..."
    )
    assert is_hallucinated_ghost_text(sobbing_dialogue) is False
    assert is_block_repetition_loop(sobbing_dialogue) is False

    pure_crying_line = (
        "— ھۈ - ھۈ - ھۈ ... ۋاي خۇدايىم، ھۈ - ھۈ - ھۈ ... ھۈ - ھۈ - ھۈ ..."
    )
    assert is_hallucinated_ghost_text(pure_crying_line) is False
    assert is_block_repetition_loop(pure_crying_line) is False

    laughing_line = "— ھا - ھا - ھا - ھا! — دەپ قاقاقلاپ كۈلدى ئۇ."
    assert is_hallucinated_ghost_text(laughing_line) is False
    assert is_block_repetition_loop(laughing_line) is False

    # Genuine Uyghur morphology & root reduplications (-ۋاتاتتى, تۇتۇش, چاقچاق, ئەنئەنە, underscore dashes)
    assert is_hallucinated_ghost_text("تۇخۇم ۋە باناندىن پەرھىز تۇتۇشى لازىم.") is False
    assert (
        is_hallucinated_ghost_text("كەتتىم، -- بۇ چاقچاق، چاقچاق قىلىپ قويدۇم.")
        is False
    )
    assert (
        is_hallucinated_ghost_text(
            "ئەنئەنە ئىزچىللىقى ئەنئەنە قاتماللىقى ئەمەس، ئەنئەنىنىڭ راۋاجلانغان تارىخىي قاتلاملىقىدىن ئىبارەت."
        )
        is False
    )
    assert (
        is_hallucinated_ghost_text(
            "__ __ گۈلئەنبەر يوقاپ كەتتى. يا، بۇۋىسۇلتان؟ __ دەپ سورىدى. __ ھەئە."
        )
        is False
    )

    # Stuttering dialogue with spaced ellipses and pipe-table TOC blocks
    stutter = "__ بۇ . . . بۇ . . . __ تىرناق تاتىلاش بىلەن ئاۋارە بولىۋاتقان ئەكبەر دۈدۈقلاپ قالدى."
    assert is_block_repetition_loop(stutter) is False
    assert is_hallucinated_ghost_text(stutter) is False

    pipe_toc = (
        "|ئەنجۈرنىڭ شىپالىق رولى|34|\n"
        "|بېھىنىڭ شىپالىق رولى|35|\n"
        "|ئانار ۋە ئۇنىڭ دورىلىق قىممىتى|35|\n"
        "|شاپتۇل ۋە ئۇنىڭ دورىلىق قىممىتى|38|\n"
        "|قوغۇن ۋە ئۇنىڭ شىپالىق رولى|40|"
    )
    assert is_block_repetition_loop(pipe_toc) is False
    assert is_hallucinated_ghost_text(pipe_toc) is False


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

    # Couplet ending with question marks (or OCR artifact mum)
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

    # Rhyming couplet without punctuation
    rhyme_couplet = [
        "ئاقتى بۇلاق تاغ باغرىدا شارقىراپ",
        "ياشلار كېلەر مەيدانلاردا پارقىراپ",
    ]
    assert is_poem_block(rhyme_couplet) is True


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


def test_clean_uyghur_text_preserves_poem_lines_exactly():
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
    assert "غېرىب بولدى ئەزىز باشىم" in poem_lines[2]

    # Prose lines must also stay exactly as they appear - never merged
    prose = (
        "بۇ بىر ئادەتتىكى تېكىست قۇرى بولۇپ كېيىنكى قۇرغا تۇتىشىدۇ\n"
        "ۋە ئاخىرقى قۇرمۇ مۇشۇ ئابزاسقا تەۋە بولىدۇ."
    )
    assert clean_uyghur_text(prose) == prose


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


def test_clean_uyghur_text_never_merges_prose_lines():
    prose = (
        "سارغۇجىدا ئەنەلەر سۇ توشۇمايتتى، قازان بېشىغا ئارىلاشمايتتى، سۇ توشۇش، ئوتۇن يېرىش ئىشلىرى توي\n"
        "ئىشىغا كىرەتتى. ئوي ئىشىنى بولسا، ئاياللار قىلاتتى، ئەرلەر تالا ئىشىنى، ئېتىز - ئېرىق، مال -\n"
        "ۋارانغا قاراش، چۆپ چېپىش، ئوتۇن تارتىش، ئوبىنىك كەم - كۇسىنى تەييارلاپ بېرىشتەك ئىشلارنى\n"
        "قىلاتتى. كۈنلەر مۇشۇ تەرىقىدە ئۆتۈۋەردى."
    )
    assert clean_uyghur_text(prose) == prose


def test_clean_uyghur_text_never_separates_lines_into_paragraphs():
    # Lines are kept exactly as OCR'd, in one block - never merged with
    # spaces, and never split apart into separate blank-line-separated
    # paragraphs either.
    mixed = (
        "ئەرلەر قازان بېشىغا ئارىلىشىپ قالسا، ئاياللار: - چىپىلمىسىلا، - دەپ قازان بېشىدىن\n"
        "ھەيدىۋېتەتتى. سارغۇجىا ئاياللىرى دىرەنزە، ھويلىلاردىن مارىشىپ قاقاقلاپ كۈلۈشتى:\n"
        "— ياغلىقلا تاڭسا چىرايلىق چوكان بولغۇدەك! - ھا - ھا - ھا!\n"
        "— پۆرمىلىك كۆينەك كىيسە ئېرىگىنى تارتىۋالامدو تېخى!\n"
        "— ۋاھ - ھا - ھا! ھېيى - ھېي!"
    )
    assert clean_uyghur_text(mixed) == mixed


def test_clean_uyghur_text_preserves_dash_attribution_lines_exactly():
    dialogue = (
        "— خەيرىيەت، ئەمدى تاھارىتىڭنى ئال. مەن نامىزىمنى ئۆتۈۋېرەي، —\n"
        "دېدى شېرىكى كۈلۈمسىرەپ ئۇنىڭغا پىسەنت قىلماي.\n"
        "— خۇپتەننى بىللە ئوقۇيلى."
    )
    assert clean_uyghur_text(dialogue) == dialogue


def test_has_repeated_word_span_detects_short_decoder_loop():
    # Real Surya full-page output: a 2-line block where the model re-emitted
    # its last line before drifting into the footnote's text.
    looped = (
        "پەرغانە نۇسخىسى ئەرەب ھەرپى ئاساس قىلىنغان ئۇيغۇر يېزىقىدا كۆچۈرۈلگەن ۋە "
        "ھەممىدىن تولۇق نۇسخا بولۇپ، بۇ نۇسخىنى تۇنجى قېتىم تاتار ئالىمى زەكى "
        "ۋەلىدىي 1914 - يىلى پەرغانىدا تولۇق نۇسخىسى بولۇپ، بۇ نۇسخىنى تۇنجى "
        "قېتىم تاتار ئالىمى زەكى ۋەلىدىي 1914 - يىلى پەرغانىدا تولۇق نۇسخىسى "
        "بولۇپ، مەھمۇد كاشى ھەرىسىڭ ئېيىنىچە، بۇ سۆزنىڭ قەدىمكى يۈركىسى"
    )
    assert is_block_repetition_loop(looped) is False  # too short a loop for it
    assert has_repeated_word_span(looped) is True


def test_has_repeated_word_span_false_for_normal_paragraph():
    normal = (
        "ۋېنا نۇسخىسى مىلادىيە 1439 - يىلى ھىرات شەھىرىدە ھەسەن قارا سايىل شەمس "
        "دېگەن كىشى تەرىپىدىن قەدىمكى ئۇيغۇر يېزىقىدا كۆچۈرۈلۈپ، مىلادىيە 1474 - "
        "يىلى ئىستانبۇلغا كەلتۈرۈلگەن، بۇ نۇسخا ھازىرمۇ شۇ كۈتۈپخانىدا ساقلانماقتا."
    )
    assert has_repeated_word_span(normal) is False


def test_has_repeated_word_span_ignores_short_repeated_phrases():
    text = (
        "بۇ نۇسخىنى تۇنجى قېتىم ئېلان قىلدى. كېيىن بۇ نۇسخىنى تۇنجى قېتىم نەشر قىلدى."
    )
    assert has_repeated_word_span(text) is False


def test_has_repeated_word_span_detects_cross_block_duplicate():
    top_block = (
        "(ئەلىگە سەن تېۋىپقا ئوخشارسەن بۇ كۈن،\n"
        "ساڭا موھتاج ئېرۇر ئاغرىق — خەلق پۈتۈن)."
    )
    bottom_echo = (
        "ئەلىگە سەن تېۋىپقا ئوخشارسەن بۇ كۈن،\n" "ساڭا موھتاج ئېرۇر ئاغرىق — خەلق پۈتۈن"
    )
    seen_spans = set()
    # Top block has no internal repetition
    assert (
        has_repeated_word_span(top_block, min_words=8, seen_spans=seen_spans) is False
    )
    add_word_spans(top_block, seen_spans, min_words=8)
    assert len(seen_spans) > 0

    # Bottom echo block repeats the span from earlier on the page
    assert (
        has_repeated_word_span(bottom_echo, min_words=8, seen_spans=seen_spans) is True
    )


def test_has_repeated_word_span_detects_cross_block_duplicate_in_combined_block():
    top_block = (
        "(ئەلىگە سەن تېۋىپقا ئوخشارسەن بۇ كۈن،\n"
        "ساڭا موھتاج ئېرۇر ئاغرىق — خەلق پۈتۈن)."
    )
    last_block = (
        "ئۆز دەۋرىدىكى رېئاللىققا قارىتا، يۈسۈپ خاس ھاجىپ ئۆزى ياراتقان غايىۋى پېرسوناژلار\n"
        "ئەلىگە سەن تېۋىپقا ئوخشارسەن بۇ كۈن،\n"
        "ساڭا موھتاج ئېرۇر ئاغرىق — خەلق پۈتۈن"
    )
    seen_spans = set()
    add_word_spans(top_block, seen_spans, min_words=8)
    assert (
        has_repeated_word_span(last_block, min_words=8, seen_spans=seen_spans) is True
    )


def test_page_number_stripping_preserves_markdown_headings_and_list_markers():
    # Numbered chapter/section headings ('# 1', '## 2') must never be treated as page numbers
    assert is_isolated_page_number("# 1") is False
    assert is_isolated_page_number("## 2") is False
    assert is_isolated_page_number("### 12") is False
    assert (
        clean_uyghur_text("# 1\n\nبىرىنچى بۆلەك تېكىستى.")
        == "# 1\n\nبىرىنچى بۆلەك تېكىستى."
    )
    assert (
        clean_uyghur_text("## 2\n\nئىككىنچى بۆلەك تېكىستى.")
        == "## 2\n\nئىككىنچى بۆلەك تېكىستى."
    )

    # Unbalanced list markers / bullets ('1)', '- 1', '* 2') must be preserved
    assert is_isolated_page_number("1)") is False
    assert is_isolated_page_number("- 1") is False
    assert is_isolated_page_number("* 2") is False
    assert clean_uyghur_text("1)\nبىرىنچى ماددا") == "1)\nبىرىنچى ماددا"


def test_has_repeated_word_span_ignores_uyghur_punctuation_and_underscore_dashes():
    # Standalone Uyghur punctuation ('،', '؟') and underscore dashes ('__') must not count as words
    short_with_punct = "__ بىر ، ئىككى ، ئۈچ ؟ __ __ بىر ، ئىككى ، ئۈچ ؟ __"
    assert has_repeated_word_span(short_with_punct, min_words=8) is False


def test_is_block_repetition_loop_preserves_attached_punctuation_onomatopoeia():
    # Real book dialogue: knocking ('تاك.....') and emphatic refusals ('ياق، ياق، ياق، ياق!')
    knocking = "دېرىزىدىن «تاك..... تاك..... تاك..... تاك.....» قىلغان تاۋۇش ئاڭلاندى."
    assert is_block_repetition_loop(knocking) is False
    assert is_hallucinated_ghost_text(knocking) is False

    emphatic_no = "— ياق، ياق، ياق، ياق! بۇنداق بولۇشى مۇمكىن ئەمەس!"
    assert is_block_repetition_loop(emphatic_no) is False
    assert is_hallucinated_ghost_text(emphatic_no) is False

    # Bare unpunctuated token loops must still be caught at 4 repeats
    assert is_block_repetition_loop("چىسىم چىسىم چىسىم چىسىم") is True


def test_is_hallucinated_arabic_block_preserves_heh_uyghur_and_vocalized_quotes():
    # Older Uyghur orthography / OCR 'ه'-for-'ە' substitution containing Turkic consonants (پ, چ, گ, ڭ)
    heh_uyghur = "توغرا تپه گکور ته گرنگ بزگه ئاتا قلغان ئه گ چوڭ نپه تلرنگ پری."
    assert is_hallucinated_arabic_block(heh_uyghur) is False

    # Genuine vocalized Quranic / Hadith quote with harakat/tashkeel in classical Uyghur books
    vocalized_quote = (
        "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ " "الرَّحْمَٰنِ الرَّحِيمِ مَالِكِ يَوْمِ الدِّينِ"
    )
    assert is_hallucinated_arabic_block(vocalized_quote) is False


def test_is_degenerate_ocr_output_preserves_questionnaire_pages_and_flags_block_loops():
    # Real book personality quiz page: 10 distinct numbered questions each followed by 'A. ياق .B. شۇنداق'
    quiz_blocks = [
        f"{i}. سىز ھەر كۈنى ئەتىگەندە كىتاب ئوقۇشنى ياقتۇرامسىز؟\nA. ياق .B. شۇنداق"
        for i in range(11, 21)
    ]
    quiz_page = "\n\n".join(quiz_blocks)
    assert is_degenerate_ocr_output(quiz_page) is False

    # Consecutive identical block/line loops across a page must still be flagged
    multi_block_loop = "\n\n".join(
        ["ئۇنىڭ كۆزلىرىدىن ياش تامچىلاپ چۈشتى ۋە يىغلاپ تاشلىدى."] * 6
    )
    assert is_degenerate_ocr_output(multi_block_loop) is True


def test_cleanup_preserves_parallel_rhetoric_recipes_footnotes_and_exclamations():
    real_book_passages = [
        # Worksheet rating rubric
        (
            "كۆزلىگەن بازىرىڭىزنى پەرقلەندۈرۈش: ياخشى يامان ئەمەس ناچار رىقابەتچىڭىزگە باھا بېرىش: "
            "ياخشى يامان ئەمەس ناچار باھانى بېكىتىش: ياخشى يامان ئەمەس ناچار ئېلان تەشۋىقات تەدبىرى تۈزۈش: "
            "ياخشى يامان ئەمەس ناچار"
        ),
        # Classical couplets / refrains rendered inline
        (
            "ئادالەتنى شاھقا يار قىلغان ئاللادۇر، تاپاۋەتنى بايغا يار قىلغان ئاللادۇر. "
            "تاقەتنى گادايغا يار قىلغان ئاللادۇر، جاسارەتنى مەردكە يار قىلغان ئاللادۇر."
        ),
        (
            "ئەي يارەنلەر، ھەركىمى، ياھۇ، يائاللا، مەندەك يېتىم بولمىغاي، ياھۇ، يائاللا. "
            "يۈرىكى زەرداپ بولۇپ، ياھۇ، يائاللا، كۆڭلى دەردكە تولمىغاي، ياھۇ! يائاللا!"
        ),
        # Parallel enumerations, herbal prescriptions, and footnote citation lists
        (
            "دەسلەپتە چىلاندىن يەتتە دانە، گۈلبىنەپشىدىن ئالتە گىرام، گۈلى نېلۇپەردىن ئالتە گىرام، "
            "شاھتەررەدىن ئالتە گىرام، كاسىنە ئۇرۇقىدىن ئالتە گىرام، بىخ كاسىنەدىن ئالتە گىرام."
        ),
        (
            "① «بەيتۇللانىڭ تارىخى»، 21 - بەت.\n"
            "② «بەيتۇللانىڭ تارىخى»، 33 - بەت.\n"
            "③ «بەيتۇللانىڭ تارىخى»، 35 - بەت.\n"
            "④ «بەيتۇللانىڭ تارىخى»، 308 - بەت."
        ),
        # Dot-leader TOC block
        (
            "160 ..... (7) داۋا\n"
            "160 ..... (8) داۋا\n"
            "161 ..... (9) داۋا\n"
            "161 ..... (10) داۋا\n"
            "161 ..... (11) داۋا"
        ),
        # Rule-of-three exclamations, vocatives, aphorisms, quiz keys, and older 'ه' orthography
        "## «ۋاقت ئۆتۈپ كېتىۋاتىدۇ، ئالدىراڭلار! ئالدىراڭلار!! ئالدىراڭلار!!»",
        "— ئەنۋەر! ئەنۋەر! — دەپ توۋلىغانىدى، ئەنۋەر ئارقىسىغا بۇرۇلۇپ:",
        "— كېلىۋاتىدۇ! كېلىۋاتىدۇ! ئاق بوز ئات ئۇچۇپ كېلىۋاتىدۇ! —",
        "— ساندۇقۇم، ساندۇقۇم، سەدەپ ساندۇقۇم!",
        "توققۇز ئاي، توققۇز كۈن، توققۇز سائەت، توققۇز مىنۇت يىغلىساق، كۆز يېشىمىز قۇرۇمايدۇ.",
        "مۇقام دېمەك — سۆيگۈ دېمەك، ھايات دېمەك، مۇقام دېمەك — يۈرەك دېمەك، قانات دېمەك.",
        "ئۈچۈن، شەمشىدىن ھاجىم ئۈچۈن، ئۆزۈم ئۈچۈن، ھەممە ئۈچۈن چىداي...»",
        "A نى تاللىغانلار 3 نومۇرغا ئېرىشتى، B نى تاللىغانلار 2 نومۇرغا ئېرىشتى، C نى تاللىغانلار 1 نومۇرغا ئېرىشتى.",
        "توغرا تپه گکور ته گرنگ بزگه ئاتا قلغان ئه گ چوڭ نپه تلرنگ پری.",
    ]
    for passage in real_book_passages:
        assert (
            is_block_repetition_loop(passage) is False
        ), f"Loop false positive: {passage}"
        assert (
            is_hallucinated_ghost_text(passage) is False
        ), f"Ghost false positive: {passage}"
        assert (
            is_hallucinated_arabic_block(passage) is False
        ), f"Arabic false positive: {passage}"

    # Numbered decoder loops with collapsed vocabulary must still be caught
    numbered_loop = (
        "(8) ئۇ قولغا باب بالىلىك بايان دېدى ۋە ئۇ باب بالىلىك بايان دېدى. "
        "(9) ئۇ باب بالىلىك بايان دېدى ۋە ئۇ باب بالىلىك بايان دېدى. "
        "(10) ئۇ باب بالىلىك بايان دېدى ۋە ئۇ باب بالىلىك بايان دېدى."
    )
    assert is_block_repetition_loop(numbered_loop) is True


def test_clean_uyghur_text_strips_surya_compact_tokens():
    raw = "بىرىنچى باب <|635|> تېكىستى <|box|><|325|>"
    assert clean_uyghur_text(raw) == "بىرىنچى باب تېكىستى"


def test_is_toc_page_detects_short_continuation_pipe_toc_and_rejects_data_tables():
    continuation_toc = (
        "| 2 . « مەدەنىيەت زور ئىنقىلابى » نى ئىنكار قىلىش | 542 |\n"
        "| 3 . مەڭگۈ ئۇنتۇلمايدىغان ساۋاق | 559 |\n"
        "| 4 . تارىخنىڭ تۆلىمى | 580 |"
    )
    assert is_toc_page(continuation_toc) is True

    markdown_data_table = (
        "| ئىسمى | يېشى |\n"
        "| --- | --- |\n"
        "| ئەلى | 20 |\n"
        "| ۋەلى | 25 |\n"
        "| سەلىم | 30 |"
    )
    assert is_toc_page(markdown_data_table) is False
