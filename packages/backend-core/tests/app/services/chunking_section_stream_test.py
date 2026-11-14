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
