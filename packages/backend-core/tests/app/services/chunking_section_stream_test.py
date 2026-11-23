import pytest

from app.services.chunking_service import ChunkingService


def test_chunk_book_sections_stitches_cross_page_prose_and_keeps_footnotes_page_local():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=200, min_chunk_size=350)
    pages = [
        {
            "page_number": 2,
            "is_toc": False,
            "text": "## بىرىنچى باب\n\nبۇ بىرىنچى بەتنىڭ تېكىستى داۋاملىشىدۇ\n\n[1]: بىرىنچى بەت ئىزاھاتى.",
        },
        {
            "page_number": 3,
            "is_toc": False,
            "text": "ۋە ئىككىنچى بەتتە تاماملىنىدۇ.\n\nئىككىنچى ئابزاس تېكىستى.",
        },
    ]
    sections = [
        {
            "id": 10,
            "level": 2,
            "title": "بىرىنچى باب",
            "start_page": 2,
            "end_page": 3,
            "order_index": 0,
        }
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) >= 1
    first = chunks[0]
    assert first.section_id == 10
    assert first.page_number == 2
    assert first.end_page_number == 3
    # Footnote stays attached to page 2 block, and prose stitches across page 2 -> 3
    assert "[1]: بىرىنچى بەت ئىزاھاتى." in first.text
    assert "ۋە ئىككىنچى بەتتە تاماملىنىدۇ." in first.text
    # Chunk text is unprefixed (no synthetic header prepended when header already present or inherited)
    assert len(first.text_hash) == 64


def test_chunk_book_sections_never_merges_across_section_boundaries():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=200, min_chunk_size=350)
    pages = [
        {
            "page_number": 2,
            "is_toc": False,
            "text": "## شېئىر 1\n\nئالتۇن كۈز كەلدى.",
        },
        {
            "page_number": 3,
            "is_toc": False,
            "text": "## شېئىر 2\n\nباھار شامىلى چىقتى.",
        },
    ]
    sections = [
        {
            "id": 101,
            "level": 2,
            "title": "شېئىر 1",
            "start_page": 2,
            "end_page": 2,
            "order_index": 0,
        },
        {
            "id": 102,
            "level": 2,
            "title": "شېئىر 2",
            "start_page": 3,
            "end_page": 3,
            "order_index": 1,
        },
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) == 2
    assert chunks[0].section_id == 101
    assert chunks[0].page_number == 2
    assert chunks[0].end_page_number == 2
    assert "شېئىر 2" not in chunks[0].text

    assert chunks[1].section_id == 102
    assert chunks[1].page_number == 3
    assert chunks[1].end_page_number == 3
    assert "شېئىر 1" not in chunks[1].text


def test_chunk_book_sections_splits_oversized_single_page_block():
    svc = ChunkingService(chunk_size=500, chunk_overlap=50, min_chunk_size=100)
    long_sentence = "بۇ ناھايىتى ئۇزۇن جۈملە بولۇپ تەكرارلىنىدۇ. " * 120
    pages = [
        {
            "page_number": 2,
            "is_toc": False,
            "text": long_sentence,
        }
    ]
    sections = [
        {
            "id": 55,
            "level": 1,
            "title": "باب",
            "start_page": 2,
            "end_page": 2,
            "order_index": 0,
        }
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert c.page_number == 2
        assert c.end_page_number == 2
        assert c.section_id == 55


def test_chunk_book_sections_chunks_chapter_intros_without_duplicating_children():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=200, min_chunk_size=350)
    pages = [
        {
            "page_number": 2,
            "is_toc": False,
            "text": "# بىرىنچى باب\n\nبۇ بىرىنچى بابنىڭ مۇھىم كىرىش سۆزى بولۇپ ئوقۇرمەنلەرگە چۈشەندۈرۈلىدۇ.\n\n## شېئىر 1\n\nشېئىر 1 مەزمۇنى.",
        },
        {
            "page_number": 3,
            "is_toc": False,
            "text": "# ئىككىنچى باب\n\nئىككىنچى بابنىڭ كىرىش سۆزى بۇ بەتتە يېزىلغان.",
        },
        {
            "page_number": 4,
            "is_toc": False,
            "text": "## شېئىر 2\n\nشېئىر 2 مەزمۇنى.",
        },
    ]
    sections = [
        {
            "id": 10,
            "section_index": 0,
            "level": 1,
            "section_type": "chapter",
            "title": "بىرىنچى باب",
            "start_page": 2,
            "start_block_index": 0,
            "end_page": 2,
            "end_block_index": 999999,
        },
        {
            "id": 11,
            "parent_id": 10,
            "parent_section_index": 0,
            "section_index": 1,
            "level": 2,
            "section_type": "work",
            "title": "شېئىر 1",
            "start_page": 2,
            "start_block_index": 2,
            "end_page": 2,
            "end_block_index": 999999,
        },
        {
            "id": 20,
            "section_index": 2,
            "level": 1,
            "section_type": "chapter",
            "title": "ئىككىنچى باب",
            "start_page": 3,
            "start_block_index": 0,
            "end_page": 4,
            "end_block_index": 999999,
        },
        {
            "id": 21,
            "parent_id": 20,
            "parent_section_index": 2,
            "section_index": 3,
            "level": 2,
            "section_type": "work",
            "title": "شېئىر 2",
            "start_page": 4,
            "start_block_index": 0,
            "end_page": 4,
            "end_block_index": 999999,
        },
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) == 4
    assert chunks[0].section_id == 10
    assert "بىرىنچى بابنىڭ مۇھىم كىرىش سۆزى" in chunks[0].text
    assert "شېئىر 1" not in chunks[0].text

    assert chunks[1].section_id == 11
    assert "شېئىر 1 مەزمۇنى" in chunks[1].text
    assert "ئىككىنچى باب" not in chunks[1].text

    assert chunks[2].section_id == 20
    assert "ئىككىنچى بابنىڭ كىرىش سۆزى" in chunks[2].text
    assert "شېئىر 2" not in chunks[2].text

    assert chunks[3].section_id == 21
    assert "شېئىر 2 مەزمۇنى" in chunks[3].text


def test_chunk_book_sections_strips_repeated_running_headers():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=200, min_chunk_size=50)
    pages = [
        {
            "page_number": i,
            "is_toc": False,
            "text": f"# كىتاب ماۋزۇسى\n\nبۇ {i}-بەتنىڭ تېكىستى داۋاملىشىدۇ",
        }
        for i in range(1, 7)
    ]
    sections = [
        {
            "id": 1,
            "level": 1,
            "title": "باب",
            "start_page": 1,
            "start_block_index": 0,
            "end_page": 6,
            "end_block_index": 999999,
        }
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) >= 1
    for c in chunks:
        assert "كىتاب ماۋزۇسى" not in c.text


def test_multi_page_stitched_safety_split_preserves_tight_per_chunk_page_spans():
    svc = ChunkingService(
        chunk_size=600, chunk_overlap=80, min_chunk_size=120, max_chunk_size=600
    )
    pages = [
        {
            "page_number": 10 + i,
            "is_toc": False,
            "text": f"بۇ {10 + i}-بەتتىكى ئۇزۇن ھېكايە تېكىستى بولۇپ توختىماي داۋاملىشىدۇ ۋە كېيىنكى بەتكە ئۇلىنىپ كېتىدۇ "
            * 5,
        }
        for i in range(5)
    ]
    sections = [
        {
            "id": 77,
            "level": 1,
            "title": "بىرىنچى باب",
            "start_page": 10,
            "end_page": 14,
            "section_index": 0,
        }
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) >= 4
    # No sub-chunk should inherit the full 5-page [10..14] range
    for ch in chunks:
        assert ch.end_page_number - ch.page_number <= 2
    assert chunks[0].page_number == 10
    assert chunks[-1].end_page_number == 14
    assert chunks[-1].page_number >= 13


def test_sentence_level_overlap_carries_trailing_sentences_on_long_paragraphs():
    svc = ChunkingService(chunk_size=450, chunk_overlap=120, min_chunk_size=150)
    para1 = (
        "بۇ بىرىنچى ئابزاسنىڭ دەسلەپكى جۈملىسى بولۇپ ناھايىتى مۇھىم مەزمۇننى بايان قىلىدۇ. "
        "ئوتتۇرىدىكى جۈملىمۇ تارىخىي ۋەقەلەرنى تەپسىلىي يورۇتۇپ بېرىدۇ ۋە ئوقۇرمەننى جەلپ قىلىدۇ. "
        "ئاخىرقى كۆۋرۈك جۈملە كېيىنكى بۆلەككە ئۇلىنىدۇ؟"
    )
    para2 = (
        "بۇ ئىككىنچى ئابزاسنىڭ يېڭى تېكىستى بولۇپ ئالدىنقى ئابزاس بىلەن مەزمۇن جەھەتتىن زىچ باغلىنىشلىق. "
        * 3
    ).strip()
    pages = [{"page_number": 1, "is_toc": False, "text": f"{para1}\n\n{para2}"}]
    sections = [{"id": 1, "level": 1, "title": "باب", "start_page": 1, "end_page": 1}]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) == 2
    assert "ئاخىرقى كۆۋرۈك جۈملە كېيىنكى بۆلەككە ئۇلىنىدۇ؟" in chunks[0].text
    assert "ئاخىرقى كۆۋرۈك جۈملە كېيىنكى بۆلەككە ئۇلىنىدۇ؟" in chunks[1].text


def test_bodyless_part_divider_preamble_emits_zero_stub_chunks():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=200, min_chunk_size=350)
    pages = [
        {
            "page_number": 13,
            "is_toc": False,
            "text": "بىرىنچى قىسىم\n\n# ھايات شۇنداق ئۆتكەن",
        },
        {
            "page_number": 15,
            "is_toc": False,
            "text": "# بىرىنچى باب\n\nبۇ بىرىنچى بابنىڭ ھەقىقىي ھېكايە تېكىستى بولۇپ ناھايىتى تەپسىلىي يېزىلغان.",
        },
    ]
    sections = [
        {
            "id": 100,
            "section_index": 0,
            "level": 1,
            "section_type": "chapter",
            "title": "بىرىنچى قىسىم ھايات شۇنداق ئۆتكەن",
            "start_page": 13,
            "start_block_index": 0,
            "end_page": 15,
            "end_block_index": 999999,
        },
        {
            "id": 101,
            "parent_id": 100,
            "parent_section_index": 0,
            "section_index": 1,
            "level": 2,
            "section_type": "chapter",
            "title": "بىرىنچى باب",
            "start_page": 15,
            "start_block_index": 0,
            "end_page": 15,
            "end_block_index": 999999,
        },
    ]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) == 1
    assert chunks[0].section_id == 101
    assert chunks[0].page_number == 15


def test_superscript_footnote_attaches_to_superscript_marker_not_bare_digit_year():
    svc = ChunkingService(chunk_size=300, chunk_overlap=0, min_chunk_size=50)
    text = (
        "بۇ 1985-يىلى يۈز بەرگەن تارىخىي ۋەقە ھەققىدە ئۇزۇن بىر بايان بولۇپ ھېچقانداق ئىزاھات بەلگىسى يوق.\n\n"
        "ئىككىنچى ئابزاس ئاخىرىدا ئالاھىدە ئاتالغۇ¹ ئىشلىتىلگەن بولۇپ ئىزاھات شۇنىڭغا تەۋە بولۇشى شەرت.\n\n"
        "¹ بۇ ئالاھىدە ئاتالغۇنىڭ تەپسىلىي ئىزاھاتى."
    )
    chunks = svc.split_text(text)
    # Force check which paragraph absorbed the footnote
    joined = "\n---\n".join(chunks)
    assert (
        "ئىشلىتىلگەن بولۇپ ئىزاھات شۇنىڭغا تەۋە بولۇشى شەرت.\n\n¹ بۇ ئالاھىدە" in joined
    )


def test_uyghur_sentence_separators_split_without_losing_punctuation():
    from app.services.chunking_service import (
        RecursiveCharacterTextSplitter,
        format_chunk_embedding_text,
    )

    splitter = RecursiveCharacterTextSplitter(chunk_size=60, chunk_overlap=0)
    sample = "سەن قەيەردىن كەلدىڭ؟ مەن قەشقەردىن كەلدىم! ئۇمۇ بۈگۈن يېتىپ كەلدى."
    parts = splitter.split_text(sample)
    assert len(parts) >= 2
    assert "؟" in parts[0]
    assert "!" in " ".join(parts)

    emb_txt = format_chunk_embedding_text(
        "بۇ دەۋردە ئىلىم-پەن گۈللەندى.",
        book_title="ئۇيغۇر تارىخى",
        section_title="قاراخانىيلار خانلىقى",
    )
    assert emb_txt.startswith("ئۇيغۇر تارىخى — قاراخانىيلار خانلىقى\n\n")


def test_compute_chunk_text_hash_invalidates_pre_v2_and_book_or_parent_renames():
    import hashlib
    from app.services.chunking_service import compute_chunk_text_hash

    body = "بۇ دەۋردە ئىلىم-پەن گۈللەندى."
    legacy_unprefixed_hash = hashlib.sha256(
        " ".join(body.split()).encode("utf-8")
    ).hexdigest()

    v2_no_ctx = compute_chunk_text_hash(body)
    assert v2_no_ctx != legacy_unprefixed_hash

    h_orig = compute_chunk_text_hash(
        body,
        book_title="ئۇيغۇر تارىخى",
        section_title="بىرىنچى قىسىم › قاراخانىيلار",
    )
    h_same = compute_chunk_text_hash(
        body,
        book_title="ئۇيغۇر تارىخى",
        section_title="بىرىنچى قىسىم › قاراخانىيلار",
    )
    h_renamed_book = compute_chunk_text_hash(
        body,
        book_title="ئوتتۇرا ئاسىيا تارىخى",
        section_title="بىرىنچى قىسىم › قاراخانىيلار",
    )
    h_renamed_parent = compute_chunk_text_hash(
        body,
        book_title="ئۇيغۇر تارىخى",
        section_title="ئىككىنچى قىسىم › قاراخانىيلار",
    )

    assert h_orig == h_same
    assert h_orig != h_renamed_book
    assert h_orig != h_renamed_parent


@pytest.mark.asyncio
async def test_load_book_embedding_context_propagates_db_errors_without_swallowing():
    from unittest.mock import AsyncMock
    from app.services.chunking_service import load_book_embedding_context

    broken_session = AsyncMock()
    broken_session.execute.side_effect = RuntimeError("connection lost")

    with pytest.raises(RuntimeError, match="connection lost"):
        await load_book_embedding_context(broken_session, "book-1")


def test_internal_paragraph_splitting_runs_only_when_gluing_across_pages():
    svc = ChunkingService(chunk_size=1500, chunk_overlap=0, min_chunk_size=10)
    pages = [
        {
            "page_number": 1,
            "is_toc": False,
            "text": (
                "بىرىنچى بەتنىڭ دەسلەپكى ئابزاسى تولۇق جۈملە بىلەن ئاخىرلاشتى.\n\n"
                "ئەخمەت ئۇزۇن يول يۈرۈپ كەچتە ئۆينىڭ ئىشىكىنى ئېچىپ ھويلىغا"
            ),
        },
        {
            "page_number": 2,
            "is_toc": False,
            "text": (
                "كىردى ۋە ئۆيدىكىلەرنىڭ ھەممىسىگە قىزغىن سالام بەردى.\n"
                "— ئەسسالامۇئەلەيكۇم، تىنچ-ئامان تۇردۇڭلارمۇ! — دېدى ئۇ كۈلۈمسىرەپ تۇرۇپ.\n\n"
                "ئانىسى ئورنىدىن تۇرۇپ ئوغلىنىڭ پېشانىسىگە سۆيۈپ قارشى ئالدى.\n"
                "— ۋەئەلەيكۇم ئەسسالام، خوش كەپسەن بالام، قېنى تۆرگە چىق!"
            ),
        },
        {
            "page_number": 3,
            "is_toc": False,
            "text": (
                "ئۇلار كەڭ داستىخان چۆرىسىدە جەم بولۇپ ئۇزۇن سۆھبەتلەشتى.\n"
                "— ئىسسىق چايدىن ئىچىپ ھاردۇقۇڭنى چىقارغىن، — دېدى ئانىسى."
            ),
        },
    ]
    sections = [{"id": 1, "level": 1, "title": "باب", "start_page": 1, "end_page": 3}]
    chunks = svc.chunk_book_sections(pages, sections)
    assert len(chunks) == 1
    full_text = chunks[0].text

    # 1. Cross-page unfinished sentence glued only to the wrapped sentence, with blank line before dialogue
    assert (
        "ئەخمەت ئۇزۇن يول يۈرۈپ كەچتە ئۆينىڭ ئىشىكىنى ئېچىپ ھويلىغا "
        "كىردى ۋە ئۆيدىكىلەرنىڭ ھەممىسىگە قىزغىن سالام بەردى.\n\n"
        "— ئەسسالامۇئەلەيكۇم، تىنچ-ئامان تۇردۇڭلارمۇ! — دېدى ئۇ كۈلۈمسىرەپ تۇرۇپ."
        in full_text
    )
    # 2. Middle block on page 2 kept its original single \n
    assert (
        "ئانىسى ئورنىدىن تۇرۇپ ئوغلىنىڭ پېشانىسىگە سۆيۈپ قارشى ئالدى.\n"
        "— ۋەئەلەيكۇم ئەسسالام، خوش كەپسەن بالام، قېنى تۆرگە چىق!" in full_text
    )
    # 3. Top block on page 3 (after page 2 ended cleanly with '!') kept its original single \n
    assert (
        "ئۇلار كەڭ داستىخان چۆرىسىدە جەم بولۇپ ئۇزۇن سۆھبەتلەشتى.\n"
        "— ئىسسىق چايدىن ئىچىپ ھاردۇقۇڭنى چىقارغىن، — دېدى ئانىسى." in full_text
    )


def test_extract_chunk_embedding_prefix_and_leading_overlap():
    from app.services.chunking_service import (
        extract_chunk_embedding_prefix,
        extract_leading_overlap,
    )

    body = "تۇنجى ئابزاس تېكىستى.\n\nئىككىنچى ئابزاس تېكىستى داۋاملىشىدۇ."
    prefix = extract_chunk_embedding_prefix(
        body,
        book_title="ئۇيغۇر تارىخى",
        section_title="بىرىنچى قىسىم › قاراخانىيلار",
    )
    assert prefix == "ئۇيغۇر تارىخى — بىرىنچى قىسىم › قاراخانىيلار"

    # When chunk already starts with both book & section titles, prefix is omitted
    redundant_body = (
        "# ئۇيغۇر تارىخى\n## بىرىنچى قىسىم › قاراخانىيلار\n\nئاساسىي مەزمۇن."
    )
    assert (
        extract_chunk_embedding_prefix(
            redundant_body,
            book_title="ئۇيغۇر تارىخى",
            section_title="بىرىنچى قىسىم › قاراخانىيلار",
        )
        is None
    )

    prev_chunk = (
        "بۇ بۆلەكنىڭ بېشىدىكى جۈملە.\n\n"
        "قاراخانىيلار دەۋرىدە ئىلىم-مەرىپەت ۋە مەدەنىيەت يۈكسەك تەرەققىي قىلدى."
    )
    cur_chunk = (
        "قاراخانىيلار دەۋرىدە ئىلىم-مەرىپەت ۋە مەدەنىيەت يۈكسەك تەرەققىي قىلدى.\n\n"
        "يۈسۈپ خاس ھاجىپ قۇتادغۇ بىلىكنى يازغان."
    )
    overlap = extract_leading_overlap(prev_chunk, cur_chunk)
    assert (
        overlap
        == "قاراخانىيلار دەۋرىدە ئىلىم-مەرىپەت ۋە مەدەنىيەت يۈكسەك تەرەققىي قىلدى."
    )
    assert extract_leading_overlap(None, cur_chunk) is None
    assert extract_leading_overlap(cur_chunk, cur_chunk) is None
