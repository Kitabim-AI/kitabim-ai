from app.utils.tts_text import prepare_answer_for_tts, split_tts_chunks


def test_prepare_answer_strips_markdown_and_ref_citations_preserves_uyghur_numbers():
    raw = (
        "### تارىخىي ئۇچۇر\n\n"
        "مىلادى **1876 — يىلى** «قولىڭدىن كەلسە، ئوتنى بۈگۈن ئۆچۈر» دېگەن سۆز "
        "[«تارىخىي رەشىدى»، 42-بەت](ref:book-123:42) دە يېزىلغان.\n\n"
        "- بىرىنچى نۇقتا (BookID: abc-99)\n"
        "- ئىككىنچى نۇقتا https://example.com/test 📚"
    )
    cleaned, truncated = prepare_answer_for_tts(raw, max_chars=5000)

    assert truncated is False
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "ref:book-123:42" not in cleaned
    assert "BookID:" not in cleaned
    assert "https://example.com" not in cleaned
    assert "📚" not in cleaned
    assert "1876 — يىلى" in cleaned
    assert "«تارىخىي رەشىدى»، 42-بەت" in cleaned
    assert "\n\n" in cleaned


def test_prepare_answer_truncates_at_sentence_boundary():
    sentence = "بۇ بىر سىناق جۈملىسىدۇر. "
    raw = sentence * 30  # ~720 chars
    cleaned, truncated = prepare_answer_for_tts(raw, max_chars=200)

    assert truncated is True
    assert len(cleaned) <= 200
    assert cleaned.endswith(".")


def test_prepare_answer_returns_empty_for_only_symbols_or_links():
    cleaned, truncated = prepare_answer_for_tts("   (ref:abc:1) https://a.co 📚  ")
    assert cleaned == ""
    assert truncated is False


def test_split_tts_chunks_preserves_paragraphs_and_splits_long_text():
    p1 = "بىرىنچى ئابزاس. " * 20
    p2 = "ئىككىنچى ئابزاس. " * 20
    p3 = "ئۈچىنچى ئابزاس. " * 20
    text = f"{p1.strip()}\n\n{p2.strip()}\n\n{p3.strip()}"

    chunks = split_tts_chunks(text, max_chunk_chars=400)
    assert len(chunks) == 3
    assert all(len(c) <= 400 for c in chunks)
